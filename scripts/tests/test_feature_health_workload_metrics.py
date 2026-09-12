"""Tripwires for the feature-health alert folder in
`apps/grafana-alerting/manifests/alert-rules-cm.yaml`.

Twelve layer-tracker rules asked `kube_pod_status_ready{condition="true"} < 1`,
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

Three kinds of guard live here:

* the **regression tripwire** (`test_no_feature_health_rule_uses_pod_readiness`),
  which asserts the defect is gone. It carried `xfail(strict=True)` through
  phases 1-2 and went live in phase 3 when the twelfth and last rule was
  migrated. Strict was the point: the suite fails on *xpass*, so finishing the
  migration meant deleting the marker rather than leaving a
  permanently-disabled guard that still looked like coverage.
* the **invariants**, which the file already satisfied before any rule was
  edited. Their job is to fail if the rewrite breaks routing, identity or
  severity while changing the queries.
* the **policy guards** at the end, which are folder-wide and outlive this
  migration: a rule that counts unavailable DaemonSet replicas has to wait out
  a node drain, and the 15m window that exists for that reason is not
  available to rules that just want to be less sensitive.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any

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
    # Tightened at code review: `>= 30` against 39 actual meant nine rules
    # could vanish silently from the guard whose stated job is guarding the
    # guards. A floor one below the real count still tolerates deliberate
    # additions without tolerating deletions.
    assert len(rules) >= 38, (
        "expected the feature-health folder to hold the full layer-tracker "
        f"set; parsed only {len(rules)} rule(s) — the ConfigMap shape or the "
        f"`data.{PROVISIONING_KEY}` key probably changed"
    )


def test_no_feature_health_rule_uses_pod_readiness():
    """The regression tripwire: `kube_pod_status_ready` is the defect class.

    A terminal pod's readiness series reads NotReady forever, so any rule built
    on it alerts on cluster history rather than cluster state. Workload-level
    availability (`kube_deployment_status_replicas_unavailable`,
    `kube_daemonset_status_number_unavailable`, or the
    `kube_statefulset_status_replicas` minus `..._ready` difference) counts
    replicas, and a tombstone is not a replica.

    This carried `@pytest.mark.xfail(strict=True)` from phase 1 until phase 3
    finished the migration on 2026-08-02, and the marker earned its keep. The
    offender list was TWELVE uids, not the eleven the plan enumerated:
    `layer-8-observability-down` also queried `kube_pod_status_ready`, behind an
    `unless on(namespace,pod) kube_pod_status_phase{phase=~"Succeeded|Failed"}`
    join — the tombstone-filtering workaround the design spec rejects. Because
    the assertion is folder-wide with no per-uid exclusions, and because
    `strict=True` turns an xpass into a FAILURE rather than a shrug, there was
    no way to finish the phase without migrating that twelfth rule too:
    eleven-of-twelve reported `FAILED [XPASS(strict)]`, not green.

    It is a live guard now. Leave it folder-wide — the moment it grows an
    exclusion list it stops guarding the class and starts guarding a list.
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

