# Custom DNS Server per Watcher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow each DNS watcher to query a specific external DNS server (e.g. 1.1.1.1) directly, bypassing the OS resolver cache.

**Architecture:** Add an optional `dnsServer` text field per watcher. When populated, `resolve_dns()` uses `dnspython` to query that server directly. When empty, existing `socket.getaddrinfo` behavior is preserved. Lazy import keeps the daemon working without dnspython installed.

**Tech Stack:** Python 3.9+ stdlib, dnspython (optional), OPNsense MVC (PHP/XML/Volt)

**Spec:** `docs/superpowers/specs/2026-03-26-custom-dns-server-design.md`

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/opnsense/mvc/app/models/OPNsense/Aliaser/Aliaser.xml` | Add `dnsServer` field to watcher schema |
| Modify | `src/opnsense/mvc/app/controllers/OPNsense/Aliaser/forms/watcher.xml` | Add DNS Server form field |
| Modify | `src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py` | Config parsing, dnspython resolution, status output |

---

### Task 1: Add `dnsServer` to config model

**Files:**
- Modify: `src/opnsense/mvc/app/models/OPNsense/Aliaser/Aliaser.xml:108-115`

- [ ] **Step 1: Add dnsServer field after addressFamily in Aliaser.xml**

Insert the following XML block after the closing `</addressFamily>` tag (line 115) and before `<description>`:

```xml
                <!-- DNS: optional external DNS server to query directly -->
                <dnsServer type="TextField">
                    <Required>N</Required>
                    <Mask>/^([0-9]{1,3}\.){3}[0-9]{1,3}$|^$/</Mask>
                    <ValidationMessage>Enter a valid IPv4 address (e.g. 1.1.1.1) or leave empty for system default</ValidationMessage>
                </dnsServer>
```

- [ ] **Step 2: Commit**

```bash
git add src/opnsense/mvc/app/models/OPNsense/Aliaser/Aliaser.xml
git commit -m "feat: add dnsServer field to watcher config model"
```

---

### Task 2: Add DNS Server form field

**Files:**
- Modify: `src/opnsense/mvc/app/controllers/OPNsense/Aliaser/forms/watcher.xml:62-67`

- [ ] **Step 1: Add form field after addressFamily field in watcher.xml**

Insert the following XML block after the Address Family `</field>` closing tag (line 67) and before the Description field:

```xml
    <field>
        <id>watcher.dnsServer</id>
        <label>DNS Server</label>
        <type>text</type>
        <help>Query this DNS server directly instead of the system resolver (bypasses DNS cache). Leave empty to use the system default. Example: 1.1.1.1</help>
    </field>
```

- [ ] **Step 2: Commit**

```bash
git add src/opnsense/mvc/app/controllers/OPNsense/Aliaser/forms/watcher.xml
git commit -m "feat: add DNS Server field to watcher edit form"
```

---

### Task 3: Update config parsing in daemon

**Files:**
- Modify: `src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py:77-91`

- [ ] **Step 1: Add dnsServer to the watcher dict in `read_config()`**

In the watcher dict construction (around line 90, after `'description'`), add:

```python
                'dnsServer': watcher_el.findtext('dnsServer', ''),
