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
    aliaserd.py health      Exit 1 and list problems if unhealthy (for Monit)
    aliaserd.py reconfigure Reload config and restart daemon
    aliaserd.py refresh UUID Force immediate refresh of a watcher

Architecture:
    - Reads watcher config from config.xml via OPNsense's XML API
    - Runs a single-threaded async event loop (select-based timer)
    - Each watcher has its own timer based on its configured interval
    - DNS resolution uses socket.getaddrinfo (supports A + AAAA)
    - URL fetching uses urllib (with timeout)
    - Table updates via: pfctl -t <alias> -T replace <ips...>
    - State persisted in /var/db/aliaser/state.json (survives reboot)
    - Logs to syslog facility 'aliaser'
"""

import concurrent.futures
import fcntl
import ipaddress
import json
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import syslog
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET

PIDFILE = '/var/run/aliaser.pid'
STATEFILE = '/var/db/aliaser/state.json'
# Old location, read once for migration. /var/run is wiped at boot, so history kept there was lost.
LEGACY_STATEFILE = '/var/run/aliaser/state.json'
LOCKFILE = '/var/db/aliaser/state.lock'
CONFIG_XML = '/conf/config.xml'
PFCTL = '/sbin/pfctl'

MIN_INTERVAL = 10
# With a TTL from a direct DNS query, re-check when it expires, but not more
# often than this (a TTL of 0 would otherwise mean a busy loop).
MIN_TTL_WAIT = 5
DNS_PORT = 53
# `health` reports a watcher once its source has failed this many times in a row
HEALTH_ERROR_THRESHOLD = 3
MAX_FEED_BYTES = 16 * 1024 * 1024
# When a DNS/URL source fails, keep serving its last good answer for this
# long instead of shrinking the table (an allow-list would lock people out,
# a block-list would silently stop blocking). After that, drop it.
STALE_PRIMARY_MAX_AGE = 24 * 3600

TABLE_NAME_RE = re.compile(r'^[a-zA-Z0-9_]{1,31}$')
UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')
# pf tables OPNsense itself maintains; a watcher must never overwrite them.
# Interface network tables (__lan_network etc.) are covered by the '__' prefix.
# general.logLevel -> syslog mask. "warn" keeps NOTICE so table changes
# still show up in the log by default.
LOG_LEVELS = {
    'error': syslog.LOG_UPTO(syslog.LOG_ERR),
    'warn': syslog.LOG_UPTO(syslog.LOG_NOTICE),
    'info': syslog.LOG_UPTO(syslog.LOG_INFO),
    'debug': syslog.LOG_UPTO(syslog.LOG_DEBUG),
}

RESERVED_TABLES = {'bogons', 'bogonsv6', 'virusprot', 'sshlockout', 'webConfiguratorlockout'}


def split_csv(value):
    return [x.strip() for x in (value or '').split(',') if x.strip()]


def is_valid_target_table(name):
    return (bool(TABLE_NAME_RE.match(name or ''))
            and name not in RESERVED_TABLES
            and not name.startswith('__'))


def normalize_entry(entry):
    """Return a canonical IP/CIDR string, or None if entry is not one.

    Single hosts are returned without a prefix length, because that is how
    `pfctl -T show` prints them; otherwise every check would see a diff.
    """
    try:
        net = ipaddress.ip_network(entry, strict=False)
    except ValueError:
        return None
    if net.prefixlen == net.max_prefixlen:
        return str(net.network_address)
    return str(net)


def mark_include_cycles(watchers):
    """Record, per watcher, the includes that lead back to its own table.

    If A includes B and B includes A, each re-adds the other's addresses, so
    an IP could never be removed from either table. Those includes are skipped.
    """
    graph = {w['alias']: split_csv(w['includeAliases']) for w in watchers}

    def reaches(start, target):
        seen, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node not in seen:
                seen.add(node)
                stack.extend(graph.get(node, []))
        return False

    for w in watchers:
        w['cyclicIncludes'] = [inc for inc in graph[w['alias']] if reaches(inc, w['alias'])]

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
        default_interval = 30
        if general is not None:
            enabled = general.findtext('enabled', '0')
            if enabled != '1':
                return watchers, log_level, max_table_entries
            log_level = general.findtext('logLevel', 'warn')
            try:
                max_table_entries = int(general.findtext('maxTableEntries', '0'))
            except (ValueError, TypeError):
                max_table_entries = 0
            try:
                default_interval = max(MIN_INTERVAL, int(general.findtext('defaultInterval') or 30))
            except (ValueError, TypeError):
                default_interval = 30
        syslog.setlogmask(LOG_LEVELS.get(log_level, LOG_LEVELS['warn']))

        watcher_container = aliaser.find('watchers')
        if watcher_container is None:
            return watchers, log_level, max_table_entries

        for watcher_el in watcher_container:
            if watcher_el.tag != 'watcher':
                continue
            uuid = watcher_el.get('uuid', '')
            name = watcher_el.findtext('name', '')
            raw_interval = (watcher_el.findtext('interval') or '').strip()
            try:
                interval = max(MIN_INTERVAL, int(raw_interval)) if raw_interval else default_interval
            except ValueError:
                syslog.syslog(syslog.LOG_WARNING,
                              f'aliaserd: [{name}] invalid interval, using {default_interval}s')
                interval = default_interval
            w = {
                'uuid': uuid,
                'enabled': watcher_el.findtext('enabled', '0'),
                'name': name,
                'type': watcher_el.findtext('type', 'dns'),
                'hostname': watcher_el.findtext('hostname', ''),
                'hostnames': watcher_el.findtext('hostnames', ''),
                'url': watcher_el.findtext('url', ''),
                'staticEntries': watcher_el.findtext('staticEntries', ''),
                'includeAliases': watcher_el.findtext('includeAliases', ''),
                'alias': watcher_el.findtext('alias', ''),
                'interval': interval,
                'addressFamily': watcher_el.findtext('addressFamily', 'ipv4'),
                'description': watcher_el.findtext('description', ''),
                'dnsServer': watcher_el.findtext('dnsServer', ''),
            }
            if w['enabled'] != '1':
                continue
            # config.xml can be edited directly or arrive via HA sync, bypassing
            # the model's validation, so check the table name again here.
            if not is_valid_target_table(w['alias']):
                syslog.syslog(syslog.LOG_ERR,
                              f'aliaserd: [{name}] refusing target table {w["alias"]!r} '
                              f'(invalid or reserved by OPNsense)')
                continue
            watchers.append(w)

        mark_include_cycles(watchers)
        return watchers, log_level, max_table_entries
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f'aliaserd: config parse error: {e}')
        return watchers, 'warn', 0


# ---------- DNS resolution ----------

class DNSError(Exception):
    pass


# qtype name -> (wire type, address family, rdata length)
DNS_TYPES = {'A': (1, socket.AF_INET, 4), 'AAAA': (28, socket.AF_INET6, 16)}


def _encode_name(hostname):
    out = b''
    for label in hostname.rstrip('.').split('.'):
        raw = label.encode('idna')
        if not 0 < len(raw) < 64:
            raise DNSError(f'invalid hostname {hostname!r}')
        out += bytes([len(raw)]) + raw
    return out + b'\0'


def _skip_name(msg, off):
    """Return the offset just past a (possibly compressed) name at off."""
    while True:
        length = msg[off]
        if length == 0:
            return off + 1
        if length & 0xC0 == 0xC0:  # compression pointer ends the name
            return off + 2
        off += 1 + length


def _parse_answers(resp, qtype, question_len):
    rtype, family, size = DNS_TYPES[qtype]
    try:
        flags, _qdcount, ancount = struct.unpack('>HHH', resp[2:8])
        if not flags & 0x8000:
            raise DNSError('not a response')
        rcode = flags & 0xF
        if rcode == 3:  # NXDOMAIN
            return [], None
        if rcode != 0:
            raise DNSError(f'server returned rcode {rcode}')
        off = 12 + question_len  # the caller verified the question is ours
        ips, ttls = [], []
        for _ in range(ancount):
            off = _skip_name(resp, off)
            atype, aclass, ttl, rdlen = struct.unpack('>HHIH', resp[off:off + 10])
            off += 10
            rdata = resp[off:off + rdlen]
            off += rdlen
            # CNAMEs in the chain are skipped; their target's records follow
            if atype == rtype and aclass == 1 and rdlen == size and len(rdata) == size:
                ips.append(socket.inet_ntop(family, rdata))
                ttls.append(ttl)
        return ips, (min(ttls) if ttls else None)
    except (struct.error, IndexError, ValueError) as e:
        raise DNSError(f'malformed response: {e}')


def dns_query(server, hostname, qtype, timeout=3.0, tries=2):
    """Minimal stub resolver: ask `server` one A or AAAA question over UDP.

    Returns (addresses, ttl), ttl being the smallest TTL of the returned
    records, or ([], None) for NXDOMAIN / no records. Raises DNSError or
    OSError on failure. Replies are only accepted from the server we asked
    (connected socket), with our random ID and our exact question.
    """
    question = _encode_name(hostname) + struct.pack('>HH', DNS_TYPES[qtype][0], 1)
    for _ in range(tries):
        header = os.urandom(2) + struct.pack('>HHHHH', 0x0100, 1, 0, 0, 0)  # RD, 1 question
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((server, DNS_PORT))
            sock.send(header + question)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                try:
                    resp = sock.recv(4096)
                except socket.timeout:
                    break
                if resp[:2] != header[:2] or resp[12:12 + len(question)].lower() != question.lower():
                    continue  # stale reply to an earlier try, or spoofed
                return _parse_answers(resp, qtype, len(question))
    raise DNSError(f'no response from {server}')


def resolve_dns(hostname, address_family='ipv4', dns_server=None):
    """Resolve a hostname. Returns (sorted unique IPs, ttl or None).

    With dns_server, query it directly (bypasses Unbound's cache, and gives
    us the TTL). Otherwise use the system resolver, which reports no TTL.
    """
    qtypes = []
    if address_family in ('ipv4', 'both'):
        qtypes.append('A')
    if address_family in ('ipv6', 'both'):
        qtypes.append('AAAA')

    if dns_server:
        ips, ttls = set(), []
        for qtype in qtypes:
            try:
                found, ttl = dns_query(dns_server, hostname, qtype)
            except (OSError, DNSError) as e:
                syslog.syslog(syslog.LOG_WARNING,
                              f'aliaserd: {qtype} query for {hostname} at {dns_server} failed: {e}')
                continue
            ips.update(found)
            if ttl is not None:
                ttls.append(ttl)
        return sorted(ips), (min(ttls) if ttls else None)

    # Default: system resolver
    ips = set()
    for qtype in qtypes:
        try:
            results = socket.getaddrinfo(hostname, None, DNS_TYPES[qtype][1], socket.SOCK_STREAM)
            for r in results:
                ips.add(r[4][0])
        except socket.gaierror:
            pass

    return sorted(ips), None


# ---------- URL fetching ----------

def fetch_url(url, timeout=30):
    """Fetch a URL and parse one IP/CIDR per line.

    Returns a sorted list, or None on failure. The feed is remote input that
    ends up in pfctl, so anything that is not a valid IP/CIDR is dropped.
    """
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OPNsense-Aliaser/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_FEED_BYTES + 1)
    except Exception as e:
        syslog.syslog(syslog.LOG_WARNING, f'aliaserd: fetch error for {url}: {e}')
        return None  # None signals failure (distinct from empty set)
    if len(body) > MAX_FEED_BYTES:
        syslog.syslog(syslog.LOG_WARNING,
                      f'aliaserd: feed {url} is larger than {MAX_FEED_BYTES} bytes, ignoring it')
        return None

    ips = set()
    invalid = 0
    for line in body.decode('utf-8', errors='ignore').splitlines():
        # Drop comments, incl. trailing ones ("1.2.3.4 ; SBL123"), and any extra columns
        line = line.split('#', 1)[0].split(';', 1)[0].strip()
        if not line:
            continue
        entry = normalize_entry(line.split()[0])
        if entry is None:
            invalid += 1
        else:
            ips.add(entry)
    if invalid:
        syslog.syslog(syslog.LOG_WARNING,
                      f'aliaserd: dropped {invalid} invalid line(s) from {url}')
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
    """Atomically replace all IPs in a pf table.

    Addresses go through a file (-f), never argv: a big feed would exceed
    ARG_MAX, and an entry starting with '-' would be parsed as a pfctl option.
    """
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

    fd, path = tempfile.mkstemp(prefix='aliaser-', suffix='.txt')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(ips) + '\n')
        result = subprocess.run([PFCTL, '-t', alias, '-T', 'replace', '-f', path],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            syslog.syslog(syslog.LOG_ERR,
                          f'aliaserd: pfctl replace failed for {alias}: {result.stderr.strip()}')
            return False
        return True
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f'aliaserd: pfctl replace failed for {alias}: {e}')
        return False
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


# ---------- State management ----------

#
# Two processes write state.json: the daemon, and `aliaserd.py refresh`
# (spawned by configd when the "Refresh Now" button is pressed). Every
# write therefore goes through locked_state(), which re-reads the file
# under an exclusive lock. Never keep a state dict in memory across checks,
# or the next save will overwrite history recorded by the other process.

def load_state():
    """Load watcher state from disk."""
    for path in (STATEFILE, LEGACY_STATEFILE):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {}


def save_state(state):
    """Persist watcher state atomically (readers never see a partial file)."""
    os.makedirs(os.path.dirname(STATEFILE), exist_ok=True)
    tmp = STATEFILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATEFILE)


class locked_state:
    """Context manager: exclusive lock + fresh state; saves on clean exit.

        with locked_state() as state:
            check_watcher(w, state)
    """

    def __enter__(self):
        os.makedirs(os.path.dirname(LOCKFILE), exist_ok=True)
        self._lock = open(LOCKFILE, 'w')
        fcntl.flock(self._lock, fcntl.LOCK_EX)
        self.state = load_state()
        return self.state

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                save_state(self.state)
        finally:
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()
        return False


# ---------- Watcher logic ----------

def gather_primary(watcher):
    """Query the watcher's primary source (DNS or URL). Network I/O only.

    Touches no state and no pf tables, so it is safe to run in a worker
    thread. Returns {'desc': str, 'ips': set or None, 'ttl': int or None};
    ips is None when the source failed, desc is '' when the watcher has no
    primary source, ttl is only known for direct DNS queries.
    """
    primary = {'desc': '', 'ips': None, 'ttl': None}
    if watcher['type'] == 'dns':
        # Use hostnames (plural) first, fall back to hostname (legacy)
        dns_hosts = split_csv(watcher.get('hostnames', '')) or split_csv(watcher.get('hostname', ''))
        if dns_hosts:
            primary['desc'] = ', '.join(dns_hosts)
            af = watcher.get('addressFamily', 'ipv4')
            dns_server = watcher.get('dnsServer', '').strip() or None
            resolved, ttls = set(), []
            for hostname in dns_hosts:
                ips, ttl = resolve_dns(hostname, af, dns_server=dns_server)
                resolved.update(ips)
                if ttl is not None:
                    ttls.append(ttl)
            if resolved:
                primary['ips'] = resolved
                primary['ttl'] = min(ttls) if ttls else None
    elif watcher['type'] == 'urltable':
        url = watcher.get('url', '').strip()
        if url:
            primary['desc'] = url
            # An empty feed is treated as a failure too: it is far more often a
            # broken mirror or captive portal than a list that is really empty.
            result = fetch_url(url)
            if result:
                primary['ips'] = set(result)
    return primary


def check_watcher(watcher, state, max_table_entries=0):
    """Gather + apply in one go. Returns True if the pf table was updated."""
    return apply_watcher(watcher, state, gather_primary(watcher), max_table_entries)


def apply_watcher(watcher, state, primary, max_table_entries=0):
    """
    Merge a watcher's sources and update its pf table. Returns True if the
    table was updated. Updates state dict in-place.

    Composite merge:
      1. Primary source (result of gather_primary) -> merged_ips
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

    now = time.time()
    ws['last_check'] = now

    primary_desc = primary['desc']
    primary_ips = primary['ips']

    # Step 2: Static entries
    static_entries = []
    for entry in split_csv(watcher.get('staticEntries', '')):
        normalized = normalize_entry(entry)
        if normalized is None:
            syslog.syslog(syslog.LOG_WARNING,
                          f'aliaserd: [{name}] ignoring invalid static entry {entry!r}')
        else:
            static_entries.append(normalized)

    # Step 3: Include aliases (read from their pf tables)
    include_aliases = []
    for inc_alias in split_csv(watcher.get('includeAliases', '')):
        if not TABLE_NAME_RE.match(inc_alias):
            syslog.syslog(syslog.LOG_WARNING,
                          f'aliaserd: [{name}] ignoring invalid include alias {inc_alias!r}')
        elif inc_alias in watcher.get('cyclicIncludes', []):
            syslog.syslog(syslog.LOG_WARNING,
                          f'aliaserd: [{name}] skipping include {inc_alias}: '
                          f'it leads back to {alias} (include loop)')
        else:
            include_aliases.append(inc_alias)

    if not primary_desc and not static_entries and not include_aliases:
        return False

    merged_ips = set(static_entries)
    for inc_alias in include_aliases:
        inc_ips = pfctl_show(inc_alias)
        if inc_ips:
            merged_ips.update(inc_ips)
        else:
            syslog.syslog(syslog.LOG_WARNING,
                          f'aliaserd: [{name}] include alias {inc_alias} not accessible or empty')

    if primary_ips is not None:
        merged_ips.update(primary_ips)
        ws['primary_ips'] = sorted(primary_ips)
        ws['primary_ok_at'] = now
        ws['last_error'] = ''
        ws['consecutive_errors'] = 0
    elif primary_desc:
        ws['consecutive_errors'] = ws.get('consecutive_errors', 0) + 1
        error = f'no results from {primary_desc}'
        if 'primary_ips' not in ws:
            # Never had a good answer (new watcher, or state from an older
            # version): we can't tell which table entries came from this
            # source, so leave the table alone rather than guess.
            ws['last_error'] = error + '; table left unchanged'
            syslog.syslog(syslog.LOG_WARNING, f'aliaserd: [{name}] {ws["last_error"]} '
                          f'(errors: {ws["consecutive_errors"]})')
            return False
        age = now - ws.get('primary_ok_at', 0)
        if age < STALE_PRIMARY_MAX_AGE:
            merged_ips.update(ws['primary_ips'])
            error += f'; keeping {len(ws["primary_ips"])} last known entries'
        else:
            error += f'; last good result is {int(age // 3600)}h old, dropping it'
        ws['last_error'] = error
        syslog.syslog(syslog.LOG_WARNING, f'aliaserd: [{name}] {error} '
                      f'(errors: {ws["consecutive_errors"]})')
    else:
        # Static/include-only watcher: nothing here can fail
        ws['last_error'] = ''
        ws['consecutive_errors'] = 0

    new_ips = sorted(merged_ips)

    # Compare with current table
    current_ips = pfctl_show(alias)
    if current_ips is None:
        syslog.syslog(syslog.LOG_WARNING,
                      f'aliaserd: [{name}] pf table {alias} does not exist or cannot be read')
        ws['last_error'] = f'pf table {alias} not accessible'
        return False

    if new_ips == current_ips:
        syslog.syslog(syslog.LOG_DEBUG, f'aliaserd: [{name}] no change ({len(new_ips)} entries)')
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
    ws['last_error'] = f'pfctl could not update table {alias} (see system log)'
    return False


