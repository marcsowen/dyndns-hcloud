"""Check the CLI's binding options with the real Waitress address resolver."""

import socket

import pytest
from waitress.adjustments import Adjustments

from dyndns_hcloud import __main__ as cli
from dyndns_hcloud.config import Config


@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 is unavailable on this host")
@pytest.mark.parametrize("use_example", [False, True])
def test_cli_resolves_both_wildcard_interfaces(config, monkeypatch, use_example):
    if use_example:
        config = Config.load("config.example.toml")
    monkeypatch.setattr(cli.Config, "load", lambda path: config)
    monkeypatch.setattr("sys.argv", ["dyndns-hcloud", "--config", "unused.toml"])
    listeners = []

    def capture_serve(app, **kwargs):
        listeners.extend(Adjustments(**kwargs).listen)

    monkeypatch.setattr(cli, "serve", capture_serve)
    cli.main()
    assert {(family, address[0], address[1]) for family, _, _, address in listeners} == {
        (socket.AF_INET, "0.0.0.0", 8080),
        (socket.AF_INET6, "::", 8080),
    }
