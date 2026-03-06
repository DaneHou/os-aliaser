# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-03-05

### Composite Watchers

- **Multiple hostnames** — DNS watchers now accept comma-separated FQDNs (e.g., `office.example.com, home.ddns.net`), all resolved and merged into the target alias
- **Static IPs/CIDRs** — optional static entries always included in the alias (e.g., `10.0.0.0/8, 192.168.1.0/24`)
- **Include aliases** — merge IPs from other existing pf tables into the target (reads live table contents, no cron delay)
- All three sources merge before `pfctl -T replace` — a single watcher can combine DNS, static, and alias sources
- Backwards compatible: existing single-hostname watchers continue to work unchanged

### Alias Health Monitoring

- **Empty table alerts** — warning when a table goes from N entries to 0 (addresses [#3737](https://github.com/opnsense/core/issues/3737), [#1396](https://github.com/opnsense/core/issues/1396))
- **Table size threshold** — configurable max entry count in General settings; warns when exceeded (addresses [#4669](https://github.com/opnsense/core/issues/4669), [#1555](https://github.com/opnsense/core/issues/1555))
- **Change history** — per-watcher log of last 20 changes with timestamps, added/removed IPs, and entry counts (addresses [#6565](https://github.com/opnsense/core/issues/6565))
- Alerts shown as color-coded badges on the status dashboard

### Status Page Enhancements

- **Service controls** — Start, Stop, Restart buttons directly on the status page
- **Sources summary** — shows all composite sources (DNS, static, include) per watcher
- **Expandable change history** — click to view full diff log with added/removed IPs

## [1.0.0] - 2026-03-05

### Initial Release

- DNS watchers with configurable check intervals (10s–3600s)
- URL feed watchers for syncing IP lists from remote URLs
- Atomic pf table updates via `pfctl -T replace` (no filter reload)
- Change detection — only updates when resolved IPs differ from current table
- Failure tracking with consecutive error counter and syslog alerts
- Self-managed Python daemon (no cron configuration needed)
- Live status dashboard with per-watcher cards showing:
  - Current IPs in the pf table
  - Last check and last change timestamps
  - Error status with color-coded health indicators
  - "Refresh Now" button for instant manual updates
- Alias picker in watcher edit dialog — browse existing aliases by type
- Inline External alias creation from the watcher dialog
- IPv4 and IPv6 dual-stack DNS resolution
- OPNsense MVC integration: UI under Services > Aliaser, REST API, configd
- Auto-start on boot via plugin hook
- HA sync support for OPNsense cluster configurations
- Syslog integration and log rotation
