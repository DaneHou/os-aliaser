# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.2.x   | Yes                |
| < 1.2   | No                 |

Only the latest release receives security fixes. Upgrade to the latest version
by running `git pull && make install` on your OPNsense system.

## Reporting Vulnerabilities

**Do not open public GitHub issues for security vulnerabilities.**

Report security issues through
[GitHub Security Advisories](https://github.com/DaneHou/os-aliaser/security/advisories/new).

When reporting, please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof of concept
- The plugin version and OPNsense version you tested on
- Any suggested fix, if you have one

## Response Timeline

- **Acknowledgment:** within 72 hours of your report
- **Initial assessment:** within 1 week
- **Fix or mitigation:** depends on severity, typically within 2 weeks for
  critical issues

You will be credited in the fix commit and changelog unless you prefer to
remain anonymous.

## Security Design

### Privilege Model

The plugin runs as **root** on OPNsense, which is standard for OPNsense
plugins. The daemon (`aliaserd.py`) is executed by configd, which runs as root.
This is required because `pfctl` table operations need root privileges.

### Data Handling

- Watcher configuration is stored in `/conf/config.xml` (OPNsense standard).
- No credentials are stored by this plugin (unlike VPN/proxy plugins, alias
  watchers only use public DNS and public URLs).
- Runtime state is stored in `/var/db/aliaser/state.json` and contains only
  IP addresses, timestamps, and error messages.
- The PID file is at `/var/run/aliaser.pid`.

### Network Security

- DNS resolution uses the system resolver by default. Ensure your OPNsense DNS
  settings (Unbound / system nameservers) are trusted.
- Watchers with a custom DNS server use the daemon's built-in stub resolver
  (plain UDP, no DNSSEC validation). It only accepts replies from the queried
  server (connected socket) that carry the random query ID and echo the exact
  question; everything else is discarded.
- URL feed fetching uses HTTPS when the feed URL uses HTTPS. The daemon
  respects system CA certificates.
- The daemon does not listen on any network ports.

### Input Validation

- Watcher names are restricted to `[a-zA-Z0-9_]{1,32}` via MVC model validation.
- Hostnames are validated against FQDN patterns.
- Multi-hostnames are restricted to `[a-zA-Z0-9\-.,\s]{0,512}` (comma-separated FQDNs).
- Static entries are restricted to `[0-9a-fA-F:./,\s]{0,1024}` (IPs and CIDRs only).
- Include alias names are restricted to `[a-zA-Z0-9_,\s]{0,256}` (valid pf table names).
- Include loops (self-reference, or A includes B includes A) are detected and
  the looping include is skipped.
- URLs must start with `http://` or `https://` and may not contain whitespace,
  quotes, `<`, `>` or backslashes.
- Alias names are validated to `[a-zA-Z0-9_]{1,31}` (pf table name limits), and
  OPNsense's own tables (`bogons`, `bogonsv6`, `virusprot`, `sshlockout`,
  `webConfiguratorlockout`, `__*`) are refused as targets.
- All user input passes through OPNsense MVC field validators before reaching
  the daemon. The daemon re-validates table names, static entries and include
  names itself, since `config.xml` can also be edited directly or arrive via HA sync.
- Every entry from a URL feed or the static list is parsed with Python's
  `ipaddress` module; anything that is not a valid IP/CIDR is dropped and logged.
  Feeds larger than 16 MB are rejected.
- The "Refresh Now" API accepts only a well-formed UUID and passes it to configd
  as an escaped parameter.
- The web UI HTML-escapes every value it renders (watcher fields, daemon status,
  error messages, log lines).

### pf Table Operations

- The daemon only uses `pfctl -t <name> -T show` (read) and
  `pfctl -t <name> -T replace -f <tempfile>` (atomic write). Addresses are
  passed in a file, never on the command line, so a feed entry can't be
  interpreted as a `pfctl` option.
- Table names are taken from validated config, not user input at runtime.
- The daemon never calls `filter reload` or modifies firewall rules.

## Known Security Considerations

- **URL feeds are trusted for their content.** Entries are validated as IPs,
  but a compromised feed can still put arbitrary *valid* IPs into your aliases.
  Only use feeds from sources you trust.
- **Failed sources keep their last good result for 24 hours.** If DNS or a feed
  fails, the table is not shrunk (that would unblock a block-list or lock users
  out of an allow-list). After 24 hours of failures the stale entries are dropped.

### Access Control

- *Services: Aliaser: Status* allows viewing status and "Refresh Now" only.
- Starting/stopping the service, editing watchers and creating firewall aliases
  require *Services: Aliaser: Watchers*.
- **DNS spoofing** could inject incorrect IPs into aliases. Use DNSSEC or a
  trusted recursive resolver to mitigate this.
- **Config backups contain watcher definitions.** While no credentials are
  stored, the hostnames and URLs in watcher configs may reveal information
  about your network topology.
