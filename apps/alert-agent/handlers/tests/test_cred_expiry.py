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
