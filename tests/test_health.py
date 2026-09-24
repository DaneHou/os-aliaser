"""`aliaserd.py health`: what gets reported to Monit."""
import pytest

from conftest import UUID1, watcher

NOW = 1_000_000


def problems(env, state, running=True, **kw):
    return env.mod.health_problems([watcher('w', 'T', interval=60, **kw)], state, running, now=NOW)


def test_healthy(env):
    assert problems(env, {'w': {'last_check': NOW - 30}}) == []


def test_daemon_down(env):
    assert problems(env, {}, running=False) == ['daemon is not running']


def test_repeated_failures_reported_single_failure_not(env):
    assert problems(env, {'w': {'last_check': NOW, 'consecutive_errors': 2}}) == []
    [p] = problems(env, {'w': {'last_check': NOW, 'consecutive_errors': 3, 'last_error': 'no results from h'}})
    assert p == 'w: 3 failures in a row: no results from h'


def test_alerts_reported(env):
    state = {'w': {'last_check': NOW, 'alerts': [{'type': 'empty', 'message': 'Table went from 5 entries to 0'}]}}
    assert problems(env, state) == ['w: Table went from 5 entries to 0']


def test_stale_watcher_reported_but_not_before_first_check(env):
    assert problems(env, {'w': {'last_check': 0}}) == []
    [p] = problems(env, {'w': {'last_check': NOW - 600}})
    assert 'not checked for 600s' in p


def test_cmd_health_exit_codes(env, monkeypatch, capsys):
    env.write_config({'uuid': UUID1, 'name': 'w', 'alias': 'T', 'interval': 60})
    monkeypatch.setattr(env.mod, 'get_pid', lambda: 123)
    env.mod.cmd_health()
    assert capsys.readouterr().out.startswith('OK: 1 watcher')

    monkeypatch.setattr(env.mod, 'get_pid', lambda: None)
    with pytest.raises(SystemExit) as exc:
        env.mod.cmd_health()
    assert exc.value.code == 1
    assert 'daemon is not running' in capsys.readouterr().out
