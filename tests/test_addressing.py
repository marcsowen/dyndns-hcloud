import pytest

from dyndns_hcloud.addressing import client_ipv6, interface_id


@pytest.mark.parametrize("mac, expected", [
    ("00:11:22:33:44:55", "2001:db8:1:2:211:22ff:fe33:4455"),
    ("02-11-22-33-44-55", "2001:db8:1:2:11:22ff:fe33:4455"),
])
def test_eui64(mac, expected):
    assert client_ipv6("2001:db8:1:2::/64", mac) == expected
    assert client_ipv6("2001:db8:1:2::", mac) == expected


def test_delegated_prefix():
    assert client_ipv6("2001:db8:1234:ab00::/56", "00:11:22:33:44:55", 42) == "2001:db8:1234:ab2a:211:22ff:fe33:4455"


@pytest.mark.parametrize("prefix, subnet", [
    ("2001:db8::/65", 0), ("2001:db8::1/64", 0), ("2001:db8::/64", 1),
    ("2001:db8::/56", 256), ("2001:db8::/64", -1), ("::/0", 0),
    ("fe80::/64", 0), ("ff02::/64", 0), ("192.0.2.0/24", 0), ("<ip6lanprefix>", 0),
])
def test_invalid_prefix(prefix, subnet):
    with pytest.raises(ValueError):
        client_ipv6(prefix, "00:11:22:33:44:55", subnet)


@pytest.mark.parametrize("mac", ["00:11:22:33:44", "ff:ff:ff:ff:ff:ff", "01:11:22:33:44:55", "00:00:00:00:00:00", "00-11:22:33:44:55"])
def test_invalid_mac(mac):
    with pytest.raises(ValueError):
        interface_id(mac)