# The twelve rules phases 2-3 migrate, with the routing-relevant fields they
# must still carry afterwards. Captured from the file before any edit. A
# rewrite that silently downgrades a severity or drops a tracker reference
# fails here rather than in production, where the symptom would be an alert
# quietly routing somewhere else (or nowhere).
#
# `layer-8-observability-down` was missing from this map until code review
# caught it — the twelfth migrated rule, the folder's only `critical`
# alerting-stack rule, and the one this change repeatedly calls the sharpest
# signal in the folder. It was pinned for `for:`, severity, threshold and expr
# shape by its own dedicated tests, but nothing pinned its **folder** or its
# **tracker**: mutating `folder: feature-health` to `feature-heath`, or
# `frank-ops#8` to `frank-ops#99`, both passed the whole suite. A folder typo
# there drops it off the Health Bridge silently — it still pages Telegram via
# the severity route, so the loss is the bug-issue lifecycle, invisibly.
MIGRATED_RULES: dict[str, dict[str, str]] = {
    "layer-3-networking-down": {"severity": "warning", "github_issue": "frank-ops#3"},
    "layer-8-observability-down": {"severity": "critical", "github_issue": "frank-ops#8"},
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


# ---------------------------------------------------------------------------
# The rewrite contract for the rules migrated in phase 3.
#
# Three of them live in namespaces that run DaemonSets, which is the whole
# reason they were split out of phase 2: a DaemonSet reports replicas
# unavailable during ANY node drain, so the 5m window that suits a Deployment
# would turn every planned Talos rolling reboot into an alert burst — trading
# one noise source for another. The 2026-08-02 control-plane roll took roughly
# seven minutes.
#
# `layer-8-observability-down` is migrated in the same phase but is NOT one of
# these: it deliberately excludes the two `monitoring` DaemonSets and keeps its
# 5m window. Its contract lives in its own section further down.
# ---------------------------------------------------------------------------

PHASE_3_DAEMONSET_UIDS: frozenset[str] = frozenset(
    {
        "layer-3-networking-down",
        "layer-4-storage-down",
        "layer-5-gpu-down",
    }
)

# kube-state-metrics DOES export an unavailability counter for DaemonSets, so
# no difference-of-two-metrics trick is needed on that side.
DAEMONSET_METRIC = "kube_daemonset_status_number_unavailable"

WORKLOAD_METRICS_WITH_DAEMONSETS: frozenset[str] = WORKLOAD_METRICS | {DAEMONSET_METRIC}

# The window a DaemonSet-bearing rule must wait before firing. Not a general
# policy for the folder — see `test_the_fifteen_minute_window_is_reserved_for_
# daemonset_rules` for why the converse is asserted narrowly.
DAEMONSET_FOR = "15m"


def _phase_3_daemonset_rules() -> dict[str, dict[str, Any]]:
    by_uid = {rule["uid"]: rule for rule in _all_rules()}
    missing = sorted(PHASE_3_DAEMONSET_UIDS - set(by_uid))
    assert not missing, f"phase-3 rule uid(s) not found in the document: {missing}"
    return {uid: by_uid[uid] for uid in sorted(PHASE_3_DAEMONSET_UIDS)}


def test_phase_3_daemonset_rules_query_only_workload_availability_metrics():
    """Same allowlist as phase 2, plus the DaemonSet unavailability counter.

    These three namespaces (`kube-system`, `longhorn-system`, `gpu-operator` /
    `intel-gpu-resource-driver`) are where the 2026-08-02 tombstone flood was
    loudest, because a node reboot leaves one terminal pod per DaemonSet per
    node behind. Counting unavailable replicas cannot see them.
    """
    offenders: dict[str, list[str]] = {}
    for uid, rule in _phase_3_daemonset_rules().items():
        used = set(_KUBE_METRIC_RE.findall(_query_expr(rule)))
        stray = sorted(used - WORKLOAD_METRICS_WITH_DAEMONSETS)
        if stray or not used:
            offenders[uid] = stray or ["<no kube_* metric at all>"]
    assert not offenders, (
        "phase-3 rule(s) query something other than workload availability. "
        f"Allowed metrics: {sorted(WORKLOAD_METRICS_WITH_DAEMONSETS)}. "
        f"Offenders: {offenders}"
    )


def test_phase_3_daemonset_rules_actually_query_daemonsets():
    """The reason these three are in a separate phase at all.

    Each targets a namespace whose signal is carried mostly or entirely by
    DaemonSets — `cilium` and `cilium-envoy`, `longhorn-manager`, the nvidia
    and intel device plugins. A rewrite that migrated only the Deployment half
    would look correct in a diff, pass every other assertion here, and silently
    stop watching the workloads that matter most.
    """
    offenders = sorted(
        uid
        for uid, rule in _phase_3_daemonset_rules().items()
        if DAEMONSET_METRIC not in _query_expr(rule)
    )
    assert not offenders, (
        f"phase-3 rule(s) never query {DAEMONSET_METRIC}, so the DaemonSets in "
        f"their namespace are unwatched: {offenders}"
    )


def test_phase_3_daemonset_rules_fire_when_replicas_are_unavailable_not_when_they_are_ready():
    """The threshold inverts here exactly as it did in phase 2: `lt 1` on a
    readiness gauge becomes `gt 0` on an unavailability counter."""
    drift: dict[str, dict[str, Any]] = {}
    want = {"type": "gt", "params": [0]}
    for uid, rule in _phase_3_daemonset_rules().items():
        evaluator = _threshold_evaluator(rule)
        actual = {"type": evaluator.get("type"), "params": evaluator.get("params")}
        if actual != want:
            drift[uid] = actual
    assert not drift, (
        "phase-3 rule(s) threshold is not `gt 0`. The metric counts UNAVAILABLE "
        f"replicas, so the alert condition is `> 0`. Got: {drift}"
    )


def test_phase_3_daemonset_rules_wait_out_a_node_drain():
    """15m, and this one IS a deliberate sensitivity change — unlike phase 2's.

    Phase 2 preserved each rule's pre-migration `for:` because swapping the
    metric is not licence to re-tune. These three are the documented exception,
    and the justification is specific rather than tidy: a DaemonSet's
    `..._number_unavailable` goes positive the moment a node is cordoned and
    drained, so on a rolling Talos reboot it is positive for as long as the
    roll takes. The 2026-08-02 control-plane roll took ~7 minutes, which a 5m
    (layer-3, layer-5) or 10m (layer-4) window would have turned into a page
    for a healthy, deliberately-reconfiguring cluster.
    """
    drift = {
        uid: rule.get("for")
        for uid, rule in _phase_3_daemonset_rules().items()
        if rule.get("for") != DAEMONSET_FOR
    }
    assert not drift, (
        f"phase-3 DaemonSet-bearing rule(s) not at `for: {DAEMONSET_FOR}` "
        f"(uid -> got): {drift}"
    )


def test_phase_3_summaries_name_the_workload_not_the_pod():
    """Workload availability series carry no `pod` label, so an annotation left
    interpolating one renders an empty resource name to the on-call."""
    offenders: dict[str, str] = {}
    for uid, rule in _phase_3_daemonset_rules().items():
        annotations = rule.get("annotations") or {}
        summary = str(annotations.get("summary") or "")
        if "$labels.workload" not in summary:
            offenders[uid] = f"summary does not interpolate $labels.workload: {summary!r}"
        elif "$labels.pod" in " ".join(str(v) for v in annotations.values()):
            offenders[uid] = "annotation still interpolates $labels.pod"
    assert not offenders, (
        "phase-3 rule annotation(s) still describe pods: " f"{offenders}"
    )


def test_phase_3_rules_normalise_kind_in_lowercase():
    """`kind` goes straight into a kubectl resource path, so `daemonset` — not
    `DaemonSet`. Grafana's templating has no `lower` filter to fall back on."""
    offenders: dict[str, str] = {}
    for uid, rule in _phase_3_daemonset_rules().items():
        expr = _query_expr(rule)
        kinds = set(re.findall(r'"kind",\s*"([A-Za-z]+)"', expr))
        if not kinds:
            offenders[uid] = "expr never label_replaces a `kind` label"
        elif not kinds <= {"deployment", "daemonset", "statefulset"}:
            offenders[uid] = f"non-lowercase or unknown kind value(s): {sorted(kinds)}"
        elif not re.search(r'"workload",\s*"\$1"', expr):
            offenders[uid] = "expr never label_replaces a `workload` label"
    assert not offenders, (
        "phase-3 rule(s) do not normalise workload/kind labels as required: "
        f"{offenders}"
    )


# ---------------------------------------------------------------------------
# The durable policy guard: DaemonSet metric <-> 15m, folder-wide.
#
# The two tests below are the point of writing any of this down. Everything
# above is scoped to a uid list and therefore expires the moment this migration
# is finished; these two keep applying to rules nobody has written yet.
#
# They key off the METRIC, not the namespace. A namespace-based derivation
# would have to encode which namespaces run a DaemonSet today, which is live
# cluster state that drifts silently — and it would misfire on layer-8, which
# lives in a DaemonSet-bearing namespace but deliberately does not query them.
# ---------------------------------------------------------------------------


def _feature_health_rules_by_uid_with_expr() -> dict[str, tuple[dict[str, Any], str]]:
    """Every feature-health rule that has a datasource query, with its PromQL.

    A handful of folder members (heartbeat/dead-man rules) are structured
    differently; `_query_expr` raises on those, so they are skipped rather than
    asserted about.
    """
    out: dict[str, tuple[dict[str, Any], str]] = {}
    for rule in _feature_health_rules():
        try:
            out[rule["uid"]] = (rule, _query_expr(rule))
        except AssertionError:
            continue
    return out


def test_rules_that_watch_daemonsets_tolerate_a_node_drain():
    """Any rule counting unavailable DaemonSet replicas must wait 15m.

    This is the reboot-noise policy, encoded so a later edit cannot quietly
    reintroduce it. A DaemonSet is unavailable on every drained node by
    definition, so a short window on such a rule alerts on planned maintenance.

    Deliberately one-directional. The plan's first draft also asserted the
    converse as "every other feature-health rule has for: 5m", which is simply
    false: the folder holds rules at 0m, 1m, 2m, 10m, 30m, 1h, 2h and 3h, and
    five of them sit at 10m on purpose (`layer-25-cicd-down`, the in-repo
    precedent for this whole migration, among them). It was six before this
    change — `layer-4-storage-down` moved 10m -> 15m because it queries a
    DaemonSet metric. Asserting it would have
    forced a mass re-tune under cover of a query rewrite — the exact mistake
    phase 2 caught and reverted.
    """
    offenders = {
        uid: rule.get("for")
        for uid, (rule, expr) in _feature_health_rules_by_uid_with_expr().items()
        if DAEMONSET_METRIC in expr and rule.get("for") != DAEMONSET_FOR
    }
    assert not offenders, (
        f"feature-health rule(s) query {DAEMONSET_METRIC} but do not wait "
        f"{DAEMONSET_FOR} before firing (uid -> for). A DaemonSet reports "
        "replicas unavailable throughout any node drain, so a shorter window "
        f"pages on every planned Talos rolling reboot: {offenders}"
    )


# Rules allowed to sit at `for: 15m` WITHOUT querying a DaemonSet metric.
#
# The point of the converse guard below is that 15m must never become the place
# tuning quietly hides. An allowlist weakens that only if entries can be added
# without saying why — so the value here IS the justification, it is asserted
# non-empty, and a stale entry fails its own test. Adding a key is a written
# decision; deleting the guard is not available.
FIFTEEN_MINUTE_EXEMPTIONS: dict[str, str] = {
    "workload-unexpectedly-scaled-to-zero": (
        "A Recreate-strategy Deployment passes through 0 replicas on every "
        "ordinary rollout — kubernetes tears the old pod down before creating "
        "the new one — and several Frank apps are on Recreate precisely because "
        "their PVC is RWO (see storage-secrets-ssa.md: RWO + RollingUpdate "
        "deadlocks). A short window would therefore page on routine deploys of "
        "exactly the apps most likely to be deployed by hand. This is a "
        "settle-time allowance, not a sensitivity dial: the condition it "
        "watches is binary (replicas are 0 or they are not), so 15m buys "
        "tolerance for a transition rather than blunting a threshold."
    ),
    "layer-2-etcd-scrape-absent": (
        "The watchdog against the etcd scrape silently disappearing, which is "
        "the failure the whole etcd layer exists to stop recurring (the chart's "
        "Endpoints object was empty for 148 days and nothing reported it). Its "
        "window absorbs the two legitimate ways the series pause: a vmagent "
        "restart, and the rolling etcd restart the Talos ConfigPatch causes on "
        "each control-plane node in turn. Both are minutes, not seconds, and "
        "neither is a real blindness event — but absent() has no `for`-like "
        "tolerance of its own, so the window IS the tolerance. It is not a "
        "sensitivity dial: the condition is binary (the series exist or they "
        "do not) and 15m does not blunt it, it only waits."
    ),
    "layer-2-etcd-wal-fsync-slow": (
        "A p99 disk-latency quantile is spiky by nature: a single etcd "
        "compaction, a Longhorn replica rebuild on the same mini, or a backup "
        "window can put one 5m sample over 50ms without the quorum being at "
        "any risk. 15m requires the elevation to persist across three "
        "evaluation windows before it is called, which is what distinguishes "
        "sustained disk pressure (the thing that actually causes leader "
        "elections) from a transient. The THRESHOLD carries the sensitivity "
        "here and is documented provisional in the spec pending a baseline; "
        "the window is only there to reject spikes."
    ),
    "layer-2-etcd-db-quota": (
        "The etcd backend database grows over hours and days, never in "
        "seconds, so detection latency is irrelevant to this signal — at 80 "
        "percent of quota there is a long runway before the cluster hits the "
        "NOSPACE alarm and goes read-only. The window exists to reject the "
        "transient ratio spikes seen around compaction and defragmentation, "
        "when db_total_size briefly moves while the quota does not. A shorter "
        "window would buy no useful warning time and would report those "
        "compaction artefacts as incidents."
    ),
}


def test_the_fifteen_minute_window_is_reserved_for_daemonset_rules():
    """The honest converse: 15m exists in this folder for exactly one reason.

    Nothing in the folder was at 15m before this migration, and the window was
    introduced solely to absorb node drains. If a future rule adopts 15m
    without querying a DaemonSet, that is a sensitivity decision wearing this
    one's clothes and deserves its own justification — so it fails here and has
    to be written down.

    Phase 4 widened "requires a DaemonSet metric" to "requires a DaemonSet
    metric OR an entry in `FIFTEEN_MINUTE_EXEMPTIONS` carrying a written
    reason", because `workload-unexpectedly-scaled-to-zero` legitimately needs
    the window for an unrelated cause (Recreate rollouts pass through 0
    replicas). Widening rather than deleting is deliberate: the guard's value is
    that 15m is never adopted silently, and an allowlist whose entries are
    prose preserves that — it converts "quietly set 15m" into "write down why",
    which is the whole behaviour being protected.
    """
    offenders = sorted(
        uid
        for uid, (rule, expr) in _feature_health_rules_by_uid_with_expr().items()
        if rule.get("for") == DAEMONSET_FOR
        and DAEMONSET_METRIC not in expr
        and uid not in FIFTEEN_MINUTE_EXEMPTIONS
    )
    assert not offenders, (
        f"feature-health rule(s) sit at `for: {DAEMONSET_FOR}` without querying "
        f"{DAEMONSET_METRIC}. That window exists to absorb node drains; using "
        "it for anything else needs its own rationale, not this one's. Either "
        "pick a window this rule can justify on its own, or add it to "
        f"FIFTEEN_MINUTE_EXEMPTIONS with a written reason: {offenders}"
    )


def test_the_fifteen_minute_exemptions_are_live_and_reasoned():
    """An allowlist rots into a rubber stamp unless its entries are checked.

    Two ways that happens, both guarded here. An entry whose rule has since
    moved off 15m (or been deleted) sits there granting a permission nobody
    needs — and silently pre-approves any future rule that reuses the uid. An
    entry with a placeholder reason is an exemption granted without the
    justification that is supposed to be its whole price.
    """
    by_uid = _feature_health_rules_by_uid_with_expr()

    stale = sorted(
        uid
        for uid in FIFTEEN_MINUTE_EXEMPTIONS
        if uid not in by_uid or by_uid[uid][0].get("for") != DAEMONSET_FOR
    )
    assert not stale, (
        "FIFTEEN_MINUTE_EXEMPTIONS grants a 15m exemption to rule(s) that are "
        "no longer at 15m (or no longer exist). Drop the entry — a stale "
        f"exemption silently pre-approves whatever next claims the uid: {stale}"
    )

    unreasoned = sorted(
        uid for uid, reason in FIFTEEN_MINUTE_EXEMPTIONS.items() if len(reason.strip()) < 80
    )
    assert not unreasoned, (
        "FIFTEEN_MINUTE_EXEMPTIONS entries must carry the justification that "
        "the DaemonSet rules get from the node-drain argument. A one-liner is "
        f"not one: {unreasoned}"
    )


# ---------------------------------------------------------------------------
# `layer-8-observability-down` — the twelfth rule, found by phase 1's
# folder-wide tripwire rather than by the brainstorm.
#
# It is the least-broken of the twelve: it already filtered tombstones inside
# the query with `unless on(namespace,pod) kube_pod_status_phase{phase=~
# "Succeeded|Failed"}`, which is why it did NOT fire during the 2026-08-02
# flood. It is migrated anyway — a second pattern for the same question in one
# folder is how the next person gets confused, the join doubles the series
# joined per evaluation, and while it stands the strict xfail above can never
# xpass, so finishing the migration would require weakening the guard.
#
# Three things make it structurally different from the other eleven, and each
# gets its own assertion below:
#
#   * it ORs in a `probe_success` clause for the health-bridge /healthz probe,
#     which is an end-to-end signal, not a workload count;
#   * it therefore normalises onto a `component` label rather than
#     `workload`/`kind` — the probe series has no workload to name;
#   * it deliberately EXCLUDES the two `monitoring` DaemonSets and keeps
#     `for: 5m`, where its DaemonSet-bearing siblings moved to 15m.
# ---------------------------------------------------------------------------

LAYER_8 = "layer-8-observability-down"

HEALTH_BRIDGE_PROBE = "http://health-bridge.monitoring.svc.cluster.local:8080/healthz"


def _layer_8() -> dict[str, Any]:
    by_uid = {rule["uid"]: rule for rule in _all_rules()}
    assert LAYER_8 in by_uid, f"{LAYER_8} not found in the provisioning document"
    return by_uid[LAYER_8]


def test_layer_8_stops_asking_about_pods_at_all():
    """Both halves of the old question go, not just the readiness gauge.

    `kube_pod_status_phase` was only ever there to subtract the tombstones
    `kube_pod_status_ready` produced. Porting the `unless` join onto workload
    metrics would be cargo cult: an unavailable-replica count has no terminal
    pods in it to filter.
    """
    expr = _query_expr(_layer_8())
    offenders = sorted(
        metric
        for metric in ("kube_pod_status_ready", "kube_pod_status_phase")
        if metric in expr
    )
    assert not offenders, (
        f"{LAYER_8} still queries per-pod state: {offenders}. The readiness "
        "gauge is the defect class; the phase join is the workaround for it, "
        "and workload availability metrics need neither."
    )


def test_layer_8_watches_deployments_and_statefulsets_but_not_daemonsets():
    """The exclusion is the point, not an oversight.

    `monitoring` runs two DaemonSets — `fluent-bit` and
    `victoria-metrics-prometheus-node-exporter` — which are node-level
    collectors. Their unavailability during a node drain is exactly the noise
    this whole change removes, and excluding them is what lets this rule keep a
    5m window while its siblings moved to 15m. The observability control plane
    proper is Deployments (grafana, vmagent, vmsingle, kube-state-metrics,
    health-bridge, blackbox-exporter, pushgateway) plus one StatefulSet
    (victoria-logs).

    Excluding them from THIS rule was a real loss of coverage, and the design
    spec's claim that "their real coverage is the Layer 1/2 node alerts" did
    not survive checking — those rules key on node Ready conditions and are
    blind to a collector dying on a healthy node. Phase 3 raised that as an
    open finding rather than widening the query mid-rewrite; phase 4 closed it
    with `layer-8-observability-collectors-down`, which watches
    `kube_daemonset_status_number_unavailable{namespace="monitoring"}` at
    warning/15m (see `test_the_collectors_rule_watches_the_monitoring_
    daemonsets`). So what this test asserts is now a ROUTING decision between
    two rules rather than a gap: the collectors are covered, on the
    drain-tolerant window they need, without dragging this critical rule off 5m.
    """
    used = set(_KUBE_METRIC_RE.findall(_query_expr(_layer_8())))

    missing = sorted(WORKLOAD_METRICS - used)
    assert not missing, (
        f"{LAYER_8} does not query {missing} — `monitoring` holds both "
        "Deployments and a StatefulSet, and kube-state-metrics exports no "
        "unavailability counter for StatefulSets, hence the two-metric "
        "difference."
    )

    stray = sorted(used - WORKLOAD_METRICS)
    assert not stray, (
        f"{LAYER_8} queries {stray}. If that includes {DAEMONSET_METRIC}, the "
        "monitoring DaemonSets have been pulled back in — they are excluded on "
        "purpose, and including them would force this critical rule onto the "
        "15m drain-tolerant window for no benefit."
    )


def test_layer_8_keeps_the_health_bridge_self_probe():
    """The sharpest signal in the folder, and entirely unaffected by the
    migration: an end-to-end HTTP probe of health-bridge's own /healthz. A
    rewrite that dropped it while restructuring the surrounding PromQL would
    leave the rule looking healthy and answer a strictly weaker question."""
    expr = _query_expr(_layer_8())
    assert "probe_success" in expr, f"{LAYER_8} no longer queries probe_success"
    assert HEALTH_BRIDGE_PROBE in expr, (
        f"{LAYER_8} no longer probes {HEALTH_BRIDGE_PROBE} — the instance "
        "selector must survive the rewrite verbatim"
    )


def test_layer_8_inverts_the_self_probe_to_match_the_new_threshold():
    """The trap this rule sets, and the one thing the design spec got wrong.

    The spec says the `probe_success` clause is "preserved verbatim ... and
    entirely unaffected by this migration". Its *selector* is; its *polarity*
    cannot be. `probe_success` is 1 when the probe SUCCEEDS, and the old rule
    read it under `lt 1`, so 0 meant fire. The migration inverts the threshold
    to `gt 0` because the workload branches now count UNAVAILABLE replicas — at
    which point a verbatim `probe_success` fires continuously while
    health-bridge is healthy and goes silent the moment it dies. Exactly
    backwards, on the sharpest signal in the folder, with a diff that looks
    like the careful thing to do.

    `== bool 0` maps success->0 and failure->1, which is the same polarity as
    an unavailable-replica count and therefore the same threshold. Verified
    live 2026-08-02: raw probe_success = 1, inverted = 0, on a healthy probe.
    """
    expr = _query_expr(_layer_8())
    inverted = re.search(r"probe_success\{[^}]*\}\s*==\s*bool\s+0", expr)
    assert inverted, (
        f"{LAYER_8}'s probe_success clause is not inverted. Under the `gt 0` "
        "threshold a raw probe_success fires while the probe is HEALTHY (1) "
        "and stays quiet when it fails (0). Write "
        "`probe_success{...} == bool 0` so success maps to 0, matching the "
        "unavailable-replica counts it is OR'd with."
    )


def test_layer_8_fires_on_unavailability():
    """Same inversion as every other migrated rule: `lt 1` on a readiness
    gauge becomes `gt 0` on an unavailability count."""
    evaluator = _threshold_evaluator(_layer_8())
    actual = {"type": evaluator.get("type"), "params": evaluator.get("params")}
    assert actual == {"type": "gt", "params": [0]}, (
        f"{LAYER_8} threshold is {actual}, expected `gt 0`"
    )


def test_layer_8_keeps_its_five_minute_window_and_critical_severity():
    """It does NOT follow the DaemonSet rule, and that is deliberate.

    This rule covers the alerting stack's own health at `severity: critical` —
    when it is right, everything else in this folder is unreliable. Blunting
    detection to 15m would be a real loss, and it buys nothing here because the
    DaemonSets that motivated the 15m window are excluded from the query.
    """
    rule = _layer_8()
    assert rule.get("for") == "5m", (
        f"{LAYER_8} moved to `for: {rule.get('for')}`. It excludes DaemonSets "
        "precisely so it can stay at 5m; if it now queries them, the exclusion "
        "regressed rather than the window."
    )
    assert (rule.get("labels") or {}).get("severity") == "critical", (
        f"{LAYER_8} must stay severity: critical — it watches the alerting "
        "stack that every other rule in this folder depends on"
    )


def test_layer_8_normalises_every_branch_onto_a_component_label():
    """`component` is what makes three unlike branches one readable alert.

    The old rule produced `pod/<name>`; the migrated one produces
    `deployment/<name>`, `statefulset/<name>` and the unchanged
    `probe/health-bridge-healthz`. `workload`/`kind` — the convention the other
    eleven rules use — is deliberately NOT used here: the probe series has no
    workload, so a summary interpolating `$labels.workload` would render empty
    for the one branch that matters most.
    """
    rule = _layer_8()
    expr = _query_expr(rule)

    components = set(re.findall(r'"component",\s*"([^"]+)"', expr))
    expected = {"deployment/$1", "statefulset/$1", "probe/health-bridge-healthz"}
    missing = sorted(expected - components)
    assert not missing, (
        f"{LAYER_8} does not label every branch with a `component`; missing "
        f"{missing}, found {sorted(components)}"
    )

    annotations = rule.get("annotations") or {}
    summary = str(annotations.get("summary") or "")
    assert "$labels.component" in summary, (
        f"{LAYER_8} summary does not interpolate $labels.component: {summary!r}"
    )
    rendered = " ".join(str(v) for v in annotations.values())
    assert "$labels.pod" not in rendered, (
        f"{LAYER_8} annotations still interpolate $labels.pod, which no longer "
        "exists on any branch of the query"
    )


# ---------------------------------------------------------------------------
# Phase 4, task 1 — `workload-unexpectedly-scaled-to-zero`.
#
# The inverse question to everything above. The twelve migrated rules ask "are
# the replicas this workload wants actually available?", which is silent about a
# workload that wants zero. A Deployment scaled to 0 has no unavailable replicas
# by definition, so every rule in this folder reads it as perfectly healthy.
#
# The whole risk of the new rule is false positives, because two Deployments on
# Frank sit at 0 replicas by design and both are healthy. Neither exclusion may
# be written from memory: they are DERIVED here from the two declarative sources
# that cause the behaviour, so adding a third GPU-timeshared workload or a
# second `scaleDown: onsuccess` Rollout fails CI instead of paging at 03:00.
#
# An earlier draft of the design spec got this wrong in both directions at once
# — it read the exclusion set out of `gpu-switcher`'s ClusterRole (which carries
# no namespaces at all) and listed `litellm` as GPU-timeshared (it is not; it is
# a Rollout scale-down). Neither error is visible in a YAML review. That is what
# this derivation is for.
# ---------------------------------------------------------------------------

SCALE_TO_ZERO = "workload-unexpectedly-scaled-to-zero"

GPU_SWITCHER_DEPLOYMENT = REPO / "apps" / "gpu-switcher" / "manifests" / "deployment.yaml"

# The metric the new rule watches: what the Deployment ASKS for, not what it
# has. `kube_deployment_status_replicas_unavailable` is 0 for a 0-replica
# Deployment, which is the blind spot being closed.
SPEC_REPLICAS_METRIC = "kube_deployment_spec_replicas"


def _gpu_timeshared_workloads() -> set[tuple[str, str]]:
    """`(namespace, deployment)` pairs that gpu-switcher scales to 0.

    Source of truth is the `WORKLOADS` env var on gpu-switcher's own Deployment,
    whose value is a comma-separated list of `name:namespace:deployment`
    triples. Explicitly NOT `apps/gpu-switcher/manifests/clusterrole.yaml`: a
    ClusterRole is cluster-scoped and carries no namespace information whatever,
    despite a leading comment there saying "in GPU workload namespaces". A
    reader who trusts that comment derives a set that cannot be right.
    """
    document = yaml.safe_load(GPU_SWITCHER_DEPLOYMENT.read_text(encoding="utf-8"))
    assert document.get("kind") == "Deployment", (
        f"{GPU_SWITCHER_DEPLOYMENT} is expected to be gpu-switcher's Deployment"
    )
    containers = document["spec"]["template"]["spec"]["containers"]
    values = [
        env["value"]
        for container in containers
        for env in container.get("env") or []
        if env.get("name") == "WORKLOADS"
    ]
    assert len(values) == 1, (
        f"expected exactly one WORKLOADS env var in {GPU_SWITCHER_DEPLOYMENT}, "
        f"found {len(values)} — the timeshare contract moved and this "
        "derivation is now reading nothing"
    )

    workloads: set[tuple[str, str]] = set()
    for triple in values[0].split(","):
        parts = [part.strip() for part in triple.strip().split(":")]
        assert len(parts) == 3, (
            f"WORKLOADS entry {triple!r} is not a name:namespace:deployment "
            "triple; gpu-switcher's parser and this one have diverged"
        )
        _name, namespace, deployment = parts
        workloads.add((namespace, deployment))
    assert workloads, f"{GPU_SWITCHER_DEPLOYMENT} declares an empty WORKLOADS list"
    return workloads


def _rollout_scaled_down_deployments() -> set[tuple[str, str]]:
    """`(namespace, deployment)` pairs an Argo Rollout parks at 0 replicas.

    `workloadRef.scaleDown: onsuccess` makes the controller scale the referenced
    Deployment to 0 the instant the Rollout goes Healthy, and serve traffic from
    the Rollout's own ReplicaSet — so the Deployment reads 0/0 while the service
    is at full strength. The default is `never`, which leaves the Deployment
    running, so the field's ABSENCE is meaningful and is what distinguishes the
    two Rollouts in this repo.
    """
    paths = sorted(REPO.glob("apps/**/rollout.yaml"))
    assert paths, (
        "no apps/**/rollout.yaml matched — the glob broke, and this derivation "
        "would silently conclude that nothing is scaled down by a Rollout"
    )

    scaled_down: set[tuple[str, str]] = set()
    seen_rollouts = 0
    for path in paths:
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not isinstance(document, dict) or document.get("kind") != "Rollout":
                continue
            seen_rollouts += 1
            workload_ref = (document.get("spec") or {}).get("workloadRef") or {}
            if workload_ref.get("scaleDown") != "onsuccess":
                continue
            assert workload_ref.get("kind") == "Deployment", (
                f"{path}: workloadRef targets {workload_ref.get('kind')!r}, not "
                "a Deployment — the scale-to-0 rule only watches Deployments, "
                "so this needs a decision rather than a silent skip"
            )
            namespace = (document.get("metadata") or {}).get("namespace")
            assert namespace, f"{path}: Rollout declares no metadata.namespace"
            scaled_down.add((namespace, workload_ref["name"]))
    assert seen_rollouts, f"parsed {len(paths)} rollout file(s) but found no Rollout objects"
    return scaled_down


def _scale_to_zero_rule() -> dict[str, Any]:
    by_uid = {rule["uid"]: rule for rule in _all_rules()}
    assert SCALE_TO_ZERO in by_uid, (
        f"no rule with uid {SCALE_TO_ZERO!r} in the provisioning document. "
        "Nothing in this folder can see a workload that has been scaled to 0: "
        "an unavailable-replica count is 0 for a 0-replica Deployment, so a "
        "service scaled down by accident reads as perfectly healthy."
    )
    return by_uid[SCALE_TO_ZERO]


def _negative_matchers(expr: str) -> dict[str, str]:
    """Every `label!~"regex"` matcher in a PromQL expression, by label."""
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r'(\w+)\s*!~\s*"([^"]*)"', expr)
    }


