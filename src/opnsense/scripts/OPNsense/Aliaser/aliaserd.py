#!/usr/local/bin/python3

"""
aliaserd.py -- Aliaser daemon for OPNsense.

A lightweight daemon that monitors DNS hostnames and URL feeds, then
atomically syncs resolved IPs into pf tables via pfctl -T replace.

Usage:
    aliaserd.py start       Start the daemon (daemonize)
    aliaserd.py stop        Stop the running daemon
    aliaserd.py restart     Restart the daemon
    aliaserd.py status      Print JSON status of all watchers
    aliaserd.py reconfigure Reload config and restart daemon
    aliaserd.py refresh UUID Force immediate refresh of a watcher

Architecture:
    - Reads watcher config from config.xml via OPNsense's XML API
    - Runs a single-threaded async event loop (select-based timer)
    - Each watcher has its own timer based on its configured interval
    - DNS resolution uses socket.getaddrinfo (supports A + AAAA)
    - URL fetching uses urllib (with timeout)
    - Table updates via: pfctl -t <alias> -T replace <ips...>
    - State cached in /var/run/aliaser/state.json
    - Logs to syslog facility 'aliaser'
"""

import json
import os
import signal
import socket
import subprocess
import sys
import syslog
import time
import urllib.request
import xml.etree.ElementTree as ET

PIDFILE = '/var/run/aliaser.pid'
STATEFILE = '/var/run/aliaser/state.json'
CONFIG_XML = '/conf/config.xml'
PFCTL = '/sbin/pfctl'

# ---------- Config parsing ----------

def read_config():
    """Parse watcher definitions from config.xml."""
    watchers = []
    try:
        tree = ET.parse(CONFIG_XML)
        root = tree.getroot()
        aliaser = root.find('.//OPNsense/Aliaser')
        if aliaser is None:
            return watchers, 'warn', 0

        general = aliaser.find('general')
        log_level = 'warn'
        max_table_entries = 0
        if general is not None:
            enabled = general.findtext('enabled', '0')
            if enabled != '1':
                return watchers, log_level, max_table_entries
            log_level = general.findtext('logLevel', 'warn')
            try:
                max_table_entries = int(general.findtext('maxTableEntries', '0'))
            except (ValueError, TypeError):
                max_table_entries = 0

        watcher_container = aliaser.find('watchers')
        if watcher_container is None:
            return watchers, log_level, max_table_entries

        for watcher_el in watcher_container:
            if watcher_el.tag != 'watcher':
                continue
            uuid = watcher_el.get('uuid', '')
            w = {
                'uuid': uuid,
                'enabled': watcher_el.findtext('enabled', '0'),
                'name': watcher_el.findtext('name', ''),
                'type': watcher_el.findtext('type', 'dns'),
                'hostname': watcher_el.findtext('hostname', ''),
                'hostnames': watcher_el.findtext('hostnames', ''),
                'url': watcher_el.findtext('url', ''),
                'staticEntries': watcher_el.findtext('staticEntries', ''),
                'includeAliases': watcher_el.findtext('includeAliases', ''),
                'alias': watcher_el.findtext('alias', ''),
                'interval': int(watcher_el.findtext('interval', '30')),
                'addressFamily': watcher_el.findtext('addressFamily', 'ipv4'),
                'description': watcher_el.findtext('description', ''),
            }
            if w['enabled'] == '1' and w['alias']:
                watchers.append(w)

        return watchers, log_level, max_table_entries
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f'aliaserd: config parse error: {e}')
        return watchers, 'warn', 0


# ---------- DNS resolution ----------

def resolve_dns(hostname, address_family='ipv4'):
    """Resolve a hostname to a sorted list of unique IPs."""
    ips = set()
    families = []
    if address_family in ('ipv4', 'both'):
        families.append(socket.AF_INET)
    if address_family in ('ipv6', 'both'):
        families.append(socket.AF_INET6)

    for af in families:
        try:
            results = socket.getaddrinfo(hostname, None, af, socket.SOCK_STREAM)
            for r in results:
                ips.add(r[4][0])
        except socket.gaierror:
            pass

    return sorted(ips)


# ---------- URL fetching ----------

def fetch_url(url, timeout=30):
    """Fetch a URL and parse one IP/CIDR per line."""
    ips = set()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OPNsense-Aliaser/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for line in resp.read().decode('utf-8', errors='ignore').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or line.startswith(';'):
                    continue
                # Basic validation: contains digits and dots/colons (IP or CIDR)
                if any(c.isdigit() for c in line) and ('.' in line or ':' in line):
                    ips.add(line)
    except Exception as e:
        syslog.syslog(syslog.LOG_WARNING, f'aliaserd: fetch error for {url}: {e}')
        return None  # None signals failure (distinct from empty set)
    return sorted(ips)


