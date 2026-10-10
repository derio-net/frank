"""cred_expiry: pure days-until-expiry verdict + the always-heartbeat/warn-on-threshold runner."""
from __future__ import annotations
import json

import pytest

from handlers import cred_expiry as ce

NOW_MS = 1_753_000_000_000          # fixed test clock
DAY_MS = 86_400_000


def _creds(days_out: float, refresh_token: str | None = "rt-abc123") -> str:
    # The REAL claude credentials.json nests the field under `claudeAiOauth`
    # (confirmed live 2026-07-22) — NOT top-level.
    #
    # `refresh_token` MUST default to a non-empty value: this fixture used to hard-code
    # `""`, which is precisely the live-BROKEN shape (2026-07-23), so the suite asserted
    # that a dead credential was healthy. Pass refresh_token="" / None to build the
    # broken shape deliberately.
    oauth = {"expiresAt": 0,
             "refreshTokenExpiresAt": int(NOW_MS + days_out * DAY_MS)}
    if refresh_token is not None:
        oauth["refreshToken"] = refresh_token
    return json.dumps({"claudeAiOauth": oauth})


def _creds_flat(days_out: float) -> str:
    # Defensive fallback: a top-level field must also work (format may vary).
    return json.dumps({"refreshTokenExpiresAt": int(NOW_MS + days_out * DAY_MS), "expiresAt": 0})


def test_reads_nested_and_flat_field():
    assert ce.evaluate_expiry(_creds(5), NOW_MS).days_left == 5        # nested claudeAiOauth
    assert ce.evaluate_expiry(_creds_flat(5), NOW_MS).days_left == 5   # top-level fallback


# --- evaluate_expiry: arithmetic + tiers -------------------------------------

@pytest.mark.parametrize("days,expected_tier", [
    (30, "ok"), (8, "ok"), (7, "notice"), (5, "notice"),
    (3, "soon"), (2, "soon"), (1, "urgent"), (0, "expired"), (-5, "expired"),
])
def test_tier_boundaries(days, expected_tier):
    v = ce.evaluate_expiry(_creds(days), NOW_MS)
    assert v.days_left == days                       # floor of an exact-day offset
    assert v.tier == expected_tier


def test_days_left_floor():
    # 6.9 days out floors to 6 (still within notice)
    v = ce.evaluate_expiry(_creds(6.9), NOW_MS)
    assert v.days_left == 6 and v.tier == "notice"


def test_should_warn_iff_not_ok():
    assert ce.evaluate_expiry(_creds(8), NOW_MS).should_warn is False
    for d in (7, 3, 1, 0, -5):
        assert ce.evaluate_expiry(_creds(d), NOW_MS).should_warn is True


# --- message wording + plain-text safety -------------------------------------

def test_message_escalates_and_is_plain_text():
    msgs = {d: ce.evaluate_expiry(_creds(d), NOW_MS).message for d in (7, 3, 1, 0)}
    # distinct wording per band
    assert len({msgs[7], msgs[3], msgs[1], msgs[0]}) == 4
    assert "EXPIRED" in msgs[0]
    # never any HTML-sensitive char (Telegram contact is plain-text)
    for m in msgs.values():
        assert "<" not in m and ">" not in m and "&" not in m


# --- broken input → error tier, never a silent skip --------------------------

# NB: 'Infinity'/'NaN' are accepted by Python's json.loads by default, and
# math.floor(inf|nan) RAISES — these would crash the runner before the heartbeat
# unless guarded. They MUST land on the error tier, not an exception.
@pytest.mark.parametrize("bad", [
    None, "{ not json", "{}", '{"refreshTokenExpiresAt": "nope"}',
    '{"refreshTokenExpiresAt": true}',        # bool is not a valid epoch
    '{"refreshTokenExpiresAt": Infinity}',    # math.floor(inf) raises
    '{"refreshTokenExpiresAt": NaN}',         # math.floor(nan) raises
    '{"refreshTokenExpiresAt": 1e18}',        # finite but out-of-range: _now_iso year>9999
    '{"refreshTokenExpiresAt": -1e18}',       # out-of-range negative
])
def test_broken_cred_is_error_tier_and_warns(bad):
    v = ce.evaluate_expiry(bad, NOW_MS)
    assert v.tier == "error"
    assert v.days_left is None
    assert v.should_warn is True
    assert "<" not in v.message and ">" not in v.message and "&" not in v.message


# --- blanked tokens: a healthy CLOCK does not mean a usable CREDENTIAL ---------