# ---------- Daemon loop ----------

def restore_tables(watchers):
    """Refill empty pf tables from the last known state.

    pf tables start empty after a reboot. Until the first lookup finishes
    (a feed can take many seconds) an allow-list rule would lock people out
    and a block-list rule would block nothing. Tables that already have
    entries (e.g. a plain daemon restart) are left alone.
    """
    state = load_state()
    for w in watchers:
        ws = state.get(w['name'], {})
        if ws.get('alias') != w['alias']:
            continue  # target table changed since this state was written
        saved = [e for e in (normalize_entry(x) for x in ws.get('current_ips', [])) if e]
        if saved and pfctl_show(w['alias']) == [] and pfctl_replace(w['alias'], saved):
            syslog.syslog(syslog.LOG_NOTICE,
                          f'aliaserd: [{w["name"]}] restored {len(saved)} entries '
                          f'into {w["alias"]} from saved state')


def next_check_delay(watcher, primary):
    """Seconds until a watcher's next check.

    Normally its interval. If the DNS answer's TTL runs out sooner, check
    right when it does: that is when a changed record becomes visible, so
    waiting for the interval only adds delay. Never later than the
    interval, never sooner than MIN_TTL_WAIT.
    """
    ttl = (primary or {}).get('ttl')
    if ttl is None:
        return watcher['interval']
    return max(MIN_TTL_WAIT, min(watcher['interval'], ttl + 1))


