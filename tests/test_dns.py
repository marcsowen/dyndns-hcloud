import pytest

from dyndns_hcloud.dns import HetznerDNS

BASE = "https://api.hetzner.cloud/v1"


def action(status="success"):
    return {"id": 77, "status": status, "command": "set_records", "progress": 100,
            "started": "2026-09-11T00:00:00Z", "finished": "2026-09-11T00:00:01Z",
            "resources": [], "error": {"code": "failed", "message": "test"} if status == "error" else None}


def setup_zone(mock, rrsets, mode="primary"):
    mock.get(BASE + "/zones/example.com", json={"zone": {"id": 1, "name": "example.com", "mode": mode}})
    mock.get(BASE + "/zones/1/rrsets", json={"rrsets": rrsets, "meta": {"pagination": {"page": 1, "per_page": 100, "next_page": None}}})
    mock.get(BASE + "/actions/77", json={"action": action()})


def rr(name="nas", kind="A", value="198.51.100.1", ttl=300):
    return {"id": f"{name}/{kind}", "zone": 1, "name": name, "type": kind, "ttl": ttl,
            "records": [{"value": value, "comment": "keep me"}]}


def test_create_and_poll(config, requests_mock, caplog):
    caplog.set_level("INFO", logger="dyndns_hcloud.dns")
    setup_zone(requests_mock, [])
    post = requests_mock.post(BASE + "/zones/1/rrsets", json={"rrset": rr(), "action": action("running")})
    assert HetznerDNS(config.hetzner).update([("nas", "A", "198.51.100.1")])
    assert post.last_request.json() == {"name": "nas", "type": "A", "ttl": 300, "records": [{"value": "198.51.100.1"}]}
    assert requests_mock.last_request.path == "/v1/actions/77"
    assert "Creating nas.example.com A = 198.51.100.1 (TTL 300): started" in caplog.text
    assert "Waiting for Hetzner action 77: started" in caplog.text
    assert "Waiting for Hetzner action 77: completed in" in caplog.text
    assert "1 changed, 0 unchanged" in caplog.text
    assert "test-token" not in caplog.text


def test_replace_and_ttl(config, requests_mock, caplog):
    caplog.set_level("INFO", logger="dyndns_hcloud.dns")
    setup_zone(requests_mock, [rr(ttl=600), rr("unrelated")])
    post = requests_mock.post(BASE + "/zones/1/rrsets/nas/A/actions/set_records", json={"action": action()})
    ttl = requests_mock.post(BASE + "/zones/1/rrsets/nas/A/actions/change_ttl", json={"action": action()})
    assert HetznerDNS(config.hetzner).update([("nas", "A", "198.51.100.2")])
    assert post.last_request.json() == {"records": [{"value": "198.51.100.2", "comment": "keep me"}]}
    assert ttl.last_request.json() == {"ttl": 300}
    assert "Updating nas.example.com A = 198.51.100.2: started" in caplog.text
    assert "Setting nas.example.com A TTL to 300: started" in caplog.text
    assert "1 changed, 0 unchanged" in caplog.text
    assert "keep me" not in caplog.text


def test_unchanged_ipv6(config, requests_mock, caplog):
    caplog.set_level("INFO", logger="dyndns_hcloud.dns")
    setup_zone(requests_mock, [rr(kind="AAAA", value="2001:0db8:0000:0000:0000:0000:0000:0001")])
    assert not HetznerDNS(config.hetzner).update([("nas", "AAAA", "2001:db8::1")])
    assert all(r.method == "GET" for r in requests_mock.request_history)
    assert "Unchanged nas.example.com AAAA = 2001:db8::1" in caplog.text
    assert "0 changed, 1 unchanged" in caplog.text


def test_cname_conflict_preflight(config, requests_mock):
    setup_zone(requests_mock, [rr("host", "CNAME", "example.org.")])
    with pytest.raises(RuntimeError):
        HetznerDNS(config.hetzner).update([("nas", "A", "198.51.100.1"), ("host", "AAAA", "2001:db8::1")])
    assert all(r.method == "GET" for r in requests_mock.request_history)


def test_failed_action(config, requests_mock, caplog):
    caplog.set_level("INFO", logger="dyndns_hcloud.dns")
    setup_zone(requests_mock, [])
    requests_mock.post(BASE + "/zones/1/rrsets", json={"rrset": rr(), "action": action()})
    failed = action("error")
    failed["error"]["message"] = "sensitive-error-details"
    requests_mock.get(BASE + "/actions/77", json={"action": failed})
    from hcloud.actions import ActionFailedException
    with pytest.raises(ActionFailedException):
        HetznerDNS(config.hetzner).update([("nas", "A", "198.51.100.1")])
    assert "Waiting for Hetzner action 77: failed after" in caplog.text
    assert "DNS reconciliation completed" not in caplog.text
    assert "sensitive-error-details" not in caplog.text


def test_secondary_zone(config, requests_mock):
    setup_zone(requests_mock, [], mode="secondary")
    with pytest.raises(RuntimeError):
        HetznerDNS(config.hetzner).update([("nas", "A", "198.51.100.1")])


def test_paginated_zone(config, requests_mock):
    setup_zone(requests_mock, [])
    requests_mock.get(BASE + "/zones/1/rrsets", [
        {"json": {"rrsets": [rr("unrelated")], "meta": {"pagination": {"page": 1, "per_page": 1, "next_page": 2}}}},
        {"json": {"rrsets": [rr()], "meta": {"pagination": {"page": 2, "per_page": 1, "next_page": None}}}},
    ])
    assert not HetznerDNS(config.hetzner).update([("nas", "A", "198.51.100.1")])
    assert requests_mock.last_request.qs["page"] == ["2"]


def test_retry_reconciles_partial_success(config, requests_mock):
    from hcloud import APIException

    setup_zone(requests_mock, [])
    creation = requests_mock.post(BASE + "/zones/1/rrsets", [
        {"json": {"rrset": rr(), "action": action()}},
        {"status_code": 403, "json": {"error": {"code": "forbidden", "message": "test"}}},
        {"json": {"rrset": rr("host", "AAAA", "2001:db8::1"), "action": action()}},
    ])
    updater = HetznerDNS(config.hetzner)
    desired = [("nas", "A", "198.51.100.1"), ("host", "AAAA", "2001:db8::1")]
    with pytest.raises(APIException):
        updater.update(desired)
    setup_zone(requests_mock, [rr()])
    assert updater.update(desired)
    assert creation.call_count == 3
    assert creation.last_request.json()["name"] == "host"
