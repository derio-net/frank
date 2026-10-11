"""Guard: every Grafana Telegram receiver pins ``parse_mode: None``.

grafana/alerting receivers/telegram/v1/config.go:84-86 falls back to HTML when
parse_mode is unset ("None" maps to plain text). A live receivers/test probe on
2026-10-10 returned Telegram 400 for unset and ok for None with a bare ``<`` in
the text (frank#799). So "unset" is NOT plain text; it must be explicit.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CM = REPO / "apps/grafana-alerting/manifests/contact-points-cm.yaml"


def _telegram_receivers():
    cm = yaml.safe_load(CM.read_text())
    doc = yaml.safe_load(cm["data"]["contact-points.yaml"])
    return [
        r
        for cp in doc.get("contactPoints", [])
        for r in cp.get("receivers", [])
        if r.get("type") == "telegram"
    ]


def test_every_telegram_receiver_pins_parse_mode_none():
    receivers = _telegram_receivers()
    assert receivers, f"no telegram receiver found in {CM}"
    for r in receivers:
        assert r.get("settings", {}).get("parse_mode") == "None", (
            f"receiver {r.get('uid')} must set parse_mode: None. An UNSET value "
            "falls back to HTML (grafana/alerting receivers/telegram/v1/config.go:84-86); "
            "the 2026-10-10 probe returned Telegram 400 for unset and ok for None "
            "with a bare '<' (frank#799)."
        )
