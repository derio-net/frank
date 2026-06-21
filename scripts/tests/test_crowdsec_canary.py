"""Unit tests for the CrowdSec ban-pipeline canary eval logic.

The canary watches CrowdSec's own counters for the three historical silent-failure
signatures (rotation-blindness #594, docker-runtime parse break, lost-persistence
#583 crashloop). It scrapes the agent :6060/metrics once per run and compares to the
previous run's persisted sample (cross-run delta), pages Telegram on the 2nd
consecutive fail, and emits a heartbeat every run.

These tests feed canned Prometheus-text samples (real label shapes captured live,
agent v1.7.8) for each signature and assert the verdict. TDD: written before canary.py.
"""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CANARY = REPO / "clusters/hop/apps/crowdsec-canary/manifests/canary.py"

_spec = importlib.util.spec_from_file_location("canary", CANARY)
canary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canary)

CADDY_SRC = (
    "/var/log/containers/caddy-6cc4c6bdc4-4xbfk_caddy-system_"
    "caddy-6d830f5c8bd88546b1b1bf3696d7f2081a71fe6e9e58f98bf130c136cd205847.log"
)


def _sample(filesource, caddy_ok, caddy_ko=5):
    """Build a minimal but realistically-labelled agent /metrics text."""
    return f"""# HELP cs_filesource_hits_total Total lines read from file source.
# TYPE cs_filesource_hits_total counter
cs_filesource_hits_total{{acquis_type="containerd",datasource_type="file",source="{CADDY_SRC}"}} {filesource}
cs_info{{version="v1.7.8-63227459"}} 0
cs_node_hits_ok_total{{acquis_type="containerd",name="crowdsecurity/caddy-logs",source="{CADDY_SRC}",stage="s01-parse",type="file"}} {caddy_ok}
cs_node_hits_ko_total{{acquis_type="containerd",name="crowdsecurity/http-logs",source="{CADDY_SRC}",stage="s02-enrich",type="file"}} {caddy_ko}
"""


# --- parse / extract -------------------------------------------------------

def test_parse_metrics_skips_comments_and_extracts_value():
    m = canary.parse_metrics(_sample(1000, 950))
    assert "cs_filesource_hits_total" in m
    # comment/HELP/TYPE lines must not become series
    assert all(not k.startswith("#") for k in m)


def test_extract_signals_reads_filesource_and_caddy_parsed():
    sig = canary.extract_signals(canary.parse_metrics(_sample(1153, 1051)))
    assert sig["filesource"] == 1153
    assert sig["caddy_parsed"] == 1051
    assert sig["alive"] is True


def test_extract_signals_agent_down_is_not_alive():
    sig = canary.extract_signals(canary.parse_metrics("# no series\n"))
    assert sig["alive"] is False


# --- evaluate (the three checks) -------------------------------------------

def _sig(fs, ok):
    return canary.extract_signals(canary.parse_metrics(_sample(fs, ok)))


def test_evaluate_healthy_is_ok():
    v = canary.evaluate(_sig(1000, 950), _sig(1030, 978))
    assert v["ok"] is True
    assert v["failed_checks"] == []


def test_evaluate_frozen_acquisition_fails():
    # filesource delta 0 → rotation-blindness (#594)
    v = canary.evaluate(_sig(1000, 950), _sig(1000, 950))
    assert v["ok"] is False
    assert "acquisition" in v["failed_checks"]


def test_evaluate_parse_broken_fails():
    # filesource advances but caddy-logs parsed delta 0 → docker-runtime bug
    v = canary.evaluate(_sig(1000, 950), _sig(1030, 950))
    assert v["ok"] is False
    assert "parsing" in v["failed_checks"]


def test_evaluate_agent_down_fails():
    cur = canary.extract_signals(canary.parse_metrics("# nothing\n"))
    v = canary.evaluate(_sig(1000, 950), cur)
    assert v["ok"] is False
    assert "agent_alive" in v["failed_checks"]


def test_evaluate_bootstrap_no_prev_is_ok():
    v = canary.evaluate(None, _sig(1000, 950))
    assert v["ok"] is True
    assert v.get("bootstrap") is True


def test_evaluate_counter_reset_is_ok_not_acquisition_fail():
    # agent restart / Caddy pod roll -> cumulative counter goes backwards.
    # Must re-baseline (OK), NOT report a frozen acquisition.
    v = canary.evaluate(_sig(5000, 4800), _sig(30, 28))
    assert v["ok"] is True
    assert v["failed_checks"] == []
    assert v.get("reset") is True


# --- consecutive-fail gate -------------------------------------------------

def test_gate_pages_only_on_second_consecutive_fail():
    # first fail
    n, page = canary.update_gate(0, ok=False)
    assert (n, page) == (1, False)
    # second consecutive fail → page
    n, page = canary.update_gate(n, ok=False)
    assert (n, page) == (2, True)


def test_gate_resets_on_ok():
    n, page = canary.update_gate(2, ok=True)
    assert (n, page) == (0, False)


# --- telegram message safety ----------------------------------------------

def test_build_message_has_no_html_special_chars():
    v = {"ok": False, "failed_checks": ["acquisition", "parsing"],
         "deltas": {"filesource": 0, "caddy_parsed": 0}}
    msg = canary.build_message(v, fail_count=2)
    assert "<" not in msg and ">" not in msg and "&" not in msg


def test_telegram_notify_skips_when_creds_absent():
    # missing creds → no send, returns False, never raises
    assert canary.telegram_notify(None, None, "hi") is False


def test_clean_cred_strips_whitespace_and_newlines():
    # a trailing newline in a secret would 404 the Telegram URL (caught live 2026-06-21)
    assert canary._clean_cred("123456:ABCdef\n") == "123456:ABCdef"
    assert canary._clean_cred("  -1001234567  ") == "-1001234567"
    assert canary._clean_cred("\n \t") is None
    assert canary._clean_cred(None) is None


def test_telegram_notify_treats_whitespace_only_token_as_absent():
    # a whitespace-only token must not produce a bot<token>\n/sendMessage 404 — skip instead
    assert canary.telegram_notify("  \n", "123", "hi") is False
