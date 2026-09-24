import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402

UUID1 = '3f2b8c1e-9d4a-4b7e-8f10-2a6c5e7d9b01'
UUID2 = '7a1d2e3f-4b5c-4d6e-8f70-8192a3b4c5d6'


class Env:
    """A throwaway OPNsense: config.xml, pf tables, DNS answers, state dir."""

    def __init__(self, path):
        self.path = str(path)
        self.mod = harness.load(self.path)
        self.tables = os.path.join(self.path, 'tables')

    def table(self, name):
        with open(os.path.join(self.tables, name)) as f:
            return f.read().split()

    def set_table(self, name, *ips):
        with open(os.path.join(self.tables, name), 'w') as f:
            f.write(''.join(ip + '\n' for ip in ips))

    def set_dns(self, answers):
        with open(os.path.join(self.path, 'dns.json'), 'w') as f:
            json.dump(answers, f)

    def pfctl_calls(self):
        with open(os.path.join(self.tables, '.argv')) as f:
            return f.read().splitlines()

    def write_config(self, *watchers, general=''):
        rows = []
        for w in watchers:
            fields = ''.join(f'<{k}>{v}</{k}>' for k, v in w.items() if k != 'uuid')
            rows.append(f'<watcher uuid="{w["uuid"]}"><enabled>1</enabled>{fields}</watcher>')
        with open(os.path.join(self.path, 'config.xml'), 'w') as f:
            f.write('<opnsense><OPNsense><Aliaser><general><enabled>1</enabled>'
                    f'{general}</general><watchers>{"".join(rows)}</watchers>'
                    '</Aliaser></OPNsense></opnsense>')

    def state(self):
        with open(self.mod.STATEFILE) as f:
            return json.load(f)


def watcher(name, alias, **kw):
    """In-memory watcher dict as read_config() returns it."""
    w = dict(uuid=UUID1, name=name, type='dns', hostnames='', hostname='', url='',
             staticEntries='', includeAliases='', alias=alias, interval=30,
             addressFamily='ipv4', dnsServer='', description='', cyclicIncludes=[])
    w.update(kw)
    return w


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)
