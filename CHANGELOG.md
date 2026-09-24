# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed

- **Change history no longer disappears.** The daemon and "Refresh Now" each kept
  their own copy of the state and overwrote each other's history. All state
  writes now go through a lock and are atomic. State moved from `/var/run/aliaser`
  (wiped at boot) to `/var/db/aliaser`; existing history is migrated.
- A DNS or feed failure (including an empty feed) no longer shrinks the table;
  the source's last good result is kept for up to 24 hours.
- Include loops (A includes B, B includes A) no longer make IPs impossible to remove.
- One watcher with a bad interval no longer disables all watchers.
- Feed failures now show an error message on the status page.
- `stop` could mistake a running daemon for a dead one (`ps` output truncated to
  80 columns) and orphan it; `start` could hang a caller capturing its output.
- `stop` shuts the daemon down gracefully instead of always escalating to SIGKILL,
  never signals an unrelated process that reused a stale PID, and two racing
  `start` calls can no longer leave two daemons running.

### Added

- **Tables survive reboots**: the daemon refills empty tables from the last known state
  on start, instead of leaving them empty until the first lookup finishes.
- **Parallel lookups**: a slow or timing-out feed no longer delays other watchers.
- **Instant nested updates**: when a table changes, watchers that include it re-merge
  immediately instead of on their own interval.
- **TTL-aware DNS**: watchers with a custom DNS server re-check as soon as the record's
  TTL expires (never later than their interval). `dnspython` is no longer needed.
- **`aliaserd.py health`** for Monit alerting (see README).
- Automated tests (`tests/`, pytest with a fake pfctl) and GitHub Actions CI.

### Changed

- `logLevel` now takes effect (Warning, the default, still logs table changes).
- `defaultInterval` now pre-fills new watchers and applies when a watcher's interval is empty.
- `make install` restarts a running daemon so upgrades take effect.

### Security

- Feed and static entries are validated as IPs/CIDRs and written to `pfctl`
  via a file, so a malicious feed can no longer inject `pfctl` options.
- Feeds larger than 16 MB are rejected.
- "Refresh Now" validates the UUID and passes it to configd escaped.
- Stored XSS fixed on the status, watchers and log pages; the log page only
  shows lines from the `aliaserd` process.
- Watchers can no longer target OPNsense's built-in tables (`bogons`, `sshlockout`, `__*`, ...).
- The Status privilege no longer grants service control or alias creation.

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
