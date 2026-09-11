import pytest
from pydantic import ValidationError

from dyndns_hcloud.config import Config


def test_example():
    assert len(Config.load("config.example.toml").records) == 2


def test_apex_enabled_by_default(config):
    assert config.apex.ipv4 and config.apex.ipv6


@pytest.mark.parametrize("ipv4,ipv6", [(True, True), (True, False), (False, True)])
def test_apex_client_conflict(config, ipv4, ipv6):
    data = config.model_dump()
    data["records"][0]["name"] = "@"
    data["apex"] = {"ipv4": ipv4, "ipv6": ipv6}
    with pytest.raises(ValidationError, match="disable both apex options"):
        Config.model_validate(data)
    data["apex"] = {"ipv4": False, "ipv6": False}
    assert Config.model_validate(data).records[0].name == "@"


@pytest.mark.parametrize("section,key,value", [
    ("server", "password", ""), ("server", "port", 0),
    ("hetzner", "token", ""), ("hetzner", "zone", "../wrong"),
    ("hetzner", "ttl", 0), ("server", "typo", True),
])
def test_invalid_config(config, section, key, value):
    data = config.model_dump()
    data[section][key] = value
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_duplicate_names(config):
    data = config.model_dump()
    data["records"][1]["name"] = "NAS"
    with pytest.raises(ValidationError):
        Config.model_validate(data)
