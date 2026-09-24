# OS Aliaser for OPNsense

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD--2--Clause-blue.svg)](LICENSE)
[![OPNsense](https://img.shields.io/badge/OPNsense-24.7+-orange.svg)](https://opnsense.org/)

A smart firewall alias management plugin for OPNsense. Monitors DNS hostnames
and URL feeds, then syncs resolved IPs into pf tables in real-time using
atomic `pfctl -T replace` — no filter reload, no dropped connections.

Supports **composite watchers** that merge multiple DNS hostnames, static
IPs/CIDRs, and existing alias tables into a single target — with built-in
health monitoring, empty-table alerts, and change history.

## Why This Plugin?

OPNsense's built-in alias resolution has well-documented limitations
([#2162](https://github.com/opnsense/core/issues/2162),
[#1396](https://github.com/opnsense/core/issues/1396),
[#3737](https://github.com/opnsense/core/issues/3737)):

| | OPNsense Built-in | Aliaser |
|---|---|---|
| Update speed | ~300s (cron + jitter) | 10s–3600s (configurable per watcher) |
| Composite sources | No (one source per alias) | DNS + static IPs + other aliases merged |
| Nested alias updates | 1-min cron delay per level | Instant — reads live pf tables |
| Failure handling | Silent — no logs, no alerts | Logs failures, tracks consecutive errors |
| Empty table detection | None ([#3737](https://github.com/opnsense/core/issues/3737)) | Alert when table goes from N→0 |
| Table size warnings | None ([#4669](https://github.com/opnsense/core/issues/4669)) | Configurable threshold alerts |
| Change tracking | None ([#6565](https://github.com/opnsense/core/issues/6565)) | Full diff history (last 20 changes) |
| Visibility | Manual `pfctl -T show` per alias | Live dashboard with service controls |
| Management | Cron + settings scattered across UI | One page, self-managed daemon |

## How It Works

```
Aliaser Daemon (Python)
  |
  |-- DNS Watcher: resolve office.example.com every 15s
  |     --> pfctl -t Office_IPs -T replace 1.2.3.4
  |
  |-- Composite Watcher "My_Access":
  |     DNS: office.example.com, home.ddns.net
  |     + Static: 192.168.0.0/16, 10.0.0.0/8
  |     + Include: Public_IP (read from its pf table)
  |     --> pfctl -t My_Access -T replace [all merged IPs]
  |
  |-- URL Watcher: fetch cloudflare-ips.txt every 1h
  |     --> pfctl -t CF_IPs -T replace 103.21.244.0/22 ...
  |
  --> All changes logged to syslog with diff history
  --> Empty table alerts, size threshold warnings
```

1. Configure watchers in the plugin UI (Services > Aliaser > Watchers)
2. Each watcher monitors a DNS hostname or URL feed on its own interval
3. Changes are applied atomically via `pfctl -T replace` (no filter reload)
4. The Status dashboard shows live state, current IPs, and error history

## Features

- **DNS watchers** — track FQDN changes with configurable intervals (10s–3600s)
- **Direct DNS queries** — optionally query a specific DNS server per watcher, bypassing the local cache; re-checks as soon as the record's TTL expires
- **URL feed watchers** — sync IP lists from URLs (threat feeds, cloud provider ranges)
- **Composite watchers** — merge multiple DNS hostnames, static IPs/CIDRs, and existing alias tables into a single target
- **Atomic updates** — `pfctl -T replace` only, never triggers filter reload
- **Survives reboots** — tables are refilled from the last known state as soon as the daemon starts, before the first lookup finishes
- **Fail-closed** — if DNS or a feed fails, the last good result is kept (up to 24h) instead of shrinking the table
- **Parallel lookups** — a slow feed never delays other watchers; nested aliases re-merge the moment an included table changes
- **Change detection** — only updates pf tables when content actually changes
- **Health monitoring** — empty table alerts, configurable size threshold warnings
- **Change history** — per-watcher diff log (last 20 changes with added/removed IPs)
- **Failure alerting** — logs DNS/fetch failures, tracks consecutive error count
- **Status dashboard** — live view with service controls (Start/Stop/Restart), current IPs, timestamps, alerts
- **Manual refresh** — "Refresh Now" button per watcher for instant updates
- **Alias picker** — browse and select existing aliases, or create new External aliases inline
- **IPv4 + IPv6** — dual-stack DNS resolution (A + AAAA records)
- **Self-managed daemon** — no cron configuration needed, just set interval and go
- **HA sync** — configuration syncs between OPNsense cluster nodes

## Installation

```sh
# SSH to OPNsense as root
git clone https://github.com/DaneHou/os-aliaser.git ~/os-aliaser
cd ~/os-aliaser
make install
```

Hard-refresh your browser (Ctrl+Shift+R) after install, then go to
**Services > Aliaser**.

## Quick Start

1. **Create an External alias** — Firewall > Aliases, click +, set type to
   **External (Advanced)**, give it a name like `Office_IP`, save and apply.
   (Or create one directly from the Aliaser watcher dialog.)

2. **Add a watcher** — Services > Aliaser > Watchers, click +:
   - **Type:** DNS Hostname (or URL Table)
   - **Hostnames:** `office.example.com` (comma-separated for multiple)
   - **Static IPs/CIDRs:** (optional) e.g., `10.0.0.0/8` — always included
   - **Include Aliases:** (optional) merge IPs from other pf tables
   - **Target Alias:** click the alias picker button to select `Office_IP`
   - **Interval:** `30` (seconds)

3. **Enable and Apply** — check "Enable Aliaser" at the top, click Apply

4. **Verify** — go to Services > Aliaser > Status to see the resolved IPs
   and update timestamps

> **Important:** Use **External (Advanced)** type aliases for watchers.
> Other alias types (Host, Network, etc.) are also managed by OPNsense's
> built-in `update_tables.py`, which will conflict with the Aliaser daemon.

## Use Cases

### Dynamic DNS Tracking
Track a remote office or home IP that uses DDNS:
- Watcher: DNS → `home.ddns.net` → `Home_IP` alias (interval: 15s)
- Firewall rule: allow `Home_IP` to access internal services

### Cloud Provider IP Allowlisting
Keep Cloudflare, AWS, or Azure IP ranges up to date:
- Watcher: URL → `https://www.cloudflare.com/ips-v4` → `CF_IPv4` alias (interval: 1h)
- Firewall rule: only allow `CF_IPv4` to reach your web server

### Composite Access Control
Combine multiple sources into one alias for a firewall rule:
- Watcher: DNS → `office.example.com, home.ddns.net`
  + Static: `192.168.1.0/24`
  + Include: `VPN_Clients` (another alias)
  → `Trusted_Sources` alias (interval: 30s)
- Firewall rule: allow `Trusted_Sources` to access management interfaces

### Threat Feed Blocklisting
Block known-bad IPs from a threat intelligence feed:
- Watcher: URL → `https://example.com/blocklist.txt` → `Blocklist` alias (interval: 30m)
- Firewall rule: block traffic from `Blocklist`

## Alerting (Monit)

The status page only helps if someone looks at it. To get an email when a
watcher keeps failing, a table goes empty, or the daemon dies, let OPNsense's
built-in Monit run the health check:

```sh
/usr/local/opnsense/scripts/OPNsense/Aliaser/aliaserd.py health
# OK: 3 watcher(s) healthy                                   (exit 0)
# office: 3 failures in a row: no results from office.example.com   (exit 1)
```

It reports: daemon not running, a source failing 3+ times in a row, empty-table
and size-threshold alerts, and watchers not checked for 3× their interval.

1. **Services > Monit > Settings > General / Alert Settings** — enable Monit,
   set up your mail server and an alert recipient (skip if already done).
2. **Service Tests Settings** — add a test: *Name* `AliaserHealth`,
   *Type* `Program Status`, *Condition* `status != 0`, *Action* `Alert`.
3. **Service Settings** — add a service: *Name* `aliaser`, *Type* `Custom`,
   *Path* `/usr/local/opnsense/scripts/OPNsense/Aliaser/aliaserd.py health`,
   *Tests* `AliaserHealth`. Save and apply.

The alert email contains the command's output, i.e. which watcher failed and why.
(Menu and field names are from OPNsense 24.7/26.1 and may differ slightly between versions.)

## Updating

```sh
cd ~/os-aliaser
git pull
make install
```

The daemon restarts automatically after install.

## Uninstalling

```sh
cd ~/os-aliaser
make uninstall
```

## Architecture

```
src/
├── etc/
│   ├── inc/plugins.inc.d/aliaser.inc      # Plugin hooks (services, syslog, boot, HA)
│   └── newsyslog.conf.d/aliaser.conf      # Log rotation
└── opnsense/
    ├── mvc/app/
    │   ├── controllers/OPNsense/Aliaser/  # UI + API controllers
    │   │   ├── IndexController.php        #   Watcher config page
    │   │   ├── StatusController.php       #   Status dashboard page
    │   │   ├── LogController.php          #   Log viewer page
    │   │   └── Api/                       #   REST API endpoints
    │   ├── models/OPNsense/Aliaser/       # Data model, menu, ACL
    │   └── views/OPNsense/Aliaser/        # Volt templates (3 pages)
    ├── scripts/OPNsense/Aliaser/
    │   └── aliaserd.py                    # Daemon (Python, stdlib only)
    └── service/conf/actions.d/
        └── actions_aliaser.conf           # configd action definitions
tests/                                     # pytest suite (fake pfctl, no OPNsense needed)
.github/workflows/ci.yml                   # CI: tests on Python 3.9/3.11, PHP + XML lint
```

## Requirements

- OPNsense 24.7+ (tested on 26.1)
- Python 3.9+ (included with OPNsense)
- No additional packages or dependencies

## Documentation

- [Changelog](CHANGELOG.md) — version history
- [Contributing](CONTRIBUTING.md) — development setup, code style and tests
- [Security](SECURITY.md) — vulnerability reporting and security design

## Known Limitations

- Target aliases must be **External (Advanced)** type to avoid conflicts with
  OPNsense's built-in alias resolution
- DNS resolution uses the system resolver (not a dedicated DNS library), so it
  follows system DNS settings and caching
- URL feed parsing expects one IP or CIDR per line (lines starting with `#` or
  `;` are ignored)
- The daemon runs as root (standard for OPNsense plugins)

## License

BSD-2-Clause
