# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | Yes                |
| < 1.0   | No                 |

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
- Runtime state is stored in `/var/run/aliaser/state.json` and contains only
  IP addresses, timestamps, and error messages.
- The PID file is at `/var/run/aliaser.pid`.

### Network Security

- DNS resolution uses the system resolver. Ensure your OPNsense DNS settings
  (Unbound / system nameservers) are trusted.
- URL feed fetching uses HTTPS when the feed URL uses HTTPS. The daemon
  respects system CA certificates.
- The daemon does not listen on any network ports.

### Input Validation

- Watcher names are restricted to `[a-zA-Z0-9_]{1,32}` via MVC model validation.
- Hostnames are validated against FQDN patterns.
- Multi-hostnames are restricted to `[a-zA-Z0-9\-.,\s]{0,512}` (comma-separated FQDNs).
- Static entries are restricted to `[0-9a-fA-F:./,\s]{0,1024}` (IPs and CIDRs only).
- Include alias names are restricted to `[a-zA-Z0-9_,\s]{0,256}` (valid pf table names).
- Self-referencing in include aliases is skipped to prevent loops.
- URLs are validated to start with `http://` or `https://`.
- Alias names are validated to `[a-zA-Z0-9_]{1,31}` (pf table name limits).
- All user input passes through OPNsense MVC field validators before reaching
  the daemon.

### pf Table Operations

- The daemon only uses `pfctl -t <name> -T show` (read) and
  `pfctl -t <name> -T replace` (atomic write).
- Table names are taken from validated config, not user input at runtime.
- The daemon never calls `filter reload` or modifies firewall rules.

## Known Security Considerations

- **URL feeds are trusted input.** If a threat feed URL is compromised, the
  attacker can inject arbitrary IPs into your firewall aliases. Only use feeds
  from sources you trust.
- **DNS spoofing** could inject incorrect IPs into aliases. Use DNSSEC or a
  trusted recursive resolver to mitigate this.
- **Config backups contain watcher definitions.** While no credentials are
  stored, the hostnames and URLs in watcher configs may reveal information
  about your network topology.
