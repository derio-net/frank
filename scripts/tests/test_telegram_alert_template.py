"""Guard: the Telegram contact point renders through the compact ``frank-telegram`` template.

Spec: docs/superpowers/specs/2026-10-22--obs--telegram-alert-brevity-design.md (R1-R9).
Grafana's default Telegram message dumps the Value line, every label and a ~900-char
silence URL; the compact template leads with summary + runbook instead. These checks
are structural - the rendered output is proven pre-merge against Grafana's own
templates/test endpoint (recorded in the PR).
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CM = REPO / "apps/grafana-alerting/manifests/contact-points-cm.yaml"

ACTION = re.compile(r"\{\{.*?\}\}", re.S)


def _doc():
    cm = yaml.safe_load(CM.read_text())
    return yaml.safe_load(cm["data"]["contact-points.yaml"])


def _template_entry():
    templates = _doc().get("templates")
    assert isinstance(templates, list) and len(templates) == 1, (
        f"{CM} must carry a top-level `templates:` list with exactly one entry"
    )
    return templates[0]


def _template_text():
    return _template_entry()["template"]


def _receiver(contact_point):
    for cp in _doc().get("contactPoints", []):
        if cp.get("name") == contact_point:
            (r,) = cp["receivers"]
            return r
    raise AssertionError(f"contact point {contact_point!r} not found in {CM}")


def test_template_entry_defines_the_three_templates():
    entry = _template_entry()
    assert entry.get("orgId") == 1
    assert entry.get("name") == "frank-telegram"
    text = entry["template"]
    for name in ("frank.telegram.message", "frank.telegram.firing", "frank.telegram.resolved"):
        assert re.search(r'\{\{-?\s*define\s+"' + re.escape(name) + r'"', text), (
            f"template must define {name!r}"
        )


def test_telegram_receiver_uses_the_template_and_stays_plain_text():
    settings = _receiver("Telegram - Willikins")["settings"]
    assert settings.get("message") == '{{ template "frank.telegram.message" . }}'
    assert settings.get("parse_mode") == "None"  # R7; see test_telegram_parse_mode_explicit.py


def test_template_never_dumps_labels_value_or_all_label_silence_url():
    text = _template_text()
    for forbidden in (".Labels.SortedPairs", ".SilenceURL", ".ValueString", ".Annotations.SortedPairs"):
        assert forbidden not in text, f"R2: template must not use {forbidden}"


def test_template_adds_no_markup_outside_actions():
    # R7: parse_mode None means plain text; markup would print literally.
    literal = ACTION.sub("", _template_text())
    # The silence matcher's label name is a literal URL token, not markup.
    literal = literal.replace("__alert_rule_uid__%3D", "")
    for markup in ("<b>", "<i>", "*", "_"):
        assert markup not in literal, f"R7: template literal text must not contain {markup!r}"


def test_template_has_no_dollar_and_no_external_url():
    text = _template_text()
    # R9: provisioning env interpolation expands $NAME in this file.
    assert "$" not in text, "R9: template text must contain no '$' at all"
    assert ".ExternalURL" not in text


def test_template_carries_the_links_caps_and_headers():
    text = _template_text()
    for needle in (
        "__alert_rule_uid__%3D",
        "/alerting/list",
        "slice",
        "more firing",
        "more resolved",
        "🔥 FIRING · ",
        "✅ RESOLVED · ",
    ):
        assert needle in text, f"template must contain {needle!r}"


IDENTITY_ORDER = (
    "namespace",
    "workload",
    "deployment",
    "statefulset",
    "daemonset",
    "cronjob",
    "node",
    "persistentvolumeclaim",
    "pod",
)


def test_identity_labels_appear_in_r3_order():
    text = _template_text()
    positions = []
    for label in IDENTITY_ORDER:
        m = re.search(r"\.Labels\." + label + r"\b", text)
        assert m, f"R3: template must reference .Labels.{label}"
        positions.append(m.start())
    assert positions == sorted(positions), f"R3: identity labels must appear in order {IDENTITY_ORDER}"


def _is_ksm_guard(action):
    return ".Labels.job" in action and '"kube-state-metrics"' in action


def test_pod_label_only_inside_a_kube_state_metrics_branch():
    """Walk the actions with a block stack; every .Labels.pod must sit under a job/KSM check."""
    text = _template_text()
    stack = []  # list of lists of condition actions for the open blocks
    seen = 0
    for m in ACTION.finditer(text):
        action = m.group(0)
        body = action.strip("{}-").strip()
        if body.startswith("/*"):
            continue
        keyword = body.split(None, 1)[0] if body else ""
        if keyword in ("if", "with", "range", "define", "block"):
            stack.append([action])
        elif keyword == "else":
            if stack:
                stack[-1].append(action)
        elif keyword == "end":
            if stack:
                stack.pop()
        if re.search(r"\.Labels\.pod\b", action):
            seen += 1
            guarded = _is_ksm_guard(action) or any(
                _is_ksm_guard(cond) for frame in stack for cond in frame
            )
            assert guarded, f"R3: {action!r} references .Labels.pod outside a job != kube-state-metrics branch"
    assert seen, "R3: template must reference .Labels.pod (non-KSM alerts)"


def test_webhook_receivers_keep_their_json_payloads():
    for name in ("Health Bridge Webhook", "AI Helper Webhook"):
        settings = _receiver(name).get("settings", {})
        assert "message" not in settings, f"R8: {name} must keep Grafana's JSON payload (no message)"
