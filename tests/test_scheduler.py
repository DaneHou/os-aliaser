"""Scheduling: restore on start, slow sources, dependent watchers."""
import concurrent.futures
import threading
import time

import pytest

from conftest import watcher


@pytest.fixture
def pool():
    p = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    yield p
    p.shutdown(wait=False, cancel_futures=True)


def run_until(scheduler, watchers, cond, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        scheduler.tick(watchers, 0)
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_restore_refills_empty_tables_only(env):
    env.mod.save_state({
        'a': {'alias': 'TA', 'current_ips': ['1.1.1.1', '2.2.2.2']},
        'b': {'alias': 'TB', 'current_ips': ['3.3.3.3']},
        'c': {'alias': 'OLD', 'current_ips': ['4.4.4.4']},  # target changed since
    })
    env.set_table('TA')
    env.set_table('TB', '9.9.9.9')
    env.set_table('TC')
    env.mod.restore_tables([watcher('a', 'TA'), watcher('b', 'TB'), watcher('c', 'TC')])
    assert env.table('TA') == ['1.1.1.1', '2.2.2.2']
    assert env.table('TB') == ['9.9.9.9']
    assert env.table('TC') == []


def test_slow_feed_does_not_block_other_watchers(env, monkeypatch, pool):
    release = threading.Event()

    def slow_fetch(url):
        release.wait(10)
        return ['8.8.8.8']
    monkeypatch.setattr(env.mod, 'fetch_url', slow_fetch)
    env.set_dns({'h': ['1.1.1.1']})
    env.set_table('TU')
    env.set_table('TD')
    watchers = [watcher('slow', 'TU', type='urltable', url='https://slow/x'),
                watcher('fast', 'TD', hostnames='h')]
    sched = env.mod.Scheduler(pool)
    try:
        assert run_until(sched, watchers, lambda: env.table('TD') == ['1.1.1.1'], timeout=2)
        assert env.table('TU') == []  # still waiting on the feed
    finally:
        release.set()
    assert run_until(sched, watchers, lambda: env.table('TU') == ['8.8.8.8'])


def test_dependent_watcher_updates_immediately(env, pool):
    env.set_dns({'h': ['2.2.2.2']})
    env.set_table('TA')
    env.set_table('TB')
    watchers = [watcher('A', 'TA', staticEntries='1.1.1.1', includeAliases='TB', interval=3600),
                watcher('B', 'TB', hostnames='h', interval=3600)]
    sched = env.mod.Scheduler(pool)
    assert run_until(sched, watchers, lambda: '2.2.2.2' in env.table('TA'))

    env.set_dns({'h': ['2.2.2.3']})
    sched.next_due['B'] = 0  # B's timer fires; A's is an hour away
    assert run_until(sched, watchers, lambda: env.table('TA') == ['1.1.1.1', '2.2.2.3'], timeout=3)


def test_edited_watcher_result_is_discarded(env, pool):
    env.set_dns({'h': ['1.1.1.1'], 'h2': ['2.2.2.2']})
    env.set_table('T')
    old = [watcher('w', 'T', hostnames='h')]
    sched = env.mod.Scheduler(pool)
    sched.tick(old, 0)                      # lookup for the old config starts
    new = [watcher('w', 'T', hostnames='h2')]
    assert run_until(sched, new, lambda: env.table('T') == ['2.2.2.2'])