class Scheduler:
    """Runs each watcher on its own timer.

    Lookups (DNS, URL fetch) run in a thread pool so one slow feed can't
    delay the other watchers. Applying results - pf updates and state
    writes - always happens on the thread calling tick().
    """

    def __init__(self, pool):
        self.pool = pool
        self.next_due = {}  # watcher name -> timestamp
        self.pending = {}   # watcher name -> (watcher dict, future)

    def tick(self, watchers, max_table_entries, now=None):
        """Apply finished lookups, start due ones. Returns seconds to sleep."""
        now = time.time() if now is None else now
        by_name = {w['name']: w for w in watchers}

        for name, (w, future) in list(self.pending.items()):
            if not future.done():
                continue
            del self.pending[name]
            if by_name.get(name) != w:
                continue  # removed or edited meanwhile; rerun with the new config
            changed, primary = False, None
            try:
                primary = future.result()
                with locked_state() as state:
                    changed = apply_watcher(w, state, primary, max_table_entries)
            except Exception as e:
                syslog.syslog(syslog.LOG_ERR, f'aliaserd: [{name}] unexpected error: {e}')
            self.next_due[name] = now + next_check_delay(w, primary)
            if changed:
                self._wake_dependents(w['alias'], watchers, now)

        for w in watchers:
            name = w['name']
            if name not in self.pending and now >= self.next_due.get(name, 0):
                self.pending[name] = (w, self.pool.submit(gather_primary, w))

        for name in list(self.next_due):
            if name not in by_name:
                del self.next_due[name]

        if self.pending:
            return 0.5
        upcoming = [self.next_due.get(name, now) for name in by_name] + [now + 10]
        return max(0.5, min(upcoming) - now)

    def _wake_dependents(self, alias, watchers, now):
        # Watchers that include this table re-merge right away instead of
        # waiting for their own interval.
        for w in watchers:
            if alias in split_csv(w['includeAliases']) and alias not in w.get('cyclicIncludes', []):
                syslog.syslog(syslog.LOG_INFO,
                              f'aliaserd: [{w["name"]}] included table {alias} changed, re-merging now')
                self.next_due[w['name']] = now


