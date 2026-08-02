"""Tripwires for the feature-health alert folder in
`apps/grafana-alerting/manifests/alert-rules-cm.yaml`.

Eleven layer-tracker rules ask `kube_pod_status_ready{condition="true"} < 1`,
which is a question about *pods* when the alert means to ask about
*capabilities*. Those two questions diverge exactly when pods are cattle: a
terminal pod (`Succeeded` or `Failed`) can never become Ready, Kubernetes does
not garbage-collect terminal pods below `--terminated-pod-gc-threshold`
(default 12500), and kube-state-metrics therefore keeps exporting a NotReady
series for it forever. On 2026-08-02 a control-plane rolling reboot left 47
`NodeShutdown` tombstones behind and produced 48 firing alerts against a
completely healthy cluster.

`layer-25-cicd-down` was migrated onto
`kube_deployment_status_replicas_unavailable` on 2026-05-14 for the same
reason (Tekton task pods accumulating in Completed state) — this file guards
finishing that job for the rest.

Two kinds of guard live here:

* the **regression tripwire** (`test_no_feature_health_rule_uses_pod_readiness`),
  which asserts the defect is gone. It is `xfail(strict=True)` until the
  migration lands in phases 2-3 — strict so that the suite fails on *xpass*,
  forcing whoever completes the migration to delete the marker instead of
  leaving a permanently-disabled guard behind.
* the **invariants** below it, which the file already satisfies today. Their
  job is to fail if the rewrite breaks routing, identity or severity while
  changing the queries.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
ALERT_RULES_CM = REPO / "apps" / "grafana-alerting" / "manifests" / "alert-rules-cm.yaml"

# The ConfigMap key holding the Grafana provisioning document. The document is
# embedded as a YAML *string*, so reading a rule needs two loads: one for the
# ConfigMap, one for the value under this key.
PROVISIONING_KEY = "alert-rules.yaml"

FEATURE_HEALTH = "feature-health"


def _load_provisioning_document() -> dict[str, Any]:
    """Return the inner Grafana provisioning document (double YAML load)."""
    configmap = yaml.safe_load(ALERT_RULES_CM.read_text(encoding="utf-8"))
    assert configmap["kind"] == "ConfigMap", (
        f"{ALERT_RULES_CM} is expected to be a ConfigMap wrapping the Grafana "
        "provisioning document"
    )
    data = configmap["data"]
    assert PROVISIONING_KEY in data, (
        f"{ALERT_RULES_CM} has no `data.{PROVISIONING_KEY}` key — the "
        f"provisioning document moved. Keys present: {sorted(data)}"
    )
    document = yaml.safe_load(data[PROVISIONING_KEY])
    assert document.get("apiVersion") == 1, (
        "expected a Grafana alerting provisioning document (apiVersion: 1)"
    )
    return document


def _all_rules() -> list[dict[str, Any]]:
    """Every rule in the document, flattened, each carrying its group context.

    The provisioning document nests `groups[].rules[]`, and the group is where
    `folder` (the routing key) and `name` live — so a flat list of rules alone
    would lose exactly the field this file cares most about. Each returned dict
    is the rule with two extra keys: `_group` and `_folder`.
    """
    rules: list[dict[str, Any]] = []
    for group in _load_provisioning_document()["groups"]:
        for rule in group.get("rules", []):
            enriched = dict(rule)
            enriched["_group"] = group.get("name")
            enriched["_folder"] = group.get("folder")
            rules.append(enriched)
    return rules


def _feature_health_rules() -> list[dict[str, Any]]:
    return [r for r in _all_rules() if r["_folder"] == FEATURE_HEALTH]


def _rule_text(rule: dict[str, Any]) -> str:
    """A rule serialised back to YAML, for substring checks over its queries."""
    return yaml.safe_dump(rule, default_flow_style=False, sort_keys=False)


def test_feature_health_folder_is_populated():
    """Guard the guards: every other test here is vacuous if the parse yields
    nothing, and the double-load shape is exactly the kind of thing a future
    refactor breaks silently."""
    rules = _feature_health_rules()
    assert len(rules) >= 30, (
        "expected the feature-health folder to hold the full layer-tracker "
        f"set; parsed only {len(rules)} rule(s) — the ConfigMap shape or the "
        f"`data.{PROVISIONING_KEY}` key probably changed"
    )


@pytest.mark.xfail(strict=True, reason="rules migrated in phases 2-3")
def test_no_feature_health_rule_uses_pod_readiness():
    """The regression tripwire: `kube_pod_status_ready` is the defect class.

    A terminal pod's readiness series reads NotReady forever, so any rule built
    on it alerts on cluster history rather than cluster state. Workload-level
    availability (`kube_deployment_status_replicas_unavailable`,
    `kube_daemonset_status_number_unavailable`, or the
    `kube_statefulset_status_replicas` minus `..._ready` difference) counts
    replicas, and a tombstone is not a replica.

    XFAIL, STRICTLY, until the migration lands. `strict=True` is the whole
    point of the marker: a non-strict xfail tolerates an xpass silently, so the
    day the last rule is migrated this guard would quietly become a no-op that
    still *looks* like coverage. Strict makes the suite go red on xpass, and
    the only way to make it green again is to delete the marker — which is
    exactly the action phase 3 owes.

    Note the offender list is TWELVE uids, not the eleven the plan enumerates:
    `layer-8-observability-down` also queries `kube_pod_status_ready`, behind an
    `unless on(namespace,pod) kube_pod_status_phase{phase=~"Succeeded|Failed"}`
    join. That join is the tombstone-filtering workaround the design spec
    rejects; it keeps the wrong question. This assertion is deliberately
    folder-wide with no per-uid exclusions, so the marker cannot be removed
    until layer-8 is migrated too.
    """
    offenders = [
        rule["uid"]
        for rule in _feature_health_rules()
        if "kube_pod_status_ready" in _rule_text(rule)
    ]
    assert not offenders, (
        "feature-health rules still alert on per-pod readiness "
        "(kube_pod_status_ready), which fires forever on terminal pods left "
        "behind by a node reboot. Migrate them to workload availability — see "
        "layer-25-cicd-down for the in-repo precedent. Offending rule uid(s): "
        f"{offenders}"
    )


# ---------------------------------------------------------------------------
# Invariants the rewrite must not break.
#
# These pass against the file as it stands today, and that is the point: they
# are written BEFORE any rule is edited so they are a genuine before/after
# contract rather than a description of whatever the edit happened to produce.
# Phases 2-4 rewrite the `expr`, the threshold direction, `for:` and the
# annotations of these rules; everything asserted below is meant to survive
# that untouched.
# ---------------------------------------------------------------------------

# The eleven rules phases 2-3 migrate, with the routing-relevant fields they
# must still carry afterwards. Captured from the file before any edit. A
# rewrite that silently downgrades a severity or drops a tracker reference
# fails here rather than in production, where the symptom would be an alert
# quietly routing somewhere else (or nowhere).
MIGRATED_RULES: dict[str, dict[str, str]] = {
    "layer-3-networking-down": {"severity": "warning", "github_issue": "frank-ops#3"},
    "layer-4-storage-down": {"severity": "warning", "github_issue": "frank-ops#4"},
    "layer-5-gpu-down": {"severity": "warning", "github_issue": "frank-ops#5"},
    "layer-6-gitops-down": {"severity": "critical", "github_issue": "frank-ops#6"},
    "layer-10-secrets-down": {"severity": "warning", "github_issue": "frank-ops#10"},
    "layer-12-agents-down": {"severity": "warning", "github_issue": "frank-ops#12"},
    "layer-13-auth-down": {"severity": "critical", "github_issue": "frank-ops#13"},
    "layer-14-vcluster-down": {"severity": "warning", "github_issue": "frank-ops#14"},
    "layer-15-workflows-down": {"severity": "warning", "github_issue": "frank-ops#15"},
    "layer-19-rollouts-down": {"severity": "warning", "github_issue": "frank-ops#19"},
    "layer-24-ingress-down": {"severity": "critical", "github_issue": "frank-ops#24"},
}

_GITHUB_ISSUE_RE = re.compile(r"^frank-ops#\d+$")
_ALLOWED_SEVERITIES = {"warning", "critical"}


def test_migrated_rules_keep_folder_uid_severity_and_tracker():
    """Routing, identity and severity are preserved across the rewrite.

    `notification-policy-cm.yaml` routes on `grafana_folder="feature-health"`,
    so a folder typo does not produce an error — it silently reroutes a layer
    to Telegram. The `uid` is the rule's stable identity (health-bridge closes
    bugs by feature-ref), and `github_issue` is the tracker the bridge files
    against. None of the three is visible in the query being rewritten, which
    is exactly why they are easy to clobber while concentrating on the PromQL.
    """
    by_uid = {rule["uid"]: rule for rule in _all_rules()}

    missing = sorted(set(MIGRATED_RULES) - set(by_uid))
    assert not missing, (
        "rule uid(s) disappeared from the provisioning document — the "
        "migration must rewrite these rules in place, not replace them with "
        f"new uids: {missing}"
    )

    drift: list[str] = []
    for uid, expected in sorted(MIGRATED_RULES.items()):
        rule = by_uid[uid]
        labels = rule.get("labels") or {}
        actual = {
            "folder": rule["_folder"],
            "severity": labels.get("severity"),
            "github_issue": labels.get("github_issue"),
        }
        want = {"folder": FEATURE_HEALTH, **expected}
        if actual != want:
            drift.append(f"{uid}: expected {want}, got {actual}")

    assert not drift, (
        "migrated feature-health rules changed a routing-relevant field. "
        "The rewrite is allowed to change expr / threshold / for: / "
        "annotations and nothing else:\n  " + "\n  ".join(drift)
    )


def test_every_feature_health_rule_lives_in_the_feature_health_folder():
    """`folder` is a group-level field, so a single mistyped group header
    silently moves every rule under it out of the health-bridge route."""
    folders = {
        rule["uid"]: rule["_folder"]
        for rule in _all_rules()
        if rule["uid"] in MIGRATED_RULES
    }
    wrong = {uid: folder for uid, folder in folders.items() if folder != FEATURE_HEALTH}
    assert not wrong, (
        "rule(s) moved out of the feature-health folder; notification-policy-cm "
        f"keys on grafana_folder=\"{FEATURE_HEALTH}\": {wrong}"
    )


def test_every_rule_has_a_non_empty_uid_and_uids_are_globally_unique():
    """Grafana keys provisioned rules by uid across the whole org, not per
    folder — a duplicate uid means one rule silently overwrites the other at
    provisioning time, and the loser simply never evaluates."""
    rules = _all_rules()

    blank = [
        f"{rule['_folder']}/{rule['_group']}"
        for rule in rules
        if not str(rule.get("uid") or "").strip()
    ]
    assert not blank, f"rule(s) with a missing or empty uid in group(s): {blank}"

    seen: dict[str, int] = {}
    for rule in rules:
        seen[rule["uid"]] = seen.get(rule["uid"], 0) + 1
    duplicates = sorted(uid for uid, count in seen.items() if count > 1)
    assert not duplicates, (
        "duplicate rule uid(s) in the provisioning document — Grafana keys "
        f"rules by uid org-wide, so one of each pair never evaluates: {duplicates}"
    )


def test_every_feature_health_rule_has_a_known_severity():
    """`severity` drives the health-bridge's degraded-vs-down mapping; an
    unrecognised value is not rejected, it just fails to match any route."""
    offenders = {
        rule["uid"]: (rule.get("labels") or {}).get("severity")
        for rule in _feature_health_rules()
        if (rule.get("labels") or {}).get("severity") not in _ALLOWED_SEVERITIES
    }
    assert not offenders, (
        f"feature-health rule(s) with a severity outside {sorted(_ALLOWED_SEVERITIES)}: "
        f"{offenders}"
    )


def test_layer_tracker_rules_carry_a_well_formed_github_issue_label():
    """Every layer-tracker rule files against a `frank-ops#N` issue.

    Scoped to `layer-*` uids rather than the whole folder, deliberately. The
    folder also holds three willikins-owned rules (`willikins#11/12/13`) and
    several rules with no `github_issue` at all — the TLS cert canaries, the
    `telegram_direct` dead-man's switches, the vk-bridge rules. Those are not
    bugs to be fixed into conformance; they are different signal classes with
    different routing. Asserting a folder-wide rule here would be asserting
    something false, and the honest scope is the tracker rules.
    """
    offenders = {
        rule["uid"]: (rule.get("labels") or {}).get("github_issue")
        for rule in _feature_health_rules()
        if rule["uid"].startswith("layer-")
        and not _GITHUB_ISSUE_RE.match(
            str((rule.get("labels") or {}).get("github_issue") or "")
        )
    }
    assert not offenders, (
        "layer-tracker rule(s) whose github_issue label is missing or does not "
        f"match ^frank-ops#\\d+$: {offenders}"
    )


def test_every_feature_health_rule_declares_nodata_and_execerr_states():
    """Grafana defaults an omitted `noDataState` to `NoData`, which fires the
    rule. A rewrite that drops these while restructuring a rule turns a typo'd
    metric name — the most likely mistake in this migration — from a silent
    NoData into a page, or the reverse. Either way the file should say."""
    offenders = {
        rule["uid"]: sorted(
            field
            for field in ("noDataState", "execErrState")
            if not rule.get(field)
        )
        for rule in _feature_health_rules()
        if not rule.get("noDataState") or not rule.get("execErrState")
    }
    assert not offenders, (
        "feature-health rule(s) missing an explicit noDataState/execErrState: "
        f"{offenders}"
    )


# ---------------------------------------------------------------------------
# The rewrite contract for the rules migrated in phase 2.
#
# Scoped to an explicit uid list rather than the whole folder, on purpose: the
# remaining pod-readiness rules are migrated in a later phase, and a
# folder-wide assertion here would go red on rules nobody has touched yet —
# which is indistinguishable from a real regression and trains people to
# ignore it. The folder-wide statement of intent is the strict-xfail tripwire
# above; this is the per-rule contract for the batch actually being changed.
# ---------------------------------------------------------------------------

# The eight rules whose namespaces contain no DaemonSet, so they keep a 5m
# `for:` (a DaemonSet reports replicas unavailable during any node drain, which
# is why the DaemonSet-bearing namespaces get a longer window in a later phase).
PHASE_2_UIDS: frozenset[str] = frozenset(
    {
        "layer-6-gitops-down",
        "layer-10-secrets-down",
        "layer-12-agents-down",
        "layer-13-auth-down",
        "layer-14-vcluster-down",
        "layer-15-workflows-down",
        "layer-19-rollouts-down",
        "layer-24-ingress-down",
    }
)

# kube-state-metrics exports no unavailability counter for StatefulSets, hence
# the two-metric difference. Nothing else belongs in a migrated `expr`.
WORKLOAD_METRICS: frozenset[str] = frozenset(
    {
        "kube_deployment_status_replicas_unavailable",
        "kube_statefulset_status_replicas",
        "kube_statefulset_status_replicas_ready",
    }
)

_KUBE_METRIC_RE = re.compile(r"kube_[a-z0-9_]+")


def _phase_2_rules() -> dict[str, dict[str, Any]]:
    by_uid = {rule["uid"]: rule for rule in _all_rules()}
    missing = sorted(PHASE_2_UIDS - set(by_uid))
    assert not missing, f"phase-2 rule uid(s) not found in the document: {missing}"
    return {uid: by_uid[uid] for uid in sorted(PHASE_2_UIDS)}


def _query_expr(rule: dict[str, Any]) -> str:
    """The PromQL of the rule's `A` query node.

    A Grafana-managed rule is a small DAG: `A` queries the datasource, `B`
    reduces it, `C` thresholds `B`. Only `A` carries PromQL.
    """
    for node in rule.get("data", []):
        model = node.get("model") or {}
        if node.get("refId") == "A" and "expr" in model:
            return str(model["expr"])
    raise AssertionError(f"rule {rule['uid']} has no refId=A datasource query")


def _threshold_evaluator(rule: dict[str, Any]) -> dict[str, Any]:
    """The evaluator of the node named by the rule's `condition` field."""
    condition = rule["condition"]
    for node in rule.get("data", []):
        if node.get("refId") != condition:
            continue
        conditions = (node.get("model") or {}).get("conditions") or []
        assert len(conditions) == 1, (
            f"rule {rule['uid']}: expected exactly one threshold condition on "
            f"node {condition}, found {len(conditions)}"
        )
        return conditions[0]["evaluator"]
    raise AssertionError(
        f"rule {rule['uid']} names condition {condition!r} but has no such node"
    )