_BARE_LITERAL_RE = re.compile(r"[A-Za-z0-9_.-]+")


def _alternation_literals(pattern: str) -> list[str]:
    """The alternatives of a flat `a|b|c` regex, asserting each is a literal.

    "The exclusions cover exactly the derived set, no more and no less" is only
    a checkable claim while the alternatives are literal workload names. A
    wildcard (`litellm.*`) would make the exclusion set unbounded and this
    comparison meaningless, so it fails loudly rather than being approximated.
    """
    body = pattern.strip()
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
        if body.startswith("?:"):
            body = body[2:]
    literals = [part.strip() for part in body.split("|")]
    strays = [part for part in literals if not _BARE_LITERAL_RE.fullmatch(part)]
    assert not strays, (
        f"exclusion pattern {pattern!r} contains non-literal alternative(s) "
        f"{strays}. The exclusion set must be exactly the workloads derived "
        "from gpu-switcher's WORKLOADS env var and the scaleDown: onsuccess "
        "Rollouts; a wildcard silently drops coverage for whatever else it "
        "happens to match."
    )
    return literals


def test_the_scale_to_zero_rule_watches_desired_replicas_not_availability():
    """It must ask a different question from every other rule in the folder.

    `kube_deployment_status_replicas_unavailable` is 0 for a Deployment scaled
    to 0 — it has no replicas to be missing — so the twelve migrated rules are
    structurally blind to this failure. Only `spec_replicas` sees it. A rewrite
    that "harmonised" this rule onto the folder's usual metric would look
    tidier and would delete the rule's entire reason to exist.
    """
    expr = _query_expr(_scale_to_zero_rule())
    assert SPEC_REPLICAS_METRIC in expr, (
        f"{SCALE_TO_ZERO} does not query {SPEC_REPLICAS_METRIC}; got: {expr!r}"
    )


