"""IPv6 modified EUI-64 construction."""

import re
from ipaddress import IPv6Address, IPv6Network


def interface_id(mac: str) -> int:
    if not re.fullmatch(r"[0-9a-fA-F]{2}([:-])(?:[0-9a-fA-F]{2}\1){4}[0-9a-fA-F]{2}", mac):
        raise ValueError("MAC must contain six octets separated by colons or hyphens")
    octets = bytearray.fromhex(mac.replace(":", "").replace("-", ""))
    if octets[0] & 1 or not any(octets):
        raise ValueError("MAC must be a nonzero unicast address")
    octets[0] ^= 2
    return int.from_bytes(octets[:3] + b"\xff\xfe" + octets[3:], "big")


def lan_network(prefix: str) -> IPv6Network:
    # An address without an explicit prefix length denotes a LAN /64.
    network = IPv6Network(prefix if "/" in prefix else prefix + "/64", strict=True)
    if not 1 <= network.prefixlen <= 64:
        raise ValueError("IPv6 prefix length must be between 1 and 64")
    if network.network_address.is_multicast or network.network_address.is_link_local or network.network_address.is_unspecified:
        raise ValueError("IPv6 prefix must be a routed unicast prefix")
    return network


def client_ipv6(prefix: str, mac: str, subnet_id: int = 0) -> str:
    network = lan_network(prefix)
    if not 0 <= subnet_id < 1 << (64 - network.prefixlen):
        raise ValueError("subnet_id does not fit the supplied prefix")
    return str(IPv6Address(int(network.network_address) | subnet_id << 64 | interface_id(mac)))