def test_phase_2_rules_query_only_workload_availability_metrics():
    """The migration's whole point: count replicas, not pods.

    A tombstone is not a replica, so `kube_deployment_status_replicas_unavailable`
    and the StatefulSet difference simply cannot see the terminal pods that
    produced 48 false alerts on 2026-08-02. Asserting the *allowlist* rather
    than just the absence of `kube_pod_status_ready` also catches the other
    tempting near-misses — `kube_pod_status_phase` joins, `kube_pod_container_*`
    — that would reintroduce per-pod cardinality by a different door.
    """
    offenders: dict[str, list[str]] = {}
    for uid, rule in _phase_2_rules().items():
        used = set(_KUBE_METRIC_RE.findall(_query_expr(rule)))
        stray = sorted(used - WORKLOAD_METRICS)
        if stray or not used:
            offenders[uid] = stray or ["<no kube_* metric at all>"]
    assert not offenders, (
        "phase-2 rule(s) query something other than workload availability. "
        f"Allowed metrics: {sorted(WORKLOAD_METRICS)}. Offenders: {offenders}"
    )


def test_phase_2_rules_fire_when_replicas_are_unavailable_not_when_they_are_ready():
    """The threshold INVERTS, and this is the highest-risk error in the change.

    The old rule read `lt 1` against a readiness gauge (1 = Ready, so `< 1`
    means NotReady). The new one reads `gt 0` against an *unavailability*
    counter (0 = fully available, so `> 0` means replicas missing). Carrying
    `lt 1` over unchanged produces a rule that fires permanently on every
    healthy workload; writing `gt 1` produces one blind to a single-replica
    outage. Neither looks wrong in a diff — both are `evaluator: {type, params}`
    with plausible numbers — which is exactly why it is asserted mechanically.
    """
    drift: dict[str, dict[str, Any]] = {}
    want = {"type": "gt", "params": [0]}
    for uid, rule in _phase_2_rules().items():
        evaluator = _threshold_evaluator(rule)
        actual = {"type": evaluator.get("type"), "params": evaluator.get("params")}
        if actual != want:
            drift[uid] = actual
    assert not drift, (
        "phase-2 rule(s) threshold is not `gt 0`. The metric counts UNAVAILABLE "
        "replicas, so the alert condition is `> 0`; `lt 1` (the old readiness "
        f"threshold) fires forever against a healthy cluster. Got: {drift}"
    )


