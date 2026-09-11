"""Authenticated DynDNS HTTP GET endpoint."""

import hmac
import logging
from ipaddress import IPv4Address, IPv6Address
from threading import Lock

from flask import Flask, Response, request

from .addressing import client_ipv6, lan_network
from .config import Config
from .dns import HetznerDNS

log = logging.getLogger(__name__)


def create_app(config: Config, dns=None) -> Flask:
    app = Flask(__name__)
    updater = dns if dns is not None else HetznerDNS(config.hetzner)
    lock = Lock()

    def reply(body: str, status: int = 200) -> Response:
        response = Response(body + "\n", status=status, mimetype="text/plain")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/nic/update", methods=["GET"])
    def update():
        # Flask otherwise also enables HEAD, which must never mutate DNS.
        if request.method != "GET":
            return reply("badagent", 405)
        if any(len(request.args.getlist(key)) != 1 for key in request.args):
            return reply("notfqdn", 400)
        auth = request.authorization
        if auth is not None:
            username = auth.username if auth.type == "basic" else ""
            password = auth.password if auth.type == "basic" else ""
        else:
            username = request.args.get("username", "")
            password = request.args.get("password", "")
        user_ok = hmac.compare_digest((username or "").encode(), config.server.username.encode())
        pass_ok = hmac.compare_digest((password or "").encode(), config.server.password.get_secret_value().encode())
        if not (user_ok and pass_ok):
            response = reply("badauth", 401)
            response.headers["WWW-Authenticate"] = 'Basic realm="DynDNS"'
            return response
        # hostname identifies this configured zone; it cannot select arbitrary records.
        hostname = request.args.get("hostname", config.hetzner.zone).lower().rstrip(".")
        allowed = {config.hetzner.zone} | {
            f"{r.name}.{config.hetzner.zone}" for r in config.records if r.name != "@"
        }
        if hostname not in allowed:
            return reply("nohost", 400)
        ipv4 = request.args.get("myip", "").strip()
        ipv6 = request.args.get("myipv6", "").strip()
        prefix = request.args.get("ip6prefix", "").strip()
        if not ipv4 and not ipv6 and not prefix:
            return reply("notfqdn", 400)
        desired = []
        try:
            if ipv4:
                address = IPv4Address(ipv4)
                if address.is_unspecified or address.is_multicast or address.is_loopback or address.is_link_local or address.is_reserved:
                    raise ValueError("invalid IPv4 address")
                if config.apex.ipv4:
                    desired.append(("@", "A", str(address)))
                desired.extend((r.name, "A", str(address)) for r in config.records if r.ipv4)
            if ipv6:
                router_address = IPv6Address(ipv6)
                if (
                    router_address.scope_id is not None
                    or router_address.is_unspecified
                    or router_address.is_multicast
                    or router_address.is_loopback
                    or router_address.is_link_local
                    or router_address.ipv4_mapped is not None
                ):
                    raise ValueError("invalid router IPv6 address")
                if config.apex.ipv6:
                    desired.append(("@", "AAAA", str(router_address)))
            if prefix:
                lan_network(prefix)
                desired.extend(
                    (r.name, "AAAA", client_ipv6(prefix, r.mac, r.subnet_id))
                    for r in config.records
                )
        except ValueError:
            return reply("notfqdn", 400)
        if not desired:
            return reply("nochg")
        # One process owns a zone; serialize callbacks and reject overlapping work.
        if not lock.acquire(blocking=False):
            return reply("911", 503)
        try:
            changed = updater.update(desired)
        except Exception as exc:
            # Exceptions may include request URLs or credentials: log only the type.
            log.error("DNS update failed (%s)", type(exc).__name__)
            return reply("911", 503)
        finally:
            lock.release()
        return reply("good" if changed else "nochg")

    return app