def test_the_scale_to_zero_exclusions_are_derived_from_both_declarative_sources():
    """The guard that earns its keep — no restating, only deriving.

    Two independent mechanisms park a Deployment at 0 replicas on Frank, and
    both are declared in this repo:

      (a) gpu-switcher's `WORKLOADS` env var (GPU timeshare on gpu-1), and
      (b) any Argo Rollout whose `workloadRef.scaleDown` is `onsuccess`.

    Both are parsed here and the rule's exclusion regexes must cover exactly
    their union. `litellm` is the reason this matters: its Deployment sits at 0
    while its Rollout serves 5/5, so a naive `spec_replicas == 0` rule pages on
    a completely healthy LLM gateway the day it ships.

    The split between the two exclusion labels is itself asserted, not
    incidental: the GPU workloads are excluded by NAMESPACE (the whole namespace
    exists to be timeshared) while the Rollout target is excluded by DEPLOYMENT
    NAME, so an unrelated Deployment appearing in the `litellm` namespace is
    still watched.
    """
    gpu_timeshared = _gpu_timeshared_workloads()
    rollout_scaled_down = _rollout_scaled_down_deployments()

    matchers = _negative_matchers(_query_expr(_scale_to_zero_rule()))
    assert set(matchers) == {"namespace", "deployment"}, (
        f"{SCALE_TO_ZERO} carries negative matchers on {sorted(matchers)}; "
        "expected exactly `namespace` (GPU timeshare) and `deployment` "
        "(Rollout scale-down). Any other exclusion label is coverage removed "
        "without a declarative source to justify it."
    )

    excluded_namespaces = set(_alternation_literals(matchers["namespace"]))
    expected_namespaces = {namespace for namespace, _ in gpu_timeshared}
    assert excluded_namespaces == expected_namespaces, (
        "the namespace exclusions do not match gpu-switcher's WORKLOADS env "
        f"var in {GPU_SWITCHER_DEPLOYMENT}. Rule excludes "
        f"{sorted(excluded_namespaces)}; WORKLOADS declares "
        f"{sorted(expected_namespaces)}. A missing namespace pages during the "
        "next GPU timeshare switch; a surplus one silently stops watching "
        "everything in it."
    )

    excluded_deployments = set(_alternation_literals(matchers["deployment"]))
    expected_deployments = {deployment for _, deployment in rollout_scaled_down}
    assert excluded_deployments == expected_deployments, (
        "the deployment exclusions do not match the set of Argo Rollouts with "
        "`workloadRef.scaleDown: onsuccess` under apps/**/rollout.yaml. Rule "
        f"excludes {sorted(excluded_deployments)}; the repo declares "
        f"{sorted(expected_deployments)}. Flipping a second Rollout to "
        "onsuccess must fail here rather than page."
    )