# The `for:` each phase-2 rule had BEFORE the migration, which it must still
# have after. This is deliberately a per-uid map rather than a blanket "5m".
#
# The design spec originally said "5m everywhere except DaemonSet-bearing
# rules", and the first cut of this test enforced that — normalising layer-6,
# layer-14 and layer-19 down from 10m. That was wrong. This change swaps the
# METRIC a rule watches; it is not licence to re-tune sensitivity. Tightening
# ArgoCD's *critical* alert from 10m to 5m raises the chance of firing during a
# slow rollout, which is precisely the false-positive class this work exists to
# remove. The in-repo precedent agrees: `layer-25-cicd-down`, migrated to
# workload metrics back in 2026-05, sits at 10m.
#
# A sensitivity change needs its own justification and its own change. None of
# these three had one.
PHASE_2_EXPECTED_FOR: dict[str, str] = {
    "layer-6-gitops-down": "10m",
    "layer-10-secrets-down": "5m",
    "layer-12-agents-down": "5m",
    "layer-13-auth-down": "5m",
    "layer-14-vcluster-down": "10m",
    "layer-15-workflows-down": "5m",
    "layer-19-rollouts-down": "10m",
    "layer-24-ingress-down": "5m",
}


def test_phase_2_rules_preserve_their_pre_migration_for_window():
    """The migration changes the metric, never the sensitivity.

    None of these eight namespaces runs a DaemonSet, so none of them needs the
    15m reboot-tolerance window. But "doesn't need 15m" is not the same as
    "should be 5m": three of these rules were deliberately set to 10m long
    before this work, and a rewrite is the wrong place to quietly re-tune them.
    """
    drift = {
        uid: (rule.get("for"), PHASE_2_EXPECTED_FOR[uid])
        for uid, rule in _phase_2_rules().items()
        if rule.get("for") != PHASE_2_EXPECTED_FOR[uid]
    }
    assert not drift, (
        "phase-2 rule(s) whose `for:` window changed during the migration "
        f"(uid: got -> want): {drift}. Changing a rule's sensitivity is a "
        "separate change from changing the metric it watches."
    )


