# Custom DNS Server per Watcher

## Problem

`resolve_dns()` uses `socket.getaddrinfo` which goes through the OS DNS resolver (Unbound on OPNsense). When a DNS record changes upstream (e.g., on Cloudflare), Unbound caches the old result until TTL expires (often 300s). Even with a 30s watcher interval, aliaser cannot detect the change faster than the cache allows.

## Solution

Add an optional `dnsServer` field per watcher. When set, bypass the system resolver and query the specified DNS server directly using `dnspython`. When empty, keep the existing `socket.getaddrinfo` behavior.

## Scope

Per-watcher only. No global DNS setting. URL-type watchers are unaffected.

## Dependency

`dnspython` — installed via `pkg install py311-dnspython` on FreeBSD/OPNsense. Only imported when at least one watcher has `dnsServer` configured; the daemon still starts fine without it if no watcher uses the feature.

## Changes

### 1. Model — `Aliaser.xml`

Add `dnsServer` field inside `<watcher>`:

```xml
<dnsServer type="TextField">
    <Required>N</Required>
    <Mask>/^([0-9]{1,3}\.){3}[0-9]{1,3}$|^$/</Mask>
    <ValidationMessage>Enter a valid IPv4 address (e.g. 1.1.1.1) or leave empty for system default</ValidationMessage>
</dnsServer>
```

Placed after `addressFamily`, before `description`.

### 2. Form — `watcher.xml`

Add field after Address Family:

```xml
<field>
    <id>watcher.dnsServer</id>
    <label>DNS Server</label>
    <type>text</type>
    <help>Query this DNS server directly instead of the system resolver. Leave empty to use the system default. Example: 1.1.1.1</help>
</field>
```

### 3. Daemon — `aliaserd.py`

#### Config parsing (`read_config`)

Read `dnsServer` from watcher XML element:

```python
'dnsServer': watcher_el.findtext('dnsServer', ''),
```

#### DNS resolution (`resolve_dns`)

Add `dns_server=None` parameter. Two code paths:

```python
def resolve_dns(hostname, address_family='ipv4', dns_server=None):
    if dns_server:
        # Use dnspython for direct query
        import dns.resolver
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [dns_server]
        resolver.lifetime = 10  # 10s timeout

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
    else:
        # Existing behavior: system resolver
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

#### Caller update (`check_watcher`)

Pass `dnsServer` through:

```python
dns_server = watcher.get('dnsServer', '').strip() or None
ips = resolve_dns(hostname, af, dns_server=dns_server)
```

#### Status output (`cmd_status`)

Add `dnsServer` to watcher output dict for debugging visibility.

### 4. No other changes

- `aliaser.inc` — no change (no new services/hooks)
- `actions_aliaser.conf` — no change
- Volt templates — no change needed (status.volt already renders arbitrary watcher fields)
- Makefile — no change

## Backward Compatibility

- Existing watchers have no `dnsServer` value → `findtext('dnsServer', '')` returns `''` → system resolver used → identical behavior
- `dnspython` is only imported inside the `if dns_server:` branch → daemon works without the package as long as no watcher uses the feature

## Installation Note

Users who want to use custom DNS servers need to install dnspython once:

```sh
pkg install py311-dnspython
```

This should be documented in README.md under requirements (optional dependency).