def test_the_scale_to_zero_rule_still_watches_the_litellm_namespace():
    """Excluding `litellm` by deployment name rather than by namespace.

    The two exclusion mechanisms are not interchangeable. The GPU namespaces
    exist to be timeshared, so excluding them wholesale is honest. `litellm` is
    a normal namespace that happens to contain one Rollout-managed Deployment —
    excluding the namespace would blind the rule to every other Deployment that
    ever lands there, which is coverage loss disguised as an exclusion.
    """
    matchers = _negative_matchers(_query_expr(_scale_to_zero_rule()))
    namespace_pattern = matchers.get("namespace", "")
    rollout_namespaces = {namespace for namespace, _ in _rollout_scaled_down_deployments()}
    overreach = sorted(
        namespace
        for namespace in rollout_namespaces
        if re.fullmatch(namespace_pattern, namespace)
    )
    assert not overreach, (
        f"{SCALE_TO_ZERO} excludes the whole namespace(s) {overreach}, which "
        "hold a Rollout-managed Deployment. Exclude the Deployment by name "
        "instead, so an unrelated Deployment scaled to 0 in that namespace is "
        "still caught."
    )


def test_the_scale_to_zero_rule_fires_on_the_series_its_filter_returns():
    """The trap in this rule, and the reason its threshold is NOT `gt 0`.

    Every other rule migrated here counts unavailable replicas and thresholds at
    `gt 0`. Copying that convention onto this rule produces one that can never
    fire, and nothing about the YAML looks wrong.

    `metric == 0` in PromQL is a FILTER, not a comparison: it returns the
    matching series carrying their ORIGINAL value, which for this filter is
    always 0. Verified live 2026-08-03 — `kube_deployment_spec_replicas == 0`
    returns `comfyui` and `litellm`, both with value `0`. So the reduce node
    hands the threshold a 0 on exactly the series that should alert, and
    `gt 0` never fires on any of them.

    The presence of a series IS the alert condition here; the value is a
    constant. `lt 1` fires on it, and `noDataState: OK` makes the healthy case
    (no series at all) quiet. `== bool 0` plus `gt 0` would also work, at the
    cost of pushing every Deployment in the cluster through the reduce node on
    every evaluation for a signal that is normally empty.
    """
    rule = _scale_to_zero_rule()
    expr = _query_expr(rule)

    assert re.search(r"==\s*0", expr) and "bool" not in expr, (
        f"{SCALE_TO_ZERO} no longer uses a bare `== 0` filter. If it moved to "
        "`== bool 0` the threshold must invert to `gt 0` at the same time — "
        "the two are a pair, and changing one alone yields a rule that either "
        f"never fires or fires on every healthy Deployment. Got: {expr!r}"
    )

    evaluator = _threshold_evaluator(rule)
    actual = {"type": evaluator.get("type"), "params": evaluator.get("params")}
    assert actual == {"type": "lt", "params": [1]}, (
        f"{SCALE_TO_ZERO} threshold is {actual}. Its query is a `== 0` FILTER, "
        "so every series it returns carries the value 0 — `gt 0` (the "
        "convention for the unavailability counters elsewhere in this folder) "
        "makes the rule structurally incapable of firing while looking "
        "entirely conventional."
    )


