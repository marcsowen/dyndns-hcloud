import pytest


def test_dual_stack(receiver):
    client, dns = receiver
    response = client.get("/update", query_string={
        "username": "router", "password": "secret",
        "hostname": "example.com", "ipaddr": "198.51.100.12", "ip6lanprefix": "2001:db8::/64",
        "ip6addr": "2001:db8:abcd::1",
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


@pytest.mark.parametrize("params,kind", [({"ipaddr": "198.51.100.12"}, "A"), ({"ip6lanprefix": "2001:db8::/64", "ipaddr": ""}, "AAAA")])
def test_single_family_and_query_auth(receiver, params, kind):
    client, dns = receiver
    dns.update.return_value = False
    response = client.get("/update", query_string={"username": "router", "password": "secret", **params})
    assert response.text == "nochg\n"
    assert all(item[1] == kind for item in dns.update.call_args.args[0])


@pytest.mark.parametrize("auth", [None, ("router", "wrong"), ("wrong", "secret"), ("röuter", "secret")])
@pytest.mark.parametrize("query_auth", [True, False])
def test_bad_auth(receiver, auth, query_auth):
    client, dns = receiver
    if query_auth:
        credentials = {} if auth is None else {"username": auth[0], "password": auth[1]}
        response = client.get("/update", query_string={"ipaddr": "198.51.100.12", **credentials})
    else:
        response = client.get("/update?ipaddr=198.51.100.12", auth=auth)
    assert response.status_code == 401
    assert response.text == "badauth\n"
    assert "WWW-Authenticate" not in response.headers
    dns.update.assert_not_called()


def test_query_credentials_override_authorization_header(receiver):
    client, dns = receiver
    response = client.get("/update", auth=("wrong", "wrong"), query_string={
        "username": "router", "password": "secret", "ipaddr": "198.51.100.12",
    })
    assert response.text == "good\n"
    dns.update.assert_called_once()


def test_invalid_query_credentials_do_not_fall_back_to_basic(receiver):
    client, dns = receiver
    response = client.get("/update", auth=("router", "secret"), query_string={
        "username": "router", "password": "wrong", "ipaddr": "198.51.100.12",
    })
    assert response.status_code == 401
    dns.update.assert_not_called()


@pytest.mark.parametrize("path,status", [("/update", 401), ("/secret-path", 404)])
def test_request_logging_does_not_expose_credentials(receiver, caplog, path, status):
    client, dns = receiver
    caplog.set_level("INFO", logger="dyndns_hcloud.app")
    response = client.get(path, query_string={
        "username": "private-user", "password": "private-password", "token": "private-token",
    })
    assert response.status_code == status
    assert "HTTP request received" in caplog.text
    assert str(status) in caplog.text
    for secret in ("private-user", "private-password", "private-token", "secret-path"):
        assert secret not in caplog.text
    dns.update.assert_not_called()


def test_router_ipv6_only(receiver):
    client, dns = receiver
    response = client.get("/update?ip6addr=2001:0db8:abcd::1", auth=("router", "secret"))
    assert response.text == "good\n"
    dns.update.assert_called_once_with([("@", "AAAA", "2001:db8:abcd::1")])


@pytest.mark.parametrize("source", ["192.168.178.1", "2001:db8::1"])
def test_log_source_and_received_addresses(receiver, caplog, source):
    client, _ = receiver
    caplog.set_level("INFO", logger="dyndns_hcloud.app")
    response = client.get("/update", query_string={
        "username": "router", "password": "secret",
        "ipaddr": "198.51.100.12", "ip6addr": "2001:0db8:abcd::1",
        "ip6lanprefix": "2001:db8:1234::/64",
    }, environ_overrides={"REMOTE_ADDR": source},
        headers={"X-Forwarded-For": "192.0.2.99"})
    assert response.status_code == 200
    assert f"from {source!r}" in caplog.text
    assert "ipaddr='198.51.100.12'" in caplog.text
    assert "ip6addr='2001:0db8:abcd::1'" in caplog.text
    assert "ip6lanprefix='2001:db8:1234::/64'" in caplog.text
    assert "192.0.2.99" not in caplog.text
    assert "secret" not in caplog.text
    assert "username=" not in caplog.text


def test_log_empty_and_missing_parameters(receiver, caplog):
    client, _ = receiver
    caplog.set_level("INFO", logger="dyndns_hcloud.app")
    response = client.get("/update", query_string={
        "username": "router", "password": "secret", "ipaddr": "",
    })
    assert response.status_code == 400
    assert "ipaddr=''" in caplog.text
    assert "ip6addr='<missing>'" in caplog.text
    assert "ip6lanprefix='<missing>'" in caplog.text


def test_parameter_logs_escape_and_bound_invalid_inputs(receiver, caplog):
    client, dns = receiver
    caplog.set_level("INFO", logger="dyndns_hcloud.app")
    response = client.get("/update", query_string={
        "username": "router", "password": "secret",
        "ipaddr": "bad\nforged log", "ip6addr": "x" * 1000,
    })
    assert response.status_code == 400
    assert "bad\\nforged log" in caplog.text
    assert "bad\nforged log" not in caplog.text
    assert "x" * 128 + "...<truncated>" in caplog.text
    assert "x" * 129 not in caplog.text
    dns.update.assert_not_called()


def test_prefix_never_sets_router_ipv6(receiver):
    client, dns = receiver
    response = client.get("/update?ip6lanprefix=2001:db8::/64&ip6addr=", auth=("router", "secret"))
    assert response.text == "good\n"
    assert all(name != "@" for name, _, _ in dns.update.call_args.args[0])


@pytest.mark.parametrize("value", ["bad", "198.51.100.12", "::", "::1", "ff02::1", "fe80::1", "2001:db8::1%eth0", "::ffff:198.51.100.12", "2001:db8::/64"])
def test_invalid_router_ipv6_rejects_entire_callback(receiver, value):
    client, dns = receiver
    response = client.get("/update", auth=("router", "secret"), query_string={
        "ipaddr": "198.51.100.12", "ip6addr": value, "ip6lanprefix": "2001:db8::/64",
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
    response = client.get("/update", auth=("router", "secret"), query_string={
        "ipaddr": "198.51.100.12", "ip6addr": "2001:db8:abcd::1", "ip6lanprefix": "2001:db8::/64",
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
    response = client.get("/update", auth=("router", "secret"), query_string={
        "ipaddr": "198.51.100.12", "ip6addr": "2001:db8:abcd::1",
    })
    assert response.status_code == 200
    dns.update.assert_called_once_with([("@", "A", "198.51.100.12"), ("@", "AAAA", "2001:db8:abcd::1")])
    dns.reset_mock()
    assert client.get("/update?ip6lanprefix=bad", auth=("router", "secret")).status_code == 400
    dns.update.assert_not_called()


@pytest.mark.parametrize("query", [
    "ipaddr=garbage", "ipaddr=::1", "ipaddr=0.0.0.0", "ipaddr=127.0.0.1", "ipaddr=224.0.0.1",
    "ipaddr=198.51.100.12&ip6lanprefix=bad", "ip6lanprefix=2001:db8::/65", "",
    "ipaddr=198.51.100.12&hostname=attacker.net", "ipaddr=198.51.100.12&ipaddr=198.51.100.13",
])
def test_invalid_input_has_no_side_effects(receiver, query):
    client, dns = receiver
    assert client.get("/update?" + query, auth=("router", "secret")).status_code == 400
    dns.update.assert_not_called()


@pytest.mark.parametrize("method", ["HEAD", "POST", "OPTIONS"])
def test_other_methods_never_update(receiver, method):
    client, dns = receiver
    client.open("/update?ipaddr=198.51.100.12", method=method, auth=("router", "secret"))
    dns.update.assert_not_called()


def test_api_failure_and_retry(receiver, caplog):
    client, dns = receiver
    dns.update.side_effect = RuntimeError("secret test-token")
    response = client.get("/update?ipaddr=198.51.100.12", auth=("router", "secret"))
    assert response.status_code == 503
    assert response.text == "911\n"
    assert "secret" not in caplog.text
    dns.update.side_effect = None
    assert client.get("/update?ipaddr=198.51.100.12", auth=("router", "secret")).status_code == 200


def test_overlapping_callback(receiver):
    client, dns = receiver
    def nested_update(desired):
        response = client.get("/update?ipaddr=198.51.100.13", auth=("router", "secret"))
        assert response.status_code == 503
        return True
    dns.update.side_effect = nested_update
    assert client.get("/update?ipaddr=198.51.100.12", auth=("router", "secret")).text == "good\n"
