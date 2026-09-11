import argparse
import logging

from pydantic import ValidationError
from waitress import serve

from .app import create_app
from .config import Config


def main():
    parser = argparse.ArgumentParser(description="Receive DynDNS updates for Hetzner DNS")
    parser.add_argument("--config", required=True, help="Path to TOML configuration")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration without API calls")
    args = parser.parse_args()
    try:
        config = Config.load(args.config)
    except ValidationError as exc:
        # Pydantic's default exception text includes input values, possibly secrets.
        for error in exc.errors(include_input=False, include_context=False, include_url=False):
            print(f"{'.'.join(map(str, error['loc']))}: {error['msg']}")
        parser.exit(2, "Invalid configuration\n")
    except (OSError, ValueError):
        parser.exit(2, "Unable to read configuration or invalid TOML\n")
    if args.check_config:
        print("Configuration is valid")
        return
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    serve(create_app(config), host=config.server.host, port=config.server.port, threads=4)


if __name__ == "__main__":
    main()
