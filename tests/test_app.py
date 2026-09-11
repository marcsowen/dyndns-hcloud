import pytest


def test_dual_stack(receiver):
    client, dns = receiver
    response = client.get("/nic/update", auth=("router", "secret"), query_string={
        "hostname": "example.com", "myip": "198.51.100.12", "ip6prefix": "2001:db8::/64",
        "myipv6": "2001:db8:abcd::1",
    })
    assert response.status_code == 200
    assert response.text == "good\n"
    assert response.headers["Cache-Control"] == "no-store"
    dns.update.assert_called_once_with([
        ("@", "A", "198.51.100.12"),
        ("nas", "A", "198.51.100.12"),
        ("@", "AAAA", "2001:db8:abcd::1"),
        ("nas", "AAAA", "2001:db8::211:22ff:fe33:4455"),
        ("host", "AAAA", "2001:db8::11:22ff:fe33:4466"),
    ])


@pytest.mark.parametrize("params,kind", [({"myip": "198.51.100.12"}, "A"), ({"ip6prefix": "2001:db8::/64", "myip": ""}, "AAAA")])
def test_single_family_and_query_auth(receiver, params, kind):
    client, dns = receiver
    dns.update.return_value = False
    response = client.get("/nic/update", query_string={"username": "router", "password": "secret", **params})
    assert response.text == "nochg\n"
    assert all(item[1] == kind for item in dns.update.call_args.args[0])


@pytest.mark.parametrize("auth", [None, ("router", "wrong"), ("wrong", "secret"), ("röuter", "secret")])
def test_bad_auth(receiver, auth):
    client, dns = receiver
    response = client.get("/nic/update?myip=198.51.100.12", auth=auth)
    assert response.status_code == 401
    assert response.text == "badauth\n"
    dns.update.assert_not_called()


def test_router_ipv6_only(receiver):
    client, dns = receiver
    response = client.get("/nic/update?myipv6=2001:0db8:abcd::1", auth=("router", "secret"))
    assert response.text == "good\n"
    dns.update.assert_called_once_with([("@", "AAAA", "2001:db8:abcd::1")])


def test_prefix_never_sets_router_ipv6(receiver):
    client, dns = receiver
    response = client.get("/nic/update?ip6prefix=2001:db8::/64&myipv6=", auth=("router", "secret"))
    assert response.text == "good\n"
    assert all(name != "@" for name, _, _ in dns.update.call_args.args[0])


@pytest.mark.parametrize("value", ["bad", "198.51.100.12", "::", "::1", "ff02::1", "fe80::1", "2001:db8::1%eth0", "::ffff:198.51.100.12", "2001:db8::/64"])
def test_invalid_router_ipv6_rejects_entire_callback(receiver, value):
    client, dns = receiver
    response = client.get("/nic/update", auth=("router", "secret"), query_string={
        "myip": "198.51.100.12", "myipv6": value, "ip6prefix": "2001:db8::/64",
    })
    assert response.status_code == 400
    dns.update.assert_not_called()


@pytest.mark.parametrize("ipv4,ipv6", [(False, False), (True, False), (False, True)])
def test_apex_options(config, ipv4, ipv6):
    from unittest.mock import Mock
    from dyndns_hcloud.app import create_app
    from dyndns_hcloud.config import Config

    data = config.model_dump()
    data["apex"] = {"ipv4": ipv4, "ipv6": ipv6}
    dns = Mock()
    client = create_app(Config.model_validate(data), dns).test_client()
    response = client.get("/nic/update", auth=("router", "secret"), query_string={
        "myip": "198.51.100.12", "myipv6": "2001:db8:abcd::1", "ip6prefix": "2001:db8::/64",
    })
    assert response.status_code == 200
    desired = dns.update.call_args.args[0]
    assert (("@", "A", "198.51.100.12") in desired) is ipv4
    assert (("@", "AAAA", "2001:db8:abcd::1") in desired) is ipv6
    assert ("nas", "AAAA", "2001:db8::211:22ff:fe33:4455") in desired


def test_apex_only_configuration(config):
    from unittest.mock import Mock
    from dyndns_hcloud.app import create_app
    from dyndns_hcloud.config import Config

    data = config.model_dump()
    del data["records"]
    dns = Mock()
    client = create_app(Config.model_validate(data), dns).test_client()
    response = client.get("/nic/update", auth=("router", "secret"), query_string={
        "myip": "198.51.100.12", "myipv6": "2001:db8:abcd::1",
    })
    assert response.status_code == 200
    dns.update.assert_called_once_with([("@", "A", "198.51.100.12"), ("@", "AAAA", "2001:db8:abcd::1")])
    dns.reset_mock()
    assert client.get("/nic/update?ip6prefix=bad", auth=("router", "secret")).status_code == 400
    dns.update.assert_not_called()


@pytest.mark.parametrize("query", [
    "myip=garbage", "myip=::1", "myip=0.0.0.0", "myip=127.0.0.1", "myip=224.0.0.1",
    "myip=198.51.100.12&ip6prefix=bad", "ip6prefix=2001:db8::/65", "",
    "myip=198.51.100.12&hostname=attacker.net", "myip=198.51.100.12&myip=198.51.100.13",
])
def test_invalid_input_has_no_side_effects(receiver, query):
    client, dns = receiver
    assert client.get("/nic/update?" + query, auth=("router", "secret")).status_code == 400
    dns.update.assert_not_called()


@pytest.mark.parametrize("method", ["HEAD", "POST", "OPTIONS"])
def test_other_methods_never_update(receiver, method):
    client, dns = receiver
    client.open("/nic/update?myip=198.51.100.12", method=method, auth=("router", "secret"))
    dns.update.assert_not_called()


def test_api_failure_and_retry(receiver, caplog):
    client, dns = receiver
    dns.update.side_effect = RuntimeError("secret test-token")
    response = client.get("/nic/update?myip=198.51.100.12", auth=("router", "secret"))
    assert response.status_code == 503
    assert response.text == "911\n"
    assert "secret" not in caplog.text
    dns.update.side_effect = None
    assert client.get("/nic/update?myip=198.51.100.12", auth=("router", "secret")).status_code == 200


def test_overlapping_callback(receiver):
    client, dns = receiver
    def nested_update(desired):
        response = client.get("/nic/update?myip=198.51.100.13", auth=("router", "secret"))
        assert response.status_code == 503
        return True
    dns.update.side_effect = nested_update
    assert client.get("/nic/update?myip=198.51.100.12", auth=("router", "secret")).text == "good\n"
