"""A failing source must not shrink the table (fail closed), within limits."""
import time

from conftest import watcher


def test_dns_outage_keeps_last_good_then_expires(env):
    w = watcher('w9', 'T9', hostnames='h.example', staticEntries='9.9.9.9')
    env.set_table('T9')
    state = {}
    env.set_dns({'h.example': ['5.5.5.5']})
    env.mod.check_watcher(w, state)
    env.set_dns({})
    env.mod.check_watcher(w, state)
    assert env.table('T9') == ['5.5.5.5', '9.9.9.9']
    assert 'keeping 1 last known' in state['w9']['last_error']
    assert state['w9']['consecutive_errors'] == 1

    state['w9']['primary_ok_at'] -= env.mod.STALE_PRIMARY_MAX_AGE + 1
    env.mod.check_watcher(w, state)
    assert env.table('T9') == ['9.9.9.9']


def test_no_known_good_result_leaves_table_alone(env):
    env.set_table('T8', '7.7.7.7')
    state = {}
    env.mod.check_watcher(watcher('w8', 'T8', hostnames='h.example', staticEntries='9.9.9.9'), state)
    assert env.table('T8') == ['7.7.7.7']
    assert 'table left unchanged' in state['w8']['last_error']


def test_empty_feed_counts_as_failure(env, monkeypatch):
    monkeypatch.setattr(env.mod, 'fetch_url', lambda url: [])
    env.set_table('U2', '1.1.1.1')
    state = {'u2': {'primary_ips': ['1.1.1.1'], 'primary_ok_at': time.time()}}
    env.mod.check_watcher(watcher('u2', 'U2', type='urltable', url='https://f/y', staticEntries='2.2.2.2'), state)
    assert env.table('U2') == ['1.1.1.1', '2.2.2.2']


def test_missing_table_reported(env):
    env.set_dns({'h': ['1.1.1.1']})
    state = {}
    assert env.mod.check_watcher(watcher('w', 'Missing', hostnames='h'), state) is False
    assert 'not accessible' in state['w']['last_error']