def test_the_scale_to_zero_rule_routes_and_annotates_like_a_tracker_rule():
    """Folder, severity, tracker and the annotations the on-call actually reads.

    `github_issue: frank-ops#8` because this is observability's own rule rather
    than any one feature layer's — the condition is workload-shaped, not
    layer-shaped, which is why it is one rule and not twelve.

    The runbook must point at `rollouts.argoproj.io`: "a Rollout owns this
    Deployment" is by far the most likely benign explanation for a hit, and an
    on-call who does not know that spends the incident looking at a Deployment
    that is supposed to be empty.
    """
    rule = _scale_to_zero_rule()
    assert rule["_folder"] == FEATURE_HEALTH, (
        f"{SCALE_TO_ZERO} is in folder {rule['_folder']!r}; notification "
        "routing keys on grafana_folder=feature-health"
    )
    labels = rule.get("labels") or {}
    assert labels.get("severity") == "warning", (
        f"{SCALE_TO_ZERO} severity is {labels.get('severity')!r}, expected "
        "warning: a scaled-to-0 workload is a real outage of that capability, "
        "but the rule is new and its exclusion set is derived from repo state, "
        "so a mistake should not page as critical"
    )
    assert labels.get("github_issue") == "frank-ops#8", (
        f"{SCALE_TO_ZERO} github_issue is {labels.get('github_issue')!r}, "
        "expected frank-ops#8 (layer 8 is obs per docs/layers.yaml)"
    )

    annotations = rule.get("annotations") or {}
    summary = str(annotations.get("summary") or "")
    for token in ("$labels.namespace", "$labels.deployment"):
        assert token in summary, (
            f"{SCALE_TO_ZERO} summary does not interpolate {token}, so the "
            f"alert cannot name the workload it is about: {summary!r}"
        )
    runbook = str(annotations.get("runbook") or "")
    assert "rollouts.argoproj.io" in runbook, (
        f"{SCALE_TO_ZERO} runbook does not tell the on-call to check for an "
        "Argo Rollout owning the Deployment, which is the most likely benign "
        f"explanation for a hit: {runbook!r}"
    )


