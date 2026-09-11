"""Authenticated DynDNS HTTP GET endpoint."""

import hmac
import logging
from ipaddress import IPv4Address, IPv6Address
from threading import Lock
from time import monotonic

from flask import Flask, Response, g, request

from .addressing import client_ipv6, lan_network
from .config import Config
from .dns import HetznerDNS

log = logging.getLogger(__name__)


def create_app(config: Config, dns=None) -> Flask:
    app = Flask(__name__)
    updater = dns if dns is not None else HetznerDNS(config.hetzner)
    lock = Lock()

    @app.before_request
    def log_request():
        g.started = monotonic()
        # Use a fixed label; paths, query strings and headers can contain secrets.
        endpoint = "/update" if request.endpoint == "update" else "unmatched route"
        log.info("HTTP request received for %s", endpoint)

    @app.after_request
    def log_unmatched_response(response):
        if request.endpoint != "update":
            log.info("HTTP response for unmatched route: %s", response.status_code)
        return response

    def reply(body: str, status: int = 200) -> Response:
        # body is an internal protocol code, never user-provided text.
        log.info("DynDNS response: HTTP %s, %s (%.2fs)", status, body, monotonic() - g.started)
        response = Response(body + "\n", status=status, mimetype="text/plain")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/update", methods=["GET"])
    def update():
        # Flask otherwise also enables HEAD, which must never mutate DNS.
        if request.method != "GET":
            return reply("badagent", 405)
        if any(len(request.args.getlist(key)) != 1 for key in request.args):
            return reply("notfqdn", 400)
        # FRITZ!Box substitutes credentials in the configured URL. They take
        # precedence over an incidental Authorization header, even if invalid.
        if "username" in request.args or "password" in request.args:
            username = request.args.get("username", "")
            password = request.args.get("password", "")
        elif (auth := request.authorization) is not None:
            username = auth.username if auth.type == "basic" else ""
            password = auth.password if auth.type == "basic" else ""
        else:
            username = password = ""
        user_ok = hmac.compare_digest((username or "").encode(), config.server.username.encode())
        pass_ok = hmac.compare_digest((password or "").encode(), config.server.password.get_secret_value().encode())
        if not (user_ok and pass_ok):
            return reply("badauth", 401)
        # hostname identifies this configured zone; it cannot select arbitrary records.
        hostname = request.args.get("hostname", config.hetzner.zone).lower().rstrip(".")
        allowed = {config.hetzner.zone} | {
            f"{r.name}.{config.hetzner.zone}" for r in config.records if r.name != "@"
        }
        if hostname not in allowed:
            return reply("nohost", 400)
        ipv4 = request.args.get("ipaddr", "").strip()
        ipv6 = request.args.get("ip6addr", "").strip()
        prefix = request.args.get("ip6lanprefix", "").strip()
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
            log.info("No record sets enabled for the supplied addresses")
            return reply("nochg")
        log.info("Authenticated update validated: %d A and %d AAAA record sets",
                 sum(kind == "A" for _, kind, _ in desired),
                 sum(kind == "AAAA" for _, kind, _ in desired))
        # One process owns a zone; serialize callbacks and reject overlapping work.
        if not lock.acquire(blocking=False):
            log.info("Update deferred: another DNS update is still running")
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
