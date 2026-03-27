# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

os-aliaser is an OPNsense plugin that manages firewall alias tables via a Python daemon. It resolves DNS hostnames, fetches URL feeds, and merges multiple sources into pf tables using atomic `pfctl -T replace` operations — faster and more reliable than OPNsense's built-in alias resolution.

## Build & Deploy

Requires an OPNsense 24.7+ VM with SSH access. All commands run as root on the OPNsense box.

```sh
make install                          # Full install: copy files + activate caches
make install-plugin && make activate  # Iterative dev (same thing, explicit steps)
make uninstall                        # Remove plugin completely
```

After install, hard-refresh browser (Ctrl+Shift+R) to pick up menu changes.

## Debugging

```sh
configctl aliaser status                                              # Daemon status via configd
/usr/local/opnsense/scripts/OPNsense/Aliaser/aliaserd.py status      # Direct daemon status
clog /var/log/system/latest.log | grep aliaserd                       # Syslog entries
pfctl -t <AliasName> -T show                                          # Inspect a pf table
```

State is cached at `/var/run/aliaser/state.json`. Config lives in `/conf/config.xml` (OPNsense standard).

## Testing

No automated tests. Manual verification on an OPNsense VM — see CONTRIBUTING.md for the full checklist. Key checks: daemon starts, status page shows resolved IPs, refresh button works, composite sources merge, start/stop/restart buttons work, clean uninstall.

## Architecture

```
src/
├── etc/inc/plugins.inc.d/aliaser.inc          # Plugin hooks (boot, services, syslog, HA sync)
├── opnsense/scripts/OPNsense/Aliaser/
│   └── aliaserd.py                            # Python daemon (~600 lines, stdlib only)
├── opnsense/mvc/app/
│   ├── controllers/OPNsense/Aliaser/
│   │   ├── IndexController.php                # Watcher config page
│   │   ├── StatusController.php               # Status dashboard page
│   │   ├── LogController.php                  # Log viewer page
│   │   └── Api/
│   │       ├── SettingsController.php         # General settings API
│   │       ├── WatcherController.php          # Watcher CRUD API
│   │       ├── ServiceController.php          # Start/stop/restart API
│   │       └── StatusController.php           # Daemon status API
│   ├── models/OPNsense/Aliaser/
│   │   ├── Aliaser.xml                        # Config schema (field types, validation)
│   │   ├── ACL/ACL.xml                        # Access control
│   │   └── Menu/Menu.xml                      # Navigation menu
│   └── views/OPNsense/Aliaser/
│       ├── index.volt                         # Watcher config UI
│       ├── status.volt                        # Status dashboard UI
│       └── log.volt                           # Log viewer UI
└── opnsense/service/conf/actions.d/
    └── actions_aliaser.conf                   # configd action definitions
```

**Data flow:** OPNsense config XML -> aliaserd.py reads watchers -> resolves DNS/URLs + merges static IPs + includes other pf tables -> atomic `pfctl -T replace` -> persists state to JSON -> Web UI queries status via API controllers -> configd actions bridge UI to daemon.

**Key design decisions:**
- Single-threaded Python daemon with per-watcher timers (no cron, no threads)
- Zero external Python dependencies (stdlib only: socket, urllib, xml.etree, subprocess)
- Atomic pf table updates only (`pfctl -T replace`), never filter reloads
- Change history tracked per watcher (last 20 changes in state.json)
- Composite watchers merge DNS + static entries + other alias tables in one update

## Code Conventions

**Platform:** This is FreeBSD/OPNsense — use `sh`/`csh` syntax in scripts, not bash-isms. Paths are under `/usr/local/` (not `/etc/`). Volt template cache must be cleared after template changes.

**PHP:** 4-space indent, OPNsense MVC patterns, Phalcon conventions (lowercase 'c' in `controllerName`). API controllers extend `ApiMutableModelControllerBase` or `ApiControllerBase`.

**Python:** PEP 8, 4-space indent, Python 3.9+ target. Use `syslog` for logging (not print). No external deps.

**JS in Volt templates:** jQuery + UIBootgrid patterns, OPNsense helpers (`mapDataToFormUI`, `SimpleActionButton`, etc.). CDN libraries are NOT available — bundle all JS/CSS locally.

**Branch naming:** `fix/`, `feat/`, `docs/`, `refactor/` prefixes.