def test_phase_2_summaries_name_the_workload_not_the_pod():
    """An alert body is a triage instruction, and the label it interpolates has
    to still exist after the rewrite.

    `$labels.pod` is *gone* from these series — workload metrics carry no pod
    label — so a summary left interpolating it renders an empty string and the
    on-call is told that "" is down. The rewritten rules normalise every series
    onto a `workload` label, so that is what the annotations must name.
    """
    offenders: dict[str, str] = {}
    for uid, rule in _phase_2_rules().items():
        annotations = rule.get("annotations") or {}
        summary = str(annotations.get("summary") or "")
        if "$labels.workload" not in summary:
            offenders[uid] = f"summary does not interpolate $labels.workload: {summary!r}"
        elif "$labels.pod" in " ".join(str(v) for v in annotations.values()):
            offenders[uid] = "annotation still interpolates $labels.pod"
    assert not offenders, (
        "phase-2 rule annotation(s) still describe pods. Workload availability "
        f"series have no `pod` label, so this renders empty: {offenders}"
    )


def test_phase_2_rules_normalise_kind_in_lowercase():
    """`kind` is written straight into a kubectl resource path.

    The runbook says `kubectl -n <ns> rollout status {{ $labels.kind }}/{{
    $labels.workload }}`, so `kind` has to be `deployment`/`statefulset`, not
    `Deployment`/`StatefulSet`. Grafana's alert templating is Go text/template
    with a restricted function set — there is no `lower` to lean on — so the
    lowercasing must happen in the PromQL `label_replace`, where a capital
    letter is invisible until someone pastes a broken command at 03:00.
    """
    offenders: dict[str, str] = {}
    for uid, rule in _phase_2_rules().items():
        expr = _query_expr(rule)
        kinds = set(re.findall(r'"kind",\s*"([A-Za-z]+)"', expr))
        if not kinds:
            offenders[uid] = "expr never label_replaces a `kind` label"
        elif not kinds <= {"deployment", "statefulset"}:
            offenders[uid] = f"non-lowercase or unknown kind value(s): {sorted(kinds)}"
        elif not re.search(r'"workload",\s*"\$1"', expr):
            offenders[uid] = "expr never label_replaces a `workload` label"
    assert not offenders, (
        "phase-2 rule(s) do not normalise workload/kind labels as required: "
        f"{offenders}"
    )
