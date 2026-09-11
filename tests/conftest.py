from unittest.mock import Mock

import pytest

from dyndns_hcloud.app import create_app
from dyndns_hcloud.config import Config


@pytest.fixture
def config():
    return Config.model_validate({
        "server": {"username": "router", "password": "secret"},
        "hetzner": {"token": "test-token", "zone": "example.com"},
        "records": [
            {"name": "nas", "mac": "00:11:22:33:44:55", "ipv4": True},
            {"name": "host", "mac": "02:11:22:33:44:66"},
        ],
    })


@pytest.fixture
def receiver(config):
    dns = Mock()
    dns.update.return_value = True
    app = create_app(config, dns)
    app.testing = True
    return app.test_client(), dns
