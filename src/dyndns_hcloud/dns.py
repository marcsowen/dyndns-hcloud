"""Reconcile only configured A/AAAA record sets through hcloud."""

import logging
from contextlib import contextmanager
from ipaddress import ip_address
from time import monotonic

from hcloud import Client
from hcloud.zones import ZoneRecord

from .config import Hetzner

log = logging.getLogger(__name__)


@contextmanager
def operation(description: str):
    """Time API work without logging exception text, URLs or credentials."""
    started = monotonic()
    log.info("%s: started", description)
    try:
        yield
    except Exception as exc:
        log.error("%s: failed after %.2fs (%s)", description, monotonic() - started, type(exc).__name__)
        raise
    else:
        log.info("%s: completed in %.2fs", description, monotonic() - started)


class HetznerDNS:
    def __init__(self, config: Hetzner, client: Client | None = None):
        self.config = config
        self.client = client or Client(
            token=config.token.get_secret_value(),
            application_name="dyndns-hcloud",
            application_version="0.1.0",
            timeout=10,
        )

    @staticmethod
    def wait(action):
        with operation(f"Waiting for Hetzner action {action.id}"):
            action.wait_until_finished(max_retries=30)

    def update(self, desired: list[tuple[str, str, str]]) -> bool:
        started = monotonic()
        log.info("Reconciling %s: %d requested record sets", self.config.zone, len(desired))
        with operation(f"Fetching zone {self.config.zone}"):
            zone = self.client.zones.get(self.config.zone)
        if zone.mode != "primary":
            raise RuntimeError("DNS zone must be primary")
        with operation("Fetching existing DNS record sets"):
            existing = {(rr.name, rr.type): rr for rr in zone.get_rrset_all()}
        log.info("Fetched %d existing record sets", len(existing))
        # Detect CNAME conflicts before making any changes.
        if any((name, "CNAME") in existing for name, _, _ in desired):
            raise RuntimeError("configured name has a CNAME record")
        changed = 0
        for name, kind, value in desired:
            fqdn = self.config.zone if name == "@" else f"{name}.{self.config.zone}"
            label = f"{fqdn} {kind}"
            rrset = existing.get((name, kind))
            if rrset is None:
                with operation(f"Creating {label} = {value} (TTL {self.config.ttl})"):
                    response = zone.create_rrset(
                        name=name, type=kind, ttl=self.config.ttl,
                        records=[ZoneRecord(value=value)],
                    )
                self.wait(response.action)
                changed += 1
                continue
            records = rrset.records or []
            same = len(records) == 1 and ip_address(records[0].value) == ip_address(value)
            if not same:
                comment = records[0].comment if len(records) == 1 else None
                with operation(f"Updating {label} = {value}"):
                    action = rrset.set_rrset_records([ZoneRecord(value=value, comment=comment)])
                self.wait(action)
            if rrset.ttl != self.config.ttl:
                with operation(f"Setting {label} TTL to {self.config.ttl}"):
                    action = rrset.change_rrset_ttl(self.config.ttl)
                self.wait(action)
            if not same or rrset.ttl != self.config.ttl:
                changed += 1
            else:
                log.info("Unchanged %s = %s (TTL %d); skipped", label, value, self.config.ttl)
        log.info("DNS reconciliation completed in %.2fs: %d changed, %d unchanged",
                 monotonic() - started, changed, len(desired) - changed)
        return bool(changed)
