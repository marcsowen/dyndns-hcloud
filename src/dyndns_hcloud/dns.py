"""Reconcile only configured A/AAAA record sets through hcloud."""

from ipaddress import ip_address

from hcloud import Client
from hcloud.zones import ZoneRecord

from .config import Hetzner


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
        action.wait_until_finished(max_retries=30)

    def update(self, desired: list[tuple[str, str, str]]) -> bool:
        zone = self.client.zones.get(self.config.zone)
        if zone.mode != "primary":
            raise RuntimeError("DNS zone must be primary")
        existing = {(rr.name, rr.type): rr for rr in zone.get_rrset_all()}
        # Detect CNAME conflicts before making any changes.
        if any((name, "CNAME") in existing for name, _, _ in desired):
            raise RuntimeError("configured name has a CNAME record")
        changed = False
        for name, kind, value in desired:
            rrset = existing.get((name, kind))
            if rrset is None:
                response = zone.create_rrset(
                    name=name, type=kind, ttl=self.config.ttl,
                    records=[ZoneRecord(value=value)],
                )
                self.wait(response.action)
                changed = True
                continue
            records = rrset.records or []
            same = len(records) == 1 and ip_address(records[0].value) == ip_address(value)
            if not same:
                comment = records[0].comment if len(records) == 1 else None
                self.wait(rrset.set_rrset_records([ZoneRecord(value=value, comment=comment)]))
                changed = True
            if rrset.ttl != self.config.ttl:
                self.wait(rrset.change_rrset_ttl(self.config.ttl))
                changed = True
        return changed
