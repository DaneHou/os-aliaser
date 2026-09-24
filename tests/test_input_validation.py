"""Remote/config input must never reach pfctl unvalidated."""
import io

from conftest import UUID1, watcher


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


def serve(env, monkeypatch, body):
    monkeypatch.setattr(env.mod.urllib.request, 'urlopen',
                        lambda req, timeout=30: FakeResponse(body))


def test_feed_keeps_only_valid_ips_and_uses_file(env, monkeypatch):
    serve(env, monkeypatch,
          b"1.2.3.4\n-k0.0.0.0/0\n-f/tmp/1.conf\n<img src=x onerror=alert(1.1)>\n"
          b"10.0.0.5/8 ; SBL123\n2001:db8::1/128\n# comment\n")
    env.set_table('U1')
    assert env.mod.check_watcher(watcher('u1', 'U1', type='urltable', url='https://f/x'), {})
    assert env.table('U1') == ['1.2.3.4', '10.0.0.0/8', '2001:db8::1']
    # Addresses go through a file, never argv
    assert env.pfctl_calls()[-1].split()[:5] == ['-t', 'U1', '-T', 'replace', '-f']


def test_normalized_entries_match_pfctl_show(env, monkeypatch):
    serve(env, monkeypatch, b"1.2.3.4/32\n10.0.0.0/8\n")
    w = watcher('u1', 'U1', type='urltable', url='https://f/x')
    env.set_table('U1')
    state = {}
    assert env.mod.check_watcher(w, state) is True
    assert env.mod.check_watcher(w, state) is False  # no churn on the next run


def test_oversize_feed_rejected(env, monkeypatch):
    serve(env, monkeypatch, b'1.1.1.1\n' * (env.mod.MAX_FEED_BYTES // 8 + 1))
    assert env.mod.fetch_url('https://f/big') is None


def test_invalid_static_entries_dropped(env):
    env.set_dns({'h': ['3.3.3.3']})
    env.set_table('T7')
    env.mod.check_watcher(watcher('w7', 'T7', hostnames='h', staticEntries='9.9.9.9, -kfoo, 1.2.3.999'), {})
    assert env.table('T7') == ['3.3.3.3', '9.9.9.9']


def test_reserved_and_invalid_target_tables(env):
    ok = env.mod.is_valid_target_table
    assert ok('MyAlias')
    for bad in ['bogons', 'bogonsv6', 'sshlockout', 'virusprot', '__lan_network', '-x', 'a' * 32, '']:
        assert not ok(bad), bad


def test_read_config_skips_reserved_target(env):
    env.write_config({'uuid': UUID1, 'name': 'bad', 'alias': 'sshlockout', 'interval': 30})
    watchers, _, _ = env.mod.read_config()
    assert watchers == []


def test_bad_interval_only_affects_that_watcher(env):
    env.write_config({'uuid': UUID1, 'name': 'a', 'alias': 'TA', 'interval': 'abc'},
                     {'uuid': UUID1, 'name': 'b', 'alias': 'TB', 'interval': 60})
    watchers, _, _ = env.mod.read_config()
    assert [(w['name'], w['interval']) for w in watchers] == [('a', 30), ('b', 60)]


def test_include_cycles_detected(env):
    ws = [watcher('A', 'TA', includeAliases='TB'),
          watcher('B', 'TB', includeAliases='TA,TC'),
          watcher('C', 'TC'),
          watcher('S', 'TS', includeAliases='TS')]
    env.mod.mark_include_cycles(ws)
    assert [w['cyclicIncludes'] for w in ws] == [['TB'], ['TA'], [], ['TS']]


def test_refresh_rejects_non_uuid(env, capsys):
    env.mod.cmd_refresh('$(id)')
    assert 'invalid uuid' in capsys.readouterr().out


def test_log_level_setting_applies_syslog_mask(env):
    syslog = env.mod.syslog
    for level, highest_shown, first_hidden in [('error', syslog.LOG_ERR, syslog.LOG_WARNING),
                                               ('warn', syslog.LOG_NOTICE, syslog.LOG_INFO),
                                               ('debug', syslog.LOG_DEBUG, None)]:
        env.write_config(general=f'<logLevel>{level}</logLevel>')
        env.mod.read_config()
        mask = syslog.setlogmask(0)  # 0 = query without changing
        assert mask & syslog.LOG_MASK(highest_shown), level
        if first_hidden is not None:
            assert not mask & syslog.LOG_MASK(first_hidden), level
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))


def test_empty_interval_uses_default_interval(env):
    env.write_config({'uuid': UUID1, 'name': 'a', 'alias': 'TA', 'interval': ''},
                     {'uuid': UUID1, 'name': 'b', 'alias': 'TB', 'interval': 5},
                     general='<defaultInterval>120</defaultInterval>')
    watchers, _, _ = env.mod.read_config()
    # empty -> default; below the minimum -> clamped
    assert [(w['name'], w['interval']) for w in watchers] == [('a', 120), ('b', 10)]