def config_signature():
    try:
        st = os.stat(CONFIG_XML)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def run_daemon():
    """Main daemon loop. Reads config, runs watchers on their intervals."""
    syslog.openlog('aliaserd', syslog.LOG_PID, syslog.LOG_LOCAL4)
    syslog.syslog(syslog.LOG_NOTICE, 'aliaserd: starting')

    # Hold an exclusive lock on the pidfile for our whole life, so two
    # `start` calls racing each other can't leave two daemons running.
    os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
    pidfile = open(PIDFILE, 'a+')
    try:
        fcntl.flock(pidfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        syslog.syslog(syslog.LOG_NOTICE, 'aliaserd: another instance is running, exiting')
        return
    pidfile.seek(0)
    pidfile.truncate()
    pidfile.write(str(os.getpid()))
    pidfile.flush()

    running = True

    def handle_signal(signum, frame):
        nonlocal running
        running = False

    def wait(seconds):
        # time.sleep() resumes after a signal (PEP 475), so sleep in short
        # slices; otherwise SIGTERM waits out the sleep and `stop` escalates
        # to SIGKILL.
        deadline = time.time() + seconds
        while running and time.time() < deadline:
            time.sleep(min(0.5, max(0, deadline - time.time())))

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    scheduler = Scheduler(pool)
    config_sig = None
    watchers, max_table_entries = [], 0
    restored = False

    while running:
        # The loop wakes every 0.5s while lookups are in flight; only
        # re-parse config.xml when it actually changed.
        sig = config_signature()
        if sig != config_sig or sig is None:
            config_sig = sig
            watchers, log_level, max_table_entries = read_config()
        if not restored:
            restore_tables(watchers)
            restored = True
        wait(min(scheduler.tick(watchers, max_table_entries), 10))

    # Cleanup. Worker threads may still be blocked in a lookup; don't wait
    # for them (the caller exits the process with os._exit()).
    pool.shutdown(wait=False, cancel_futures=True)
    syslog.syslog(syslog.LOG_NOTICE, 'aliaserd: stopping')
    try:
        os.unlink(PIDFILE)
    except FileNotFoundError:
        pass


# ---------- Daemon control ----------

def get_pid():
    """Read PID from pidfile, return None if the daemon is not running.

    After a crash or SIGKILL the pidfile is stale and its PID may belong to
    an unrelated process by now, so check the command line before trusting
    it (cmd_stop sends signals to whatever PID this returns).
    """
    try:
        with open(PIDFILE, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # Check if process exists
        # -ww: without a tty, ps truncates the command line (~80 columns),
        # which can cut off the script name
        result = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'command='],
                                capture_output=True, text=True, timeout=5)
        if 'aliaserd' not in result.stdout:
            return None
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError,
            OSError, subprocess.SubprocessError):
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
    # Detach stdio at the fd level: replacing sys.stdout alone leaves fds 1/2
    # pointing at the caller's pipe, and a caller capturing our output
    # (configd, a test) would then wait forever for EOF.
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    os.close(devnull)
    run_daemon()
    os._exit(0)  # don't wait for lookup threads still blocked on the network


