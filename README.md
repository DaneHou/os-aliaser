# OS Aliaser for OPNsense

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD--2--Clause-blue.svg)](LICENSE)
[![OPNsense](https://img.shields.io/badge/OPNsense-24.7+-orange.svg)](https://opnsense.org/)

A smart firewall alias management plugin for OPNsense. Monitors DNS hostnames
and URL feeds, then syncs resolved IPs into pf tables in real-time using
atomic `pfctl -T replace` -- no filter reload, no dropped connections.

## Why This Plugin?

OPNsense's built-in alias resolution has well-documented limitations:

- **Slow updates** -- default 300-second resolve interval, cron-based with random jitter
- **Silent failures** -- DNS resolution errors are swallowed without notification
- **No change visibility** -- no dashboard showing what changed, when, or why
- **Stale entries** -- no TTL awareness, old IPs can linger in tables
- **URL table mystery** -- URL-based aliases stop updating silently with no diagnostics

Aliaser fixes all of these by running a lightweight daemon that manages alias
contents directly, with per-watcher intervals, change detection, failure
alerting, and a live status dashboard.

## How It Works

```
Aliaser Daemon (Python)
  |
  |-- DNS Watcher: resolve office.example.com every 15s
  |     --> pfctl -t Office_IPs -T replace 1.2.3.4
  |
  |-- DNS Watcher: resolve home.ddns.net every 10s
  |     --> pfctl -t Home_IPs -T replace 5.6.7.8
  |
  |-- URL Watcher: fetch threat-feed.txt every 3600s
  |     --> pfctl -t Blocklist -T replace -f /tmp/aliaser_feed.txt
  |
  --> All changes logged to syslog with before/after diff
```

1. Configure watchers in the plugin UI (Services > Aliaser)
2. Each watcher monitors a DNS hostname or URL feed
3. Changes are applied atomically via `pfctl -T replace` (no filter reload)
4. The status dashboard shows live state of all watched aliases

## Features

- **DNS watchers** -- track FQDN changes with configurable intervals (10s-3600s)
- **URL feed watchers** -- sync IP lists from URLs (threat feeds, cloud provider ranges)
- **Atomic updates** -- `pfctl -T replace` only, never triggers filter reload
- **Change detection** -- only updates when content actually changes
- **Failure alerting** -- logs DNS/fetch failures, tracks consecutive errors
- **Status dashboard** -- live view of all watchers, current IPs, last update time
- **Manual refresh** -- "Refresh Now" button per watcher for debugging
- **IPv4 + IPv6** -- dual-stack support for DNS watchers
- **Self-managed daemon** -- no cron configuration needed, just set interval and go

## Installation

```bash
# SSH to OPNsense as root
git clone https://github.com/DaneHou/os-aliaser.git ~/os-aliaser
cd ~/os-aliaser
make install
```

Then go to **Services > Aliaser**.

## Quick Start

1. **Create target aliases** -- go to Firewall > Aliases, create Host-type aliases
   for the IPs you want to manage (or use existing ones)
2. **Add a watcher** -- Services > Aliaser > Watchers, click +
   - Type: DNS or URL Feed
   - Target: hostname or URL
   - Alias: select the target alias
   - Interval: how often to check (seconds)
3. **Enable and Apply** -- enable the plugin, click Apply
4. **Check status** -- Services > Aliaser > Status dashboard

## Architecture

```
src/
  etc/inc/plugins.inc.d/aliaser.inc     # Plugin hooks (services, syslog, boot)
  opnsense/
    mvc/app/
      controllers/OPNsense/Aliaser/     # MVC controllers (UI + API)
      models/OPNsense/Aliaser/          # Data model, menu, ACL
      views/OPNsense/Aliaser/           # Volt templates
    scripts/OPNsense/Aliaser/           # Backend daemon + helpers
    service/conf/actions.d/             # configd action definitions
```

## Requirements

- OPNsense 24.7+ (tested on 26.1)
- Python 3.x (included with OPNsense)

## License

BSD-2-Clause