# ---------------------------------------------------------------------------
# Phase 4, task 2 — `layer-8-observability-collectors-down`.
#
# Closing a coverage regression this migration itself introduced. The
# pre-migration layer-8 query matched EVERY pod in `monitoring`, which included
# the pods of both DaemonSets there: `fluent-bit` and
# `victoria-metrics-prometheus-node-exporter`. Migrating layer-8 to Deployments
# and StatefulSets dropped them, and the design spec justified that by asserting
# their "real coverage is the Layer 1/2 node alerts".
#
# That claim was checked and is false. `layer-1-hardware-down` and
# `layer-2-os-down` both key on
# `kube_node_status_condition{condition="Ready",status="false"}` — they see a
# dead NODE and are completely blind to a collector crashlooping on a healthy
# one. Grepping the whole ConfigMap for `fluent-bit` and `node-exporter` finds
# only comments and `job=` label selectors: no rule anywhere watched either
# DaemonSet's health.
#
# So the coverage is restored, in a SEPARATE rule rather than folded back into
# layer-8. Folding it in would force that rule to 15m (the node-drain policy
# applies the moment a DaemonSet metric appears in an expr), which would blunt
# detection of the alerting stack's own failure from 5m to 15m — trading a real
# critical-path regression for the fix to a warning-level one.
# ---------------------------------------------------------------------------

COLLECTORS_DOWN = "layer-8-observability-collectors-down"


def _collectors_rule() -> dict[str, Any]:
    by_uid = {rule["uid"]: rule for rule in _all_rules()}
    assert COLLECTORS_DOWN in by_uid, (
        f"no rule with uid {COLLECTORS_DOWN!r}. Migrating layer-8 to workload "
        "metrics dropped the two `monitoring` DaemonSets (fluent-bit, "
        "victoria-metrics-prometheus-node-exporter) and nothing else in the "
        "ConfigMap watches them — the Layer 1/2 node alerts fire on a NotReady "
        "NODE, not on a collector dying on a healthy one."
    )
    return by_uid[COLLECTORS_DOWN]


def test_the_collectors_rule_watches_the_monitoring_daemonsets():
    """The restored coverage, asserted at the metric AND the namespace.

    Scoped to `namespace="monitoring"` with no name selector: the point is to
    watch whatever collectors run there, so a third DaemonSet added later is
    covered without anyone remembering to extend a regex. That is the opposite
    of the choice made for the layer trackers, and deliberately so — those name
    specific control-plane workloads, this one names a namespace whose entire
    DaemonSet population is collectors.
    """
    expr = _query_expr(_collectors_rule())
    assert DAEMONSET_METRIC in expr, (
        f"{COLLECTORS_DOWN} does not query {DAEMONSET_METRIC}, so it does not "
        f"restore anything: {expr!r}"
    )
    assert 'namespace="monitoring"' in expr, (
        f"{COLLECTORS_DOWN} is not scoped to namespace=\"monitoring\"; it would "
        "duplicate the layer-3/4/5 DaemonSet rules or watch the whole cluster: "
        f"{expr!r}"
    )
    used = set(_KUBE_METRIC_RE.findall(expr))
    stray = sorted(used - WORKLOAD_METRICS_WITH_DAEMONSETS)
    assert not stray, (
        f"{COLLECTORS_DOWN} queries non-workload metric(s) {stray}; the "
        "regression tripwire at the top of this file exists because per-pod "
        "metrics are how this folder got 48 false alerts"
    )


def test_the_collectors_rule_fires_on_unavailability_after_a_drain_window():
    """`gt 0` on an unavailability counter, and 15m because these ARE DaemonSets.

    No exemption needed and none taken: the rule satisfies
    `test_the_fifteen_minute_window_is_reserved_for_daemonset_rules` on its
    merits, which is a large part of why restoring the coverage as a separate
    rule is cheaper than folding it back into layer-8.
    """
    rule = _collectors_rule()
    evaluator = _threshold_evaluator(rule)
    actual = {"type": evaluator.get("type"), "params": evaluator.get("params")}
    assert actual == {"type": "gt", "params": [0]}, (
        f"{COLLECTORS_DOWN} threshold is {actual}, expected `gt 0` — the "
        "metric counts UNAVAILABLE replicas, so `lt 1` fires forever against a "
        "healthy cluster"
    )
    assert rule.get("for") == DAEMONSET_FOR, (
        f"{COLLECTORS_DOWN} is at `for: {rule.get('for')}`, expected "
        f"{DAEMONSET_FOR}: a DaemonSet reports replicas unavailable throughout "
        "any node drain, so a shorter window pages on every planned Talos "
        "rolling reboot"
    )
    assert COLLECTORS_DOWN not in FIFTEEN_MINUTE_EXEMPTIONS, (
        f"{COLLECTORS_DOWN} does not need a 15m exemption — it queries "
        f"{DAEMONSET_METRIC} and earns the window outright. An unnecessary "
        "allowlist entry is how an allowlist becomes a rubber stamp."
    )


