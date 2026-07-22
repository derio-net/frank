"""cred_expiry: pure days-until-expiry verdict + the always-heartbeat/warn-on-threshold runner."""
from __future__ import annotations
import json

import pytest

from handlers import cred_expiry as ce

NOW_MS = 1_753_000_000_000          # fixed test clock
DAY_MS = 86_400_000


def _creds(days_out: float) -> str:
    # The REAL claude credentials.json nests the field under `claudeAiOauth`
    # (confirmed live 2026-07-22) — NOT top-level.
    return json.dumps({"claudeAiOauth": {
        "refreshToken": "", "expiresAt": 0,
        "refreshTokenExpiresAt": int(NOW_MS + days_out * DAY_MS)}})


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

@pytest.fixture
def wired(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(ce.bridge, "tg_send", lambda text, *a, **k: sent.append(text))
    return sent


def test_run_prints_heartbeat_and_warns_when_expiring(wired, monkeypatch, capsys):
    monkeypatch.setattr(ce, "_read_cred", lambda: _creds(2))    # 2 days → soon → warn
    ce.run_cred_check(now_ms=NOW_MS)
    out = capsys.readouterr().out
    assert "cred-expiry-check" in out and "tier=soon" in out    # heartbeat printed
    assert len(wired) == 1 and "expire" in wired[0].lower()      # warning sent


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
    assert len(wired) == 1                                       # error → warns


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
    assert len(wired) == 1


def test_run_never_crashes_and_always_heartbeats_on_unexpected_error(wired, monkeypatch, capsys):
    # Belt-and-suspenders: even if evaluate_expiry blows up unexpectedly, the runner
    # must still print a heartbeat (the dead-man keys on it) and warn — never crash.
    monkeypatch.setattr(ce, "_read_cred", lambda: "{}")
    monkeypatch.setattr(ce, "evaluate_expiry", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    ce.run_cred_check(now_ms=NOW_MS)                             # must NOT raise
    out = capsys.readouterr().out
    assert "cred-expiry-check" in out and "tier=error" in out   # heartbeat still emitted
    assert len(wired) == 1                                       # and warned
