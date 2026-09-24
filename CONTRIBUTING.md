# Contributing to os-aliaser

Thanks for your interest in improving os-aliaser. This guide covers the
development workflow, code conventions, and how to get your changes merged.

## Development Environment

You need a working OPNsense installation for testing. A VM works well:

1. Install OPNsense 24.7+ in a VM (VirtualBox, Proxmox, etc.)
2. Enable SSH access: System > Settings > Administration > Enable Secure Shell
3. SSH in as root and clone the repo:

```sh
git clone https://github.com/DaneHou/os-aliaser.git ~/os-aliaser
cd ~/os-aliaser
make install
```

4. Hard-refresh your browser (Ctrl+Shift+R) to pick up menu changes
5. Navigate to Services > Aliaser

For iterative development, use:

```sh
make install-plugin && make activate
```

This reinstalls plugin files without restarting everything from scratch.

## Code Style

### PHP

Follow OPNsense conventions:

- 4-space indentation
- Opening brace on the same line for functions
- Use OPNsense MVC patterns (models, controllers, forms, views)
- Docblocks on public functions
- Match the style in `aliaser.inc` and the existing controllers

### Python

- PEP 8 with 4-space indentation
- Use `syslog` for operational messages (not `print`)
- Target Python 3.9+ (the version bundled with OPNsense)
- Standard library only — no `pip`/`pkg` dependencies
- Match the patterns in `aliaserd.py`

### XML (MVC Models, Menus, ACLs)

- 4-space indentation
- Follow the existing OPNsense MVC schema conventions

### JavaScript (Volt Templates)

- Follow the jQuery + UIBootgrid patterns used by OPNsense
- Use OPNsense standard helpers (`mapDataToFormUI`, `SimpleActionButton`, etc.)

## Making Changes

### Branch Naming

Use a descriptive prefix:

- `fix/` — bug fixes (e.g., `fix/daemon-not-starting-on-boot`)
- `feat/` — new features (e.g., `feat/ttl-aware-resolution`)
- `docs/` — documentation only
- `refactor/` — code restructuring without behavior changes

### Workflow

1. Fork the repository on GitHub
2. Create a feature branch from `main`
3. Make your changes
4. Run the automated tests, and test on an OPNsense installation (see below)
5. Commit with a clear message describing what changed and why
6. Push your branch and open a pull request against `main`

### Commit Messages

Write concise commit messages that explain the "why":

```
Fix daemon not restarting after config change

The reconfigure action was calling cmd_stop() but not waiting for the
PID file to be cleaned up before starting the new instance, causing
a race condition where the new daemon couldn't write the PID file.
```

## Testing

### Automated tests

The daemon has a pytest suite that runs anywhere (no OPNsense needed). It
drives the real `aliaserd.py` against a fake `pfctl` (`tests/fake_pfctl.py`,
tables are plain files) and fake DNS answers (`tests/harness.py`):

```sh
pip install pytest
python3 -m pytest -q tests
```

CI runs it on Python 3.9 and 3.11 for every push, plus `php -l` and an XML
well-formedness check. Any change to daemon behaviour should come with a test.

### Manual checklist

The UI, configd and real pf still need an OPNsense VM. Before submitting a PR, verify:

- [ ] `make install` completes without errors
- [ ] The Services > Aliaser menu appears (after browser hard-refresh)
- [ ] Add a DNS watcher pointing to a known hostname, apply — daemon starts
- [ ] Services > Aliaser > Status shows the watcher with resolved IPs
- [ ] "Refresh Now" button triggers an immediate check
- [ ] Change the hostname's DNS record (or use a different hostname) — alias updates
- [ ] Composite: add multiple hostnames, static IPs, and include aliases — all merged
- [ ] Status page shows sources summary and change history
- [ ] Start/Stop/Restart buttons on status page work correctly
- [ ] Disable a watcher and apply — it stops being checked
- [ ] `make uninstall` cleanly removes the plugin
- [ ] Reboot the OPNsense VM — daemon restarts, logs `restored N entries`, tables are filled right away
- [ ] `aliaserd.py health` prints `OK` (and exits 1 with a reason after stopping the daemon)

For daemon debugging:

```sh
# Check daemon status
configctl aliaser status

# View syslog entries
clog /var/log/system/latest.log | grep aliaserd

# Run status directly
/usr/local/opnsense/scripts/OPNsense/Aliaser/aliaserd.py status

# Check a specific pf table
pfctl -t MyAlias -T show
```

## Reporting Bugs

Open a [GitHub issue](https://github.com/DaneHou/os-aliaser/issues/new) with:

- OPNsense version (`opnsense-version`)
- Plugin version (from `Makefile` or the Changelog)
- Steps to reproduce
- Expected vs. actual behavior
- Output of `configctl aliaser status`

## Pull Request Process

1. Describe what changed and why, and which tests/checklist items you ran
2. Keep PRs focused — one logical change per PR
3. Maintainers will review within a few days
4. Address review feedback by pushing additional commits (no force-push)
5. Once approved, a maintainer will merge

## Security Issues

Do **not** open public issues for security vulnerabilities. See
[SECURITY.md](SECURITY.md) for the private disclosure process.

## Questions?

- Open a [GitHub Discussion](https://github.com/DaneHou/os-aliaser/discussions)
  for general questions
- Check existing issues before opening a new one
- For OPNsense-specific questions (not plugin-related), try the
  [OPNsense Forum](https://forum.opnsense.org/)

## License

By contributing, you agree that your contributions will be licensed under the
[BSD 2-Clause License](LICENSE).