# ---------- pf table operations ----------

def pfctl_show(alias):
    """Get current IPs in a pf table."""
    try:
        result = subprocess.run(
            [PFCTL, '-t', alias, '-T', 'show'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    except Exception:
        return None


def pfctl_replace(alias, ips):
    """Atomically replace all IPs in a pf table."""
    if not ips:
        # Flush the table if empty
        try:
            subprocess.run(
                [PFCTL, '-t', alias, '-T', 'flush'],
                capture_output=True, timeout=5
            )
            return True
        except Exception:
            return False

    try:
        cmd = [PFCTL, '-t', alias, '-T', 'replace'] + list(ips)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f'aliaserd: pfctl replace failed for {alias}: {e}')
        return False


# ---------- State management ----------

def load_state():
    """Load cached watcher state from disk."""
    try:
        with open(STATEFILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    """Persist watcher state to disk."""
    os.makedirs(os.path.dirname(STATEFILE), exist_ok=True)
    with open(STATEFILE, 'w') as f:
        json.dump(state, f, indent=2)


# ---------- Watcher logic ----------

def check_watcher(watcher, state, max_table_entries=0):
    """
    Check a single watcher. Returns True if the pf table was updated.
    Updates state dict in-place.

    Composite merge:
      1. Primary source (DNS hostnames or URL) -> merged_ips
      2. staticEntries CSV -> add to merged_ips
      3. includeAliases -> read each pf table, add to merged_ips
      4. pfctl_replace(alias, sorted(merged_ips))
    """
    name = watcher['name']
    alias = watcher['alias']
    wtype = watcher['type']

    ws = state.setdefault(name, {
        'uuid': watcher['uuid'],
        'alias': alias,
        'type': wtype,
        'current_ips': [],
        'last_check': 0,
        'last_change': 0,
        'last_error': '',
        'consecutive_errors': 0,
        'history': [],
        'alerts': [],
    })
    # Ensure history/alerts keys exist for older state files
    ws.setdefault('history', [])
    ws.setdefault('alerts', [])

    merged_ips = set()
    primary_ok = False

    # Step 1: Primary source
    if wtype == 'dns':
        # Use hostnames (plural) first, fall back to hostname (legacy)
        hostnames_str = watcher.get('hostnames', '').strip()
        if hostnames_str:
            dns_hosts = [h.strip() for h in hostnames_str.split(',') if h.strip()]
        else:
            legacy = watcher.get('hostname', '').strip()
            dns_hosts = [legacy] if legacy else []

        if not dns_hosts and not watcher.get('staticEntries', '').strip() and not watcher.get('includeAliases', '').strip():
            return False

        af = watcher.get('addressFamily', 'ipv4')
        for hostname in dns_hosts:
            ips = resolve_dns(hostname, af)
            if ips:
                merged_ips.update(ips)
                primary_ok = True

        if dns_hosts and not primary_ok:
            ws['last_error'] = f'DNS resolution returned no results for {", ".join(dns_hosts)}'
            ws['consecutive_errors'] = ws.get('consecutive_errors', 0) + 1
            ws['last_check'] = time.time()
            syslog.syslog(syslog.LOG_WARNING,
                          f'aliaserd: [{name}] no DNS results for {", ".join(dns_hosts)} '
                          f'(errors: {ws["consecutive_errors"]})')
            # Don't return yet — static/include sources may still contribute

    elif wtype == 'urltable':
        url = watcher.get('url', '').strip()
        if url:
            result = fetch_url(url)
            if result is None:
                ws['consecutive_errors'] = ws.get('consecutive_errors', 0) + 1
                ws['last_check'] = time.time()
                # Don't return yet — static/include sources may still contribute
            elif result:
                merged_ips.update(result)
                primary_ok = True
        elif not watcher.get('staticEntries', '').strip() and not watcher.get('includeAliases', '').strip():
            return False

    # Step 2: Static entries
    static_str = watcher.get('staticEntries', '').strip()
    if static_str:
        for entry in static_str.split(','):
            entry = entry.strip()
            if entry:
                merged_ips.add(entry)

    # Step 3: Include aliases (read from their pf tables)
    include_str = watcher.get('includeAliases', '').strip()
    if include_str:
        for inc_alias in include_str.split(','):
            inc_alias = inc_alias.strip()
            if not inc_alias or inc_alias == alias:  # Skip self-reference
                continue
            inc_ips = pfctl_show(inc_alias)
            if inc_ips:
                merged_ips.update(inc_ips)
            else:
                syslog.syslog(syslog.LOG_WARNING,
                              f'aliaserd: [{name}] include alias {inc_alias} not accessible or empty')

    new_ips = sorted(merged_ips)

    # If nothing resolved from any source and no static/include, it's an error
    if not new_ips and not primary_ok and not static_str and not include_str:
        return False

    ws['last_check'] = time.time()
    if primary_ok or not (watcher.get('hostnames', '').strip() or watcher.get('hostname', '').strip() or watcher.get('url', '').strip()):
        ws['last_error'] = ''
        ws['consecutive_errors'] = 0

    # Compare with current table
    current_ips = pfctl_show(alias)
    if current_ips is None:
        syslog.syslog(syslog.LOG_WARNING,
                      f'aliaserd: [{name}] pf table {alias} does not exist or cannot be read')
        ws['last_error'] = f'pf table {alias} not accessible'
        return False

    if new_ips == current_ips:
        return False

    # Update the table
    old_count = len(current_ips)
    new_count = len(new_ips)

    if pfctl_replace(alias, new_ips):
        ws['current_ips'] = new_ips
        ws['last_change'] = time.time()
        syslog.syslog(syslog.LOG_NOTICE,
                      f'aliaserd: [{name}] updated {alias}: {old_count} -> {new_count} entries '
                      f'({", ".join(new_ips[:5])}{"..." if new_count > 5 else ""})')

        # Health monitoring: empty table alert
        alerts = []
        if new_count == 0 and old_count > 0:
            alert_msg = f'Table went from {old_count} entries to 0'
            syslog.syslog(syslog.LOG_WARNING, f'aliaserd: [{name}] ALERT: {alert_msg}')
            alerts.append({'type': 'empty', 'message': alert_msg, 'timestamp': time.time()})

        # Health monitoring: table size threshold
        if max_table_entries > 0 and new_count > max_table_entries:
            alert_msg = f'Table has {new_count} entries (threshold: {max_table_entries})'
            syslog.syslog(syslog.LOG_WARNING, f'aliaserd: [{name}] ALERT: {alert_msg}')
            alerts.append({'type': 'threshold', 'message': alert_msg, 'timestamp': time.time()})

        ws['alerts'] = alerts

        # Change history: record diff
        added = sorted(set(new_ips) - set(current_ips))
        removed = sorted(set(current_ips) - set(new_ips))
        history_entry = {
            'timestamp': time.time(),
            'old_count': old_count,
            'new_count': new_count,
            'added': added[:50],  # Cap to avoid bloated state
            'removed': removed[:50],
        }
        ws['history'].append(history_entry)
        ws['history'] = ws['history'][-20:]  # Keep last 20 changes

        return True
    return False


# ---------- Daemon loop ----------

def run_daemon():
    """Main daemon loop. Reads config, runs watchers on their intervals."""
    syslog.openlog('aliaserd', syslog.LOG_PID, syslog.LOG_LOCAL4)
    syslog.syslog(syslog.LOG_NOTICE, 'aliaserd: starting')

    # Write PID file
    os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
    with open(PIDFILE, 'w') as f:
        f.write(str(os.getpid()))

    state = load_state()
    running = True

    def handle_signal(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Track per-watcher last-run times
    last_run = {}

    while running:
        watchers, log_level, max_table_entries = read_config()
        if not watchers:
            time.sleep(10)
            continue

        now = time.time()
        next_wake = now + 10  # Default wake in 10s if nothing scheduled

        for w in watchers:
            name = w['name']
            interval = w['interval']
            last = last_run.get(name, 0)

            if now - last >= interval:
                try:
                    changed = check_watcher(w, state, max_table_entries)
                    if changed:
                        save_state(state)
                except Exception as e:
                    syslog.syslog(syslog.LOG_ERR,
                                  f'aliaserd: [{name}] unexpected error: {e}')
                last_run[name] = now

            # Calculate next wake time
            next_for_watcher = last_run.get(name, now) + interval
            if next_for_watcher < next_wake:
                next_wake = next_for_watcher

        # Save state periodically
        save_state(state)

        # Sleep until next watcher needs to run
        sleep_time = max(1, next_wake - time.time())
        time.sleep(min(sleep_time, 10))  # Cap at 10s for responsiveness

    # Cleanup
    syslog.syslog(syslog.LOG_NOTICE, 'aliaserd: stopping')
    try:
        os.unlink(PIDFILE)
    except FileNotFoundError:
        pass


# ---------- Daemon control ----------

def get_pid():
    """Read PID from pidfile, return None if not running."""
    try:
        with open(PIDFILE, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # Check if process exists
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def cmd_start():
    if get_pid():
        print('aliaserd already running')
        return
    # Fork to background
    pid = os.fork()
    if pid > 0:
        return  # Parent exits
    os.setsid()
    pid = os.fork()
    if pid > 0:
        os._exit(0)
    # Redirect stdio
    sys.stdin.close()
    sys.stdout = open('/dev/null', 'w')
    sys.stderr = open('/dev/null', 'w')
    run_daemon()


def cmd_stop():
    pid = get_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):  # Wait up to 5s
            time.sleep(0.1)
            if not get_pid():
                return
        os.kill(pid, signal.SIGKILL)
    try:
        os.unlink(PIDFILE)
    except FileNotFoundError:
        pass


def cmd_restart():
    cmd_stop()
    time.sleep(0.5)
    cmd_start()


def cmd_status():
    """Print JSON status for the API."""
    state = load_state()
    pid = get_pid()

    output = {
        'daemon': {
            'running': pid is not None,
            'pid': pid,
        },
        'watchers': {},
    }

    watchers, _, max_table_entries = read_config()
    for w in watchers:
        name = w['name']
        ws = state.get(name, {})
        # Also get live table content
        current_table = pfctl_show(w['alias'])
        ip_count = len(current_table) if current_table else 0

        # Determine target display
        if w['type'] == 'dns':
            target = w.get('hostnames', '').strip() or w.get('hostname', '')
        else:
            target = w.get('url', '')

        # Build sources summary
        sources = []
        if target:
            sources.append(w['type'].upper() + ': ' + target)
        if w.get('staticEntries', '').strip():
            sources.append('Static: ' + w['staticEntries'].strip())
        if w.get('includeAliases', '').strip():
            sources.append('Include: ' + w['includeAliases'].strip())

        # Compute active alerts
        alerts = ws.get('alerts', [])
        if max_table_entries > 0 and ip_count > max_table_entries:
            alerts = [a for a in alerts if a.get('type') != 'threshold']
            alerts.append({
                'type': 'threshold',
                'message': f'Table has {ip_count} entries (threshold: {max_table_entries})',
                'timestamp': time.time(),
            })

        output['watchers'][name] = {
            'uuid': w['uuid'],
            'type': w['type'],
            'target': target,
            'sources': sources,
            'alias': w['alias'],
            'interval': w['interval'],
            'staticEntries': w.get('staticEntries', ''),
            'includeAliases': w.get('includeAliases', ''),
            'current_ips': current_table or [],
            'ip_count': ip_count,
            'last_check': ws.get('last_check', 0),
            'last_change': ws.get('last_change', 0),
            'last_error': ws.get('last_error', ''),
            'consecutive_errors': ws.get('consecutive_errors', 0),
            'alerts': alerts,
            'history': ws.get('history', []),
        }

    print(json.dumps(output, indent=2))


def cmd_reconfigure():
    """Restart the daemon to pick up new config."""
    cmd_stop()
    time.sleep(0.5)

    watchers, _, _ = read_config()
    if not watchers:
        print(json.dumps({'status': 'ok', 'message': 'no watchers configured'}))
        return

    cmd_start()
    print(json.dumps({'status': 'ok', 'message': f'restarted with {len(watchers)} watchers'}))


def cmd_refresh(uuid):
    """Force immediate refresh of a single watcher by UUID."""
    watchers, _, max_table_entries = read_config()
    state = load_state()

    for w in watchers:
        if w['uuid'] == uuid:
            changed = check_watcher(w, state, max_table_entries)
            save_state(state)
            print(json.dumps({
                'status': 'ok',
                'watcher': w['name'],
                'changed': changed,
                'current_ips': state.get(w['name'], {}).get('current_ips', []),
            }))
            return

    print(json.dumps({'status': 'error', 'message': f'watcher {uuid} not found'}))


# ---------- Entry point ----------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} start|stop|restart|status|reconfigure|refresh [uuid]')
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'start':
        cmd_start()
    elif cmd == 'stop':
        cmd_stop()
    elif cmd == 'restart':
        cmd_restart()
    elif cmd == 'status':
        cmd_status()
    elif cmd == 'reconfigure':
        cmd_reconfigure()
    elif cmd == 'refresh' and len(sys.argv) > 2:
        cmd_refresh(sys.argv[2])
    else:
        print(f'Unknown command: {cmd}')
        sys.exit(1)