```

The full dict should now include this key alongside the existing fields.

- [ ] **Step 2: Commit**

```bash
git add src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py
git commit -m "feat: read dnsServer from watcher config"
```

---

### Task 4: Implement dnspython resolution path

**Files:**
- Modify: `src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py:101-120`

- [ ] **Step 1: Replace the `resolve_dns` function**

Replace the entire `resolve_dns` function (lines 103-120) with:

```python
def resolve_dns(hostname, address_family='ipv4', dns_server=None):
    """Resolve a hostname to a sorted list of unique IPs.

    If dns_server is provided, query it directly via dnspython
    (bypasses OS resolver cache). Otherwise use socket.getaddrinfo.
    """
    if dns_server:
        try:
            import dns.resolver
            import dns.exception
        except ImportError:
            syslog.syslog(syslog.LOG_ERR,
                          'aliaserd: dnspython not installed — '
                          'run: pkg install py311-dnspython')
            return []

        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [dns_server]
        resolver.lifetime = 10

        ips = set()
        rdtypes = []
        if address_family in ('ipv4', 'both'):
            rdtypes.append('A')
        if address_family in ('ipv6', 'both'):
            rdtypes.append('AAAA')

        for rdtype in rdtypes:
            try:
                answers = resolver.resolve(hostname, rdtype)
                for rdata in answers:
                    ips.add(rdata.address)
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
                    dns.resolver.NoNameservers, dns.exception.Timeout):
                pass

        return sorted(ips)

    # Default: system resolver
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
```

Key differences from original:
- New `dns_server` parameter
- `try/except ImportError` around dnspython import — logs clear error message if not installed, returns empty list
- dnspython path: `Resolver(configure=False)` with explicit nameserver and 10s timeout
- Original `socket.getaddrinfo` path unchanged in the `else` branch

- [ ] **Step 2: Commit**

```bash
git add src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py
git commit -m "feat: add dnspython resolution path for custom DNS servers"
```

---

### Task 5: Pass dnsServer through check_watcher

**Files:**
- Modify: `src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py:249-251`

- [ ] **Step 1: Update the DNS resolution call in `check_watcher()`**

Find this code block inside `check_watcher()` (around line 249-251):

```python
        af = watcher.get('addressFamily', 'ipv4')
        for hostname in dns_hosts:
            ips = resolve_dns(hostname, af)
```

Replace with:

```python
        af = watcher.get('addressFamily', 'ipv4')
        dns_server = watcher.get('dnsServer', '').strip() or None
        for hostname in dns_hosts:
            ips = resolve_dns(hostname, af, dns_server=dns_server)
```

- [ ] **Step 2: Commit**

```bash
git add src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py
git commit -m "feat: pass dnsServer to resolve_dns in check_watcher"
```

---

### Task 6: Add dnsServer to status output

**Files:**
- Modify: `src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py:534-551`

- [ ] **Step 1: Add dnsServer to the watcher status dict in `cmd_status()`**

In the `output['watchers'][name]` dict (around line 534), add after the `'interval'` key:

```python
            'dnsServer': w.get('dnsServer', ''),
```

- [ ] **Step 2: Commit**

```bash
git add src/opnsense/scripts/OPNsense/Aliaser/aliaserd.py
git commit -m "feat: include dnsServer in status output"
```

---

### Task 7: Verification on OPNsense

This task is manual — run on the OPNsense VM after `make install`.

- [ ] **Step 1: Install dnspython**

```bash
pkg install py311-dnspython
```

- [ ] **Step 2: Deploy and activate**

```bash
make install
```

Hard-refresh browser (Ctrl+Shift+R).

- [ ] **Step 3: Verify form field appears**

Navigate to Services > Aliaser > Watchers. Edit a DNS watcher. Confirm "DNS Server" field appears after "Address Family".

- [ ] **Step 4: Test with custom DNS server**

Set a DNS watcher's DNS Server to `1.1.1.1`. Apply. Check status page — watcher should resolve and show IPs.

- [ ] **Step 5: Test without custom DNS server**

Create/edit a watcher with DNS Server left empty. Confirm it resolves using system default (same behavior as before).

- [ ] **Step 6: Test missing dnspython**

Temporarily remove dnspython: `pkg remove py311-dnspython`. Restart daemon. Confirm watcher with `dnsServer` set logs an error but daemon stays running. Watchers without `dnsServer` should work normally. Re-install after: `pkg install py311-dnspython`.

- [ ] **Step 7: Check status API**

```bash
/usr/local/opnsense/scripts/OPNsense/Aliaser/aliaserd.py status | python3 -m json.tool
```

Confirm `dnsServer` field appears in watcher output.