# Incident 2026-07-23: the C&C bot answered every DM with the deterministic-snapshot
# fallback for ~14h. The credential file was intact and its clock read 26 days out, but
# BOTH tokens had been blanked to "" (claude clears them when a refresh fails, leaving
# the metadata behind). `claude -p` said "Failed to authenticate: OAuth session expired
# and could not be refreshed", the tmux pane died on launch, every turn timed out — and
# this check reported `tier=ok WARN=False`. The clock is necessary, never sufficient.

@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_or_missing_refresh_token_is_error_despite_healthy_clock(blank):
    v = ce.evaluate_expiry(_creds(26, refresh_token=blank), NOW_MS)
    assert v.tier == "error"          # NOT "ok" — this is the whole bug
    assert v.should_warn is True
    assert v.days_left is None


@pytest.mark.parametrize("bad", [0, 123, True, [], {}])
def test_non_string_refresh_token_is_error(bad):
    doc = json.loads(_creds(26))
    doc["claudeAiOauth"]["refreshToken"] = bad
    v = ce.evaluate_expiry(json.dumps(doc), NOW_MS)
    assert v.tier == "error" and v.should_warn is True


def test_blank_token_message_names_the_real_fault_and_is_plain_text():
    m = ce.evaluate_expiry(_creds(26, refresh_token=""), NOW_MS).message
    # must not read as "expires in 26 days" — the operator action is re-login NOW
    assert "26" not in m
    assert "login" in m.lower()
    assert "<" not in m and ">" not in m and "&" not in m


def test_blank_token_heartbeat_is_stable_single_line_error():
    hb = ce.evaluate_expiry(_creds(26, refresh_token=""), NOW_MS).heartbeat
    assert "\n" not in hb
    assert hb.startswith("cred-expiry-check")   # the Grafana dead-man rule matches this
    assert "tier=error" in hb


def test_healthy_token_with_far_clock_is_still_ok():
    # the fix must not turn every healthy credential into an error
    v = ce.evaluate_expiry(_creds(26), NOW_MS)
    assert v.tier == "ok" and v.should_warn is False and v.days_left == 26


def test_flat_fallback_shape_keeps_clock_only_semantics():
    # The top-level shape is a defensive tolerance for a schema we have never seen live;
    # we cannot demand a token field we do not know the name of. Clock-only, as before.
    assert ce.evaluate_expiry(_creds_flat(26), NOW_MS).tier == "ok"


# --- heartbeat line ----------------------------------------------------------

def test_heartbeat_is_stable_single_line():
    v = ce.evaluate_expiry(_creds(5), NOW_MS)
    assert "\n" not in v.heartbeat
    assert v.heartbeat.startswith("cred-expiry-check")
    assert "days_left=5" in v.heartbeat and "tier=notice" in v.heartbeat


def test_heartbeat_error_says_unknown():
    v = ce.evaluate_expiry(None, NOW_MS)
    assert "days_left=unknown" in v.heartbeat and "tier=error" in v.heartbeat


# --- run_cred_check wiring: always heartbeat, warn on threshold, never crash --

@pytest.fixture(autouse=True)
def _state(monkeypatch, tmp_path):
    # The de-dup state file must never touch the real /home/agent cache.
    p = tmp_path / "state" / "cred-expiry-last-warn"
    monkeypatch.setattr(ce, "STATE_PATH", str(p))
    return p


@pytest.fixture
def wired(monkeypatch, capsys):
    sent = []

    def _send(text, *a, **k):
        sent.append(text)
        return {"ok": True}
    monkeypatch.setattr(ce.bridge, "tg_send", _send)
    return sent


def test_run_prints_heartbeat_and_warns_when_expiring(wired, monkeypatch, capsys):
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds(2))    # 2 days → soon → warn
    ce.run_cred_check(now_ms=NOW_MS)
    out = capsys.readouterr().out
    assert "cred-expiry-check" in out and "tier=soon" in out    # heartbeat printed
    assert len(wired) == 2 and "expire" in wired[0].lower()      # warning + command sent


def test_run_prints_heartbeat_no_warn_when_ok(wired, monkeypatch, capsys):
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds(20))   # healthy → no warn
    ce.run_cred_check(now_ms=NOW_MS)
    assert "cred-expiry-check" in capsys.readouterr().out
    assert wired == []                                           # no Telegram warning


def test_run_swallows_tg_send_error_but_still_heartbeats(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("telegram down")
    monkeypatch.setattr(ce.bridge, "tg_send", boom)
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds(1))    # would warn
    ce.run_cred_check(now_ms=NOW_MS)                                          # must NOT raise
    assert "cred-expiry-check" in capsys.readouterr().out       # heartbeat still printed


