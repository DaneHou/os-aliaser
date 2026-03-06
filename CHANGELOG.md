# Changelog

All notable changes to this project will be documented in this file.

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
