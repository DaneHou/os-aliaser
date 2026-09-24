"""Load aliaserd.py with every path pointed into a test directory.

Used by conftest.py (in-process) and as a script for multi-process tests:
    python3 harness.py TESTDIR start|stop|run|refresh UUID
DNS answers come from TESTDIR/dns.json: {"hostname": ["1.2.3.4", ...]}.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
DAEMON = os.path.join(HERE, '..', 'src', 'opnsense', 'scripts', 'OPNsense', 'Aliaser', 'aliaserd.py')


def load(testdir):
    spec = importlib.util.spec_from_file_location('aliaserd', DAEMON)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tables = os.path.join(testdir, 'tables')
    os.makedirs(tables, exist_ok=True)
    os.environ['PFCTL_TABLES'] = tables
    mod.PFCTL = os.path.join(HERE, 'fake_pfctl.py')
    mod.CONFIG_XML = os.path.join(testdir, 'config.xml')
    mod.STATEFILE = os.path.join(testdir, 'db', 'state.json')
    mod.LOCKFILE = os.path.join(testdir, 'db', 'state.lock')
    mod.LEGACY_STATEFILE = os.path.join(testdir, 'legacy-state.json')
    mod.PIDFILE = os.path.join(testdir, 'aliaserd.pid')

    def fake_resolve(hostname, address_family='ipv4', dns_server=None):
        try:
            with open(os.path.join(testdir, 'dns.json')) as f:
                return list(json.load(f).get(hostname, [])), None
        except (FileNotFoundError, ValueError):
            return [], None
    mod.real_resolve_dns = mod.resolve_dns  # for tests of the DNS client itself
    mod.resolve_dns = fake_resolve
    return mod


if __name__ == '__main__':
    a = load(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == 'refresh':
        a.cmd_refresh(sys.argv[3])
    else:
        {'start': a.cmd_start, 'stop': a.cmd_stop, 'run': a.run_daemon}[cmd]()
