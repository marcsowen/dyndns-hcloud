# dyndns-hcloud

Keep your domain pointing to your home network when your internet address changes.
This Python service receives updates from a FRITZ!Box and updates your DNS records
at Hetzner. It can also give devices such as a NAS their own IPv6 subdomain.

## Getting started

These installation instructions target recent versions of **Ubuntu** and
**Raspberry Pi OS** (Lite or Desktop), with Python 3.11 or newer.
You need a DNS zone in Hetzner Console and a read/write
API token for its project. The service must be reachable by your FRITZ!Box. You can
run it on a Raspberry Pi in your trusted home network using HTTP directly, without
a reverse proxy. For connections over the internet, use [HTTPS](#https-setup).

### 1. Install prerequisites

Both systems use the same steps. Install Python and the required system packages:

```sh
sudo apt update
sudo apt install python3 python3-venv ca-certificates
```

### 2. Install the application

Download or clone this repository, then run these commands in its directory:

```sh
sudo install -d -m 755 /opt/dyndns-hcloud
sudo /usr/bin/python3 -m venv /opt/dyndns-hcloud/venv
sudo /opt/dyndns-hcloud/venv/bin/python -m pip install .
```

The `venv` command creates a separate
place for this service's libraries under `/opt/dyndns-hcloud`; it still uses that
Python interpreter. `pip install .` installs the application from the current
directory (`.`) and its dependencies there. Nothing needs to be activated in your
shell; systemd uses the full path automatically.

This follows the Python installation guidance for
[Ubuntu](https://ubuntu.com/developers/docs/tutorials/python-use/) and
[Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html#use-python-on-a-raspberry-pi),
which keep pip-installed libraries separate from OS-managed Python packages.

### 3. Create the configuration file

From the repository directory, copy the example configuration:

```sh
sudo mkdir -p /etc/dyndns-hcloud
sudo cp --update=none config.example.toml /etc/dyndns-hcloud/config.toml
sudo chown root:root /etc/dyndns-hcloud/config.toml
sudo chmod 600 /etc/dyndns-hcloud/config.toml
```

The configuration is stored at `/etc/dyndns-hcloud/config.toml`. The copy command
keeps an existing configuration intact, and mode 600 protects its credentials.

Edit the configuration with:

```sh
sudoedit /etc/dyndns-hcloud/config.toml
```

Enter your domain, Hetzner API token, and a separate username and password for
DynDNS. Use letters, digits, `-`, and `_` for the DynDNS credentials
so they work in the update URL. Keep the Hetzner token on the service host.

By default, your domain (for example, `example.com`) points to the router's IPv4
and IPv6 addresses. To give a device its own subdomain, edit the `[[records]]`
examples with its name and Ethernet MAC address. Remove these entries if you only
want to update the root domain (`example.com`).

Device IPv6 addresses are calculated from the LAN prefix and MAC. The device must
use a matching EUI-64 address; see [IPv6 client addresses](#ipv6-client-addresses).

### 4. Start the service

The default configuration listens on all IPv4 and IPv6 interfaces:

```toml
host = "*"
```

You can instead specify a particular LAN IPv4 or IPv6 address to listen only there. For a reverse
proxy on the same host, use `127.0.0.1` to accept only local IPv4 connections.

```sh
sudo /opt/dyndns-hcloud/venv/bin/python -m dyndns_hcloud --config /etc/dyndns-hcloud/config.toml --check-config
sudo cp deploy/dyndns-hcloud.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dyndns-hcloud
sudo systemctl status dyndns-hcloud
```

Run these commands from the repository directory. The service starts immediately
and automatically at boot, under its own service account. With the default port,
it is reachable at
`http://raspberrypi.fritz.box:8080` if that is your Pi's local hostname.
After configuration changes, run `sudo systemctl restart dyndns-hcloud`.

### 5. Configure the FRITZ!Box

Open **Internet → Freigaben / Permit Access → DynDNS** and fill in the form from
top to bottom:

1. **DynDNS aktiv:** enable DynDNS. If your FRITZ!OS version shows a provider
   selection, choose a custom provider.
2. **Update-URL:** paste the following URL as one line. Replace
   `raspberrypi.fritz.box` with your service host's local hostname or LAN IP address
   if different. Keep the placeholders, including their angle brackets:

   ```text
   http://raspberrypi.fritz.box:8080/nic/update?username=<username>&password=<pass>&hostname=<domain>&myip=<ipaddr>&myipv6=<ip6addr>&ip6prefix=<ip6lanprefix>
   ```

3. **Domainnamen:** enter the domain you set as `zone` under `[hetzner]` in
   `/etc/dyndns-hcloud/config.toml`, for example `example.com`.
4. **Benutzername:** enter the `username` you set under `[server]` in
   `/etc/dyndns-hcloud/config.toml`.
5. **Kennwort:** enter the `password` you set under `[server]` in
   `/etc/dyndns-hcloud/config.toml`. Enter the credential values without the TOML quotation marks.

Save the settings. The FRITZ!Box replaces the URL placeholders with the values
from these fields and its current addresses when sending an update.

HTTP sends the DynDNS credentials unencrypted, so use this setup on a trusted LAN.
The service's outgoing calls to Hetzner still use HTTPS.

The FRITZ!Box can now send address changes to the service. DNS updates do not open
firewall ports: reaching a device also requires the appropriate router and device
firewall rules, and port forwarding for IPv4.

## Advanced

### Configuration options

One service configuration manages one router and one existing primary DNS zone.
The zone must be delegated to Hetzner's authoritative nameservers. This service
uses the Cloud DNS API; legacy `dns.hetzner.com` zones must first be migrated to
Hetzner Console.

See [config.example.toml](config.example.toml) for a complete example.

The **root domain** is the domain itself, such as `example.com`, without a
subdomain such as `nas`. Its settings are in `[apex]` (the DNS term for this is
"zone apex"). By default, `example.com` resolves to the router's current IPv4
and IPv6 addresses, updated whenever the FRITZ!Box sends an update. This can be
disabled by setting `ipv4 = false` or `ipv6 = false` in `[apex]` for the respective
address family.

| Setting | Default | Purpose |
| --- | --- | --- |
| `server.host` / `server.port` | `*` / `8080` | Listen on all IPv4 and IPv6 interfaces |
| `hetzner.ttl` | `300` | DNS cache lifetime in seconds |
| `apex.ipv4` | `true` | Update `example.com` to resolve to the router's current IPv4 address (A record) |
| `apex.ipv6` | `true` | Update `example.com` to resolve to the router's own current IPv6 address (AAAA record) |
| `records[].ipv4` | `false` | Also point this client's A record to the router; configure port forwarding on the router to reach the client via IPv4 |
| `records[].subnet_id` | `0` | Select a LAN /64 within a larger IPv6 prefix |

Client names are relative to the zone: `nas` means `nas.example.com`, and
`home.server` means `home.server.example.com`. Each client gets a MAC-derived
AAAA record. The root domain needs no MAC address. To assign the
root domain to a MAC-based client instead, disable both `[apex]` options and add a client
named `@`.

**The service replaces each managed A/AAAA record set with a single address.**
Use dedicated names if you have existing records with multiple addresses.
Unmanaged names and record types are untouched. Disabling an option or removing
a client leaves its existing DNS records in place. CNAME conflicts cause the
callback to fail before any writes.

Validate the configuration without starting the server or making API calls:

```sh
sudo /opt/dyndns-hcloud/venv/bin/python -m dyndns_hcloud --config /etc/dyndns-hcloud/config.toml --check-config
```

Unknown fields and invalid configuration values are rejected at startup.

### IPv6 client addresses

The router's own IPv6 address (`<ip6addr>`) updates the root domain's AAAA record. The LAN
prefix (`<ip6lanprefix>`) is used only to calculate client addresses.

For example, prefix `2001:db8:1:2::/64` and MAC `00:11:22:33:44:55` produce
`2001:db8:1:2:211:22ff:fe33:4455`. This uses modified EUI-64: insert `ff:fe` and flip
the MAC's universal/local bit. Verify that the device actually has this address.
Privacy addresses, stable opaque addresses (RFC 7217), and DHCPv6 addresses cannot
be inferred from a MAC.

A bare prefix address is interpreted as `/64`. An explicit larger network such
as `2001:db8:1234:ab00::/56` is also accepted: `subnet_id = 42` selects
`2001:db8:1234:ab2a::/64`. This must match the LAN advertised by your router.
For `/64` input, `subnet_id` must be zero. Prefixes with host bits set or prefix
lengths greater than 64 are rejected.

Private or CGNAT IPv4 addresses do not provide direct public IPv4 reachability.

### HTTPS setup

HTTPS is optional for a trusted LAN deployment. For callbacks over the internet
or another untrusted network, put an HTTPS reverse proxy with a trusted certificate
in front of the service. With the proxy on the same host, use
`server.host = "127.0.0.1"` and expose only the proxy to the internet.

Use this update URL with your proxy's domain:

```text
https://updates.example.net/nic/update?username=<username>&password=<pass>&hostname=<domain>&myip=<ipaddr>&myipv6=<ip6addr>&ip6prefix=<ip6lanprefix>
```

For Caddy, use [deploy/Caddyfile](deploy/Caddyfile): replace the example domain
and point that domain's DNS to the service host. If hosting outside your home
network, a server with stable connectivity avoids depending on the changing home
address for updates. A local deployment can use its LAN hostname or address.

The callback URL contains credentials. Disable query-string logging at your
proxy and any upstream proxies. The Caddy example omits access logging, and the
application does not log request URLs or credentials. Clients that support HTTP
Basic authentication can use it instead of query credentials.

### Run automatically with systemd

The [systemd unit](deploy/dyndns-hcloud.service) runs the installed application
using `/opt/dyndns-hcloud/venv/bin/python`. The `-m dyndns_hcloud` argument tells
Python to find and run that package; the downloaded repository is not needed
while the service runs.

The unit reads `/etc/dyndns-hcloud/config.toml`, installed in the quick start.
It uses `DynamicUser` and systemd credentials to provide a private readable copy
to the service. The application runs without root privileges. The quick start
installs and enables the unit; use these commands to manage it:

```sh
sudo systemctl restart dyndns-hcloud
sudo systemctl stop dyndns-hcloud
sudo journalctl -u dyndns-hcloud -f
```

Run one process/instance per zone. An overlapping callback receives a temporary
failure while an update is running.

To update the application, download the new source and run these commands from
its directory. Your configuration in `/etc` is preserved:

```sh
sudo systemctl stop dyndns-hcloud
sudo /opt/dyndns-hcloud/venv/bin/python -m pip install --upgrade .
sudo cp deploy/dyndns-hcloud.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start dyndns-hcloud
```

### Callback behavior and troubleshooting

| Parameter | FRITZ!Box placeholder | Updates |
| --- | --- | --- |
| `myip` | `<ipaddr>` | Root domain's A record and clients with IPv4 enabled |
| `myipv6` | `<ip6addr>` | Root domain's AAAA record |
| `ip6prefix` | `<ip6lanprefix>` | Client AAAA records |

These parameters may be sent independently. Missing or empty values leave the
corresponding records unchanged; at least one must be supplied. Nonempty invalid
values reject the entire callback before any DNS API calls. The `hostname` must
identify the zone or a configured client FQDN; each accepted callback updates all
configured names for the supplied addresses. HEAD/POST requests never update DNS.
No address is inferred from the HTTP source IP.

| Response | Meaning |
| --- | --- |
| `good` (200) | Requested record/TTL changes completed at the API |
| `nochg` (200) | Nothing needed changing |
| `badauth` (401) | Missing or invalid credentials |
| `nohost` (400) | Hostname is outside the configured names |
| `notfqdn` (400) | Invalid, duplicate, or missing address parameters |
| `911` (503) | API failure, failed/timed-out action, or update already running |

The service checks Hetzner on every callback and skips unchanged records. Updates
are not transactional across record sets: a failure can leave some records updated,
and a later callback reconciles the remaining changes. There is no background retry
queue or persistent address cache.

API completion does not mean every resolver has refreshed its cache; the TTL
controls normal caching. API calls have a 10-second timeout, and action polling is
limited to 30 attempts per change. Allow sufficient proxy timeout for sequential
updates if you configure many records.

### Development and references

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
```

Tests cover address calculation, configuration, authentication, callback handling,
and the real `hcloud` client against mocked HTTP responses. They never change live
DNS records.

- [FRITZ!Box placeholders](https://fritz.com/en/apps/knowledge-base/fritz-box-7690/30_Setting-up-dynamic-DNS-in-the-FRITZ-Box)
- [Hetzner zone and RRSet client](https://hcloud-python.readthedocs.io/en/latest/api.clients.zones.html)
- [Modified EUI-64: RFC 4291, Appendix A](https://www.rfc-editor.org/rfc/rfc4291#appendix-A)