def test_the_collectors_rule_routes_as_a_warning_layer_8_tracker():
    """`warning`, not `critical`, and the distinction is the whole design.

    Losing `fluent-bit` stops log shipping and losing node-exporter stops node
    metrics — both real degradations. But `vmagent`, `vmsingle` and `grafana`
    are Deployments still covered at critical/5m by `layer-8-observability-down`
    proper, so the alerting stack itself is not blind and this does not need to
    page at the same level.
    """
    rule = _collectors_rule()
    assert rule["_folder"] == FEATURE_HEALTH, (
        f"{COLLECTORS_DOWN} is in folder {rule['_folder']!r}, not {FEATURE_HEALTH}"
    )
    labels = rule.get("labels") or {}
    assert labels.get("severity") == "warning", (
        f"{COLLECTORS_DOWN} severity is {labels.get('severity')!r}, expected "
        "warning — layer-8 proper still covers the alerting control plane at "
        "critical"
    )
    assert labels.get("github_issue") == "frank-ops#8", (
        f"{COLLECTORS_DOWN} github_issue is {labels.get('github_issue')!r}, "
        "expected frank-ops#8"
    )


def test_the_collectors_rule_names_the_workload_with_a_lowercase_kind():
    """The folder's label convention, so the runbook interpolates into a real
    `kubectl` resource path.

    `kind` is written lowercase in the expr rather than lowered at render time:
    Grafana's alert templating is Go `text/template` with a restricted function
    set, and betting on a `lower` filter to make `daemonset/fluent-bit` out of
    `DaemonSet/fluent-bit` is an avoidable bet on the one path nobody exercises
    until an incident.
    """
    rule = _collectors_rule()
    expr = _query_expr(rule)
    assert '"workload", "$1", "daemonset", "(.*)"' in expr, (
        f"{COLLECTORS_DOWN} does not label_replace the `daemonset` label into "
        f"`workload`, so the summary would render an empty name: {expr!r}"
    )
    assert '"kind", "daemonset"' in expr, (
        f"{COLLECTORS_DOWN} does not inject a lowercase `kind` label: {expr!r}"
    )
    assert '"kind", "DaemonSet"' not in expr, (
        f"{COLLECTORS_DOWN} injects a capitalised `kind`, which does not "
        "interpolate into a kubectl resource path"
    )

    annotations = rule.get("annotations") or {}
    summary = str(annotations.get("summary") or "")
    for token in ("$labels.kind", "$labels.workload"):
        assert token in summary, (
            f"{COLLECTORS_DOWN} summary does not interpolate {token}: {summary!r}"
        )
    rendered = " ".join(str(value) for value in annotations.values())
    assert "$labels.pod" not in rendered, (
        f"{COLLECTORS_DOWN} annotations interpolate $labels.pod, which does "
        "not exist on a DaemonSet availability series"
    )
    assert "$value" not in rendered or "$values.B.Value" in rendered, (
        f"{COLLECTORS_DOWN} annotations use the bare `$value`, which Grafana "
        "renders as `[ var='B' labels={...} value=1 ]`. Use "
        '`{{ $values.B.Value | printf "%.0f" }}` — the convention every other '
        "migrated rule in this folder follows."
    )


# ---------------------------------------------------------------------------
# Notification routing: this folder is NOT Health-Bridge-only.
#
# Believed otherwise for most of this migration and corrected at code review.
# `notification-policy-cm.yaml` evaluates `severity=critical -> Telegram
# (continue: true)` and `severity=warning -> Telegram (continue: true)` BEFORE
# the `grafana_folder=feature-health -> Health Bridge` route, so a rule carrying
# none of the escape-hatch labels delivers to BOTH. The escape hatches
# (`gpu_timeshare`, `health_bridge_only`, `canary*`, `telegram_direct`) sit above
# the severity routes precisely because that is how a rule opts out.
#
# Practical consequence: adding a warning-level rule to this folder adds a
# PAGER, not a dashboard tile.
# ---------------------------------------------------------------------------

_TELEGRAM_ESCAPE_HATCHES = ("gpu_timeshare", "health_bridge_only", "canary",
                            "canary_watchdog", "telegram_direct")


def test_scale_to_zero_stays_off_telegram():
    """`workload-unexpectedly-scaled-to-zero` must keep `health_bridge_only`.

    It watches every non-excluded Deployment in the cluster (~73) on a 15m
    window, and two procedures this repo documents deliberately park a
    Deployment at 0 for far longer than that: the Longhorn instance-manager
    retirement in `storage-secrets-ssa.md` ("scale workloads to 0 and wait for
    natural detach") and the durable scale-to-0 recipe in `frank-argocd.md`.

    Without the label it matches the `severity=warning -> Telegram` route and
    turns both of those correct operator actions into a page. Dropping the label
    is a one-line edit with no visible effect in the diff, which is exactly why
    it is asserted here rather than left to the comment beside it.
    """
    by_uid = {rule["uid"]: rule for rule in _feature_health_rules()}
    rule = by_uid.get(SCALE_TO_ZERO)
    assert rule is not None, f"{SCALE_TO_ZERO} is missing from the feature-health folder"
    labels = rule.get("labels", {})
    assert labels.get("health_bridge_only") == "true", (
        f"{SCALE_TO_ZERO} lost its `health_bridge_only: \"true\"` label, so it now "
        "matches the severity=warning -> Telegram route in "
        "notification-policy-cm.yaml. It watches ~73 Deployments cluster-wide and "
        "fires on deliberate operator scale-downs (Longhorn IM retirement, the "
        f"ArgoCD scale-to-0 recipe). Current labels: {labels}"
    )


def test_collectors_rule_deliberately_does_page():
    """The converse, asserted so the two rules cannot drift into each other.

    `layer-8-observability-collectors-down` fires when `fluent-bit` or
    `node-exporter` is unavailable — a real degradation worth a page, and
    consistent with how every other warning-level rule in this folder already
    behaves. If someone copies the scale-to-zero rule's label across "for
    consistency", log-shipping and node-metric loss go silent.
    """
    by_uid = {rule["uid"]: rule for rule in _feature_health_rules()}
    rule = by_uid.get(COLLECTORS_DOWN)
    assert rule is not None, f"{COLLECTORS_DOWN} is missing from the feature-health folder"
    present = sorted(
        hatch for hatch in _TELEGRAM_ESCAPE_HATCHES
        if rule.get("labels", {}).get(hatch) == "true"
    )
    assert not present, (
        f"{COLLECTORS_DOWN} carries Telegram escape-hatch label(s) {present}, so a "
        "collector dying would no longer page. That is a deliberate difference "
        f"from {SCALE_TO_ZERO}, not an inconsistency to tidy away."
    )