def test_run_missing_file_warns(wired, monkeypatch, capsys):
    monkeypatch.setattr(ce, "_read_cred", lambda: None)         # FileNotFound → None
    ce.run_cred_check(now_ms=NOW_MS)
    assert "tier=error" in capsys.readouterr().out
    assert len(wired) == 2                                       # error → warns (+ command)


def test_read_cred_swallows_non_filenotfound(monkeypatch, tmp_path):
    # A directory / permission error must not raise out of _read_cred (which would
    # crash the runner before the heartbeat) — it returns None → error tier.
    monkeypatch.setattr(ce, "CRED_PATH", str(tmp_path))          # a dir → IsADirectoryError
    assert ce._read_cred() is None


def test_read_cred_swallows_invalid_utf8(monkeypatch, tmp_path):
    # UnicodeDecodeError is a ValueError, NOT an OSError — it must still be swallowed.
    p = tmp_path / "creds.json"
    p.write_bytes(b"\xff\xfe not utf-8")
    monkeypatch.setattr(ce, "CRED_PATH", str(p))
    assert ce._read_cred() is None


def test_run_out_of_range_epoch_is_error_not_crash(wired, monkeypatch, capsys):
    # A finite-but-huge epoch (e.g. seconds*1000) drove _now_iso to ValueError. It must
    # go through the REAL code path to an error heartbeat + warning, never crash.
    monkeypatch.setattr(ce, "_read_cred", lambda: '{"refreshTokenExpiresAt": 1e18}')
    ce.run_cred_check(now_ms=NOW_MS)                            # must NOT raise
    assert "tier=error" in capsys.readouterr().out
    assert len(wired) == 2                                       # warning + command


def test_run_never_crashes_and_always_heartbeats_on_unexpected_error(wired, monkeypatch, capsys):
    # Belt-and-suspenders: even if evaluate_expiry blows up unexpectedly, the runner
    # must still print a heartbeat (the dead-man keys on it) and warn — never crash.
    monkeypatch.setattr(ce, "_read_cred", lambda: "{}")
    monkeypatch.setattr(ce, "evaluate_expiry", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    ce.run_cred_check(now_ms=NOW_MS)                             # must NOT raise
    out = capsys.readouterr().out
    assert "cred-expiry-check" in out and "tier=error" in out   # heartbeat still emitted
    assert len(wired) == 2                                       # and warned (+ command)


# --- the re-login instruction is a copy-pastable command -----------------------

# The old wording ("attach the agent tmux and run /login") gave no command, and
# `tmux attach` lands in a LIVE driver session (alert-agent-digest / -surge), not a
# login shell. The fix: every warning points at a follow-up message that holds ONLY
# the command, so a long-press → Copy on Telegram yields exactly what to paste.

def test_login_cmd_is_a_single_plain_line_into_the_agent_container():
    cmd = ce.LOGIN_CMD
    assert "\n" not in cmd
    assert "<" not in cmd and ">" not in cmd and "&" not in cmd
    assert cmd.startswith("kubectl exec -it -n alert-agent deploy/alert-agent -c agent -- ")
    assert cmd.endswith("claude auth login")


@pytest.mark.parametrize("creds", [_creds(7), _creds(3), _creds(1), _creds(0),
                                   _creds(26, refresh_token=""), None])
def test_every_warning_points_at_the_command_not_tmux(creds):
    m = ce.evaluate_expiry(creds, NOW_MS).message
    assert "tmux" not in m.lower()
    assert "next message" in m.lower()


@pytest.mark.parametrize("creds", [_creds(2), None])
def test_run_sends_warning_then_bare_command(wired, monkeypatch, capsys, creds):
    monkeypatch.setattr(ce, "_read_cred", lambda: creds)
    ce.run_cred_check(now_ms=NOW_MS)
    assert len(wired) == 2
    assert "next message" in wired[0].lower()
    assert wired[1] == ce.LOGIN_CMD                              # nothing else to trim


def test_run_ok_sends_no_command(wired, monkeypatch, capsys):
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds(20))
    ce.run_cred_check(now_ms=NOW_MS)
    assert wired == []


# --- once-a-day warning de-dup (frank#746) -------------------------------------
# The check runs 6-hourly (03/09/15/21 UTC) so the dead-man heartbeat window can be
# 13h, but the WARNING must stay once per warning-day per tier. A warning-day runs
# 09:00 to 09:00 UTC (key = date(now - 9h)), so the 03:00 run joins the previous day.

def _at(day: int, hour: int, minute: int = 0) -> int:
    from datetime import datetime, timezone
    return int(datetime(2026, 7, day, hour, minute, tzinfo=timezone.utc).timestamp() * 1000)