def cmd_stop():
    pid = get_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):  # Wait up to 10s (a check in progress may take a while)
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
            'dnsServer': w.get('dnsServer', ''),
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


def health_problems(watchers, state, daemon_running, now=None):
    """List what a monitoring system should alert on (empty list = healthy)."""
    now = time.time() if now is None else now
    problems = [] if daemon_running else ['daemon is not running']
    for w in watchers:
        name, ws = w['name'], state.get(w['name'], {})
        errors = ws.get('consecutive_errors', 0)
        if errors >= HEALTH_ERROR_THRESHOLD:
            problems.append(f'{name}: {errors} failures in a row: {ws.get("last_error", "")}')
        for alert in ws.get('alerts', []):
            problems.append(f'{name}: {alert.get("message", "")}')
        last = ws.get('last_check', 0)
        # last == 0: not checked yet (new watcher, daemon just started)
        if daemon_running and last and now - last > max(3 * w['interval'], w['interval'] + 120):
            problems.append(f'{name}: not checked for {int(now - last)}s (interval {w["interval"]}s)')
    return problems


def plugin_enabled():
    try:
        return ET.parse(CONFIG_XML).getroot().findtext('.//OPNsense/Aliaser/general/enabled') == '1'
    except (OSError, ET.ParseError):
        return False


def cmd_health():
    """Monit-style check: exit 0 when healthy, 1 with one line per problem."""
    if not plugin_enabled():
        print('OK: aliaser is disabled')
        return
    watchers, _, _ = read_config()
    problems = health_problems(watchers, load_state(), get_pid() is not None)
    if problems:
        print('\n'.join(problems))
        sys.exit(1)
    print(f'OK: {len(watchers)} watcher(s) healthy')


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
    if not UUID_RE.match(uuid):
        print(json.dumps({'status': 'error', 'message': 'invalid uuid'}))
        return
    watchers, _, max_table_entries = read_config()

    for w in watchers:
        if w['uuid'] == uuid:
            primary = gather_primary(w)  # network I/O outside the state lock
            with locked_state() as state:
                changed = apply_watcher(w, state, primary, max_table_entries)
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
        print(f'Usage: {sys.argv[0]} start|stop|restart|status|health|reconfigure|refresh [uuid]')
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
    elif cmd == 'health':
        cmd_health()
    elif cmd == 'refresh' and len(sys.argv) > 2:
        cmd_refresh(sys.argv[2])
    else:
        print(f'Unknown command: {cmd}')
        sys.exit(1)
