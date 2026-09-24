"""State persistence across processes, and daemon process control."""
import json
import os
import subprocess
import sys
import time

import pytest

from conftest import UUID1

HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harness.py')


def history(env):
    return [h['added'] for h in env.state()['w1']['history']]


def test_legacy_state_is_migrated(env):
    with open(env.mod.LEGACY_STATEFILE, 'w') as f:
        json.dump({'w1': {'history': [{'added': ['old']}]}}, f)
    with env.mod.locked_state() as state:
        assert state['w1']['history'][0]['added'] == ['old']
    assert os.path.exists(env.mod.STATEFILE)


def test_save_is_atomic(env):
    env.mod.save_state({'a': 1})
    assert not os.path.exists(env.mod.STATEFILE + '.tmp')
    assert env.state() == {'a': 1}


@pytest.fixture
def daemon_env(env, tmp_path):
    # get_pid() only trusts a PID whose command line mentions aliaserd
    link = tmp_path / 'aliaserd_harness.py'
    os.symlink(HARNESS, link)
    env.run = lambda *args: subprocess.run([sys.executable, str(link), env.path, *args],
                                           capture_output=True, text=True, timeout=30)
    env.write_config({'uuid': UUID1, 'name': 'w1', 'type': 'dns', 'hostnames': 'h',
                      'alias': 'T1', 'interval': 10})
    env.set_table('T1')
    yield env
    env.run('stop')


def wait_for(cond, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_daemon_and_refresh_both_keep_history(daemon_env):
    env = daemon_env
    env.set_dns({'h': ['4.4.4.10']})
    env.run('start')
    assert wait_for(lambda: env.table('T1') == ['4.4.4.10'])
    for n in range(11, 17):
        env.set_dns({'h': [f'4.4.4.{n}']})
        assert json.loads(env.run('refresh', UUID1).stdout)['changed'] is True
    time.sleep(1.5)  # several daemon ticks, each of which used to clobber the file
    added = history(env)
    assert added == [[f'4.4.4.{n}'] for n in range(10, 17)]


def test_single_instance_and_graceful_stop(daemon_env):
    env = daemon_env
    env.set_dns({'h': ['1.1.1.1']})
    env.run('start')
    assert wait_for(lambda: env.mod.get_pid() is not None)
    first = env.mod.get_pid()
    env.run('start')
    time.sleep(1)
    assert env.mod.get_pid() == first
    started = time.time()
    env.run('stop')
    assert env.mod.get_pid() is None
    assert time.time() - started < 5  # SIGTERM honoured, no SIGKILL escalation


def test_stale_pidfile_never_signals_other_process(daemon_env):
    env = daemon_env
    bystander = subprocess.Popen(['sleep', '60'])
    try:
        with open(env.mod.PIDFILE, 'w') as f:
            f.write(str(bystander.pid))
        assert env.mod.get_pid() is None
        env.run('stop')
        assert bystander.poll() is None
    finally:
        bystander.kill()