def _creds_at(now_ms: int, days_out: float) -> str:
    return json.dumps({"claudeAiOauth": {"expiresAt": 0, "refreshToken": "rt",
                                         "refreshTokenExpiresAt": int(now_ms + days_out * DAY_MS)}})


def test_warn_key_is_utc_date_minus_nine_hours_and_tier():
    assert ce._warn_key("soon", _at(10, 9)) == "2026-07-10:soon"
    assert ce._warn_key("soon", _at(10, 15)) == "2026-07-10:soon"
    assert ce._warn_key("soon", _at(10, 21)) == "2026-07-10:soon"
    assert ce._warn_key("soon", _at(11, 3)) == "2026-07-10:soon"     # 03:00 = previous warning-day
    assert ce._warn_key("soon", _at(11, 8, 59)) == "2026-07-10:soon"  # one minute before the roll
    assert ce._warn_key("soon", _at(11, 9)) == "2026-07-11:soon"
    assert ce._warn_key("error", _at(11, 9)) == "2026-07-11:error"


def test_same_warning_day_and_tier_sends_once(wired, monkeypatch, capsys):
    # 2.9 days out at 09:00 stays in the "soon" tier (2.4 days) through the 21:00 run
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 2.9))
    for h in (9, 15, 21):
        ce.run_cred_check(now_ms=_at(10, h))
    assert len(wired) == 2                                   # one warning + command, not six
    assert capsys.readouterr().out.count("cred-expiry-check") == 3   # heartbeat EVERY run


def test_next_warning_day_warns_again(wired, monkeypatch):
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 2))
    ce.run_cred_check(now_ms=_at(10, 9))
    ce.run_cred_check(now_ms=_at(11, 9))
    assert len(wired) == 4


def test_03_utc_run_belongs_to_previous_warning_day(wired, monkeypatch):
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 2.9))
    ce.run_cred_check(now_ms=_at(10, 21))
    ce.run_cred_check(now_ms=_at(11, 3))                     # same warning-day → silent
    assert len(wired) == 2


def test_tier_escalation_same_day_warns(wired, monkeypatch):
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 5))      # notice
    ce.run_cred_check(now_ms=_at(10, 9))
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 15), 2))     # soon
    ce.run_cred_check(now_ms=_at(10, 15))
    assert len(wired) == 4


def test_failed_send_does_not_record_key_so_next_run_warns(monkeypatch, capsys):
    calls = []
    # bridge.tg_send returns {"ok": False} on HTTP errors instead of raising
    monkeypatch.setattr(ce.bridge, "tg_send",
                        lambda text, *a, **k: calls.append(text) or {"ok": False})
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 2))
    ce.run_cred_check(now_ms=_at(10, 9))
    assert not __import__("os").path.exists(ce.STATE_PATH)
    ce.run_cred_check(now_ms=_at(10, 15))
    assert len(calls) == 4


def test_second_send_failing_also_leaves_key_unwritten(monkeypatch):
    results = iter([{"ok": True}, {"ok": False}, {"ok": True}, {"ok": True}])
    monkeypatch.setattr(ce.bridge, "tg_send", lambda *a, **k: next(results))
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 2))
    ce.run_cred_check(now_ms=_at(10, 9))
    assert not __import__("os").path.exists(ce.STATE_PATH)


def test_non_dict_send_result_does_not_record_key(monkeypatch):
    monkeypatch.setattr(ce.bridge, "tg_send", lambda *a, **k: None)
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 2))
    ce.run_cred_check(now_ms=_at(10, 9))
    assert not __import__("os").path.exists(ce.STATE_PATH)


def test_unreadable_state_warns(wired, monkeypatch, tmp_path):
    d = tmp_path / "statedir"
    d.mkdir()
    monkeypatch.setattr(ce, "STATE_PATH", str(d))            # a directory → read error
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 2))
    ce.run_cred_check(now_ms=_at(10, 9))
    assert len(wired) == 2


def test_unwritable_state_warns_and_heartbeat_prints(wired, monkeypatch, tmp_path, capsys):
    f = tmp_path / "afile"
    f.write_text("x")
    monkeypatch.setattr(ce, "STATE_PATH", str(f / "sub" / "state"))   # parent is a file
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 2))
    ce.run_cred_check(now_ms=_at(10, 9))                     # must NOT raise
    assert len(wired) == 2
    assert "cred-expiry-check" in capsys.readouterr().out


def test_ok_tier_never_touches_state(wired, monkeypatch):
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds_at(_at(10, 9), 20))
    ce.run_cred_check(now_ms=_at(10, 9))
    assert not __import__("os").path.exists(ce.STATE_PATH)
