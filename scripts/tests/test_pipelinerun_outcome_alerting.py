"""Tripwires for scraping `tekton-pipelines-controller` metrics.

The controller Service publishes three ports — `http-metrics` (9090),
`http-profiling` (8008) and `probes` (8080) — and the VictoriaMetrics operator
resolves a VMServiceScrape endpoint by Service port *name*, not by number. A
scrape pointed at either of the other two ports comes up Ready with a target
that returns 200 and zero Tekton metrics: the failure mode is silent (no
CrashLoop, no Degraded Application, no error anywhere) and looks exactly like
"the alert rules built on these metrics have no data yet" rather than "the
scrape is watching the wrong port".
`test_the_scrape_manifest_targets_the_controller_metrics_port` pins the port
name so a future edit can't silently swap it for the numeric value or for one
of the other two ports.

The controller's own metrics are also dangerously unbounded. The 2026-09-13
capture (`fixtures/tekton/controller-series-census.json`) shows one metric —
`tekton_pipelines_controller_taskruns_pod_latency_milliseconds`, labelled by
TaskRun pod name — holding 87.1% of the controller's series (5721/6572): one
permanent series per TaskRun ever reconciled, forever, on a 1-month
retention. That is the same growth shape that took kube-state-metrics to
21.6 MiB on 2026-07-27, tripped `-promscrape.maxScrapeSize`, and silently
blinded every `kube_*` alert rule because vmagent discards an oversized
scrape response WHOLE rather than trimming it (see `frank-gotchas.md`,
Grafana section). `test_the_scrape_drops_the_unbounded_metric` derives which
metric is the offender from the captured census rather than hardcoding its
name, so re-capturing the fixture after a Tekton upgrade re-checks the
premise instead of silently preserving a stale one — a regression here would
re-open exactly that kube-state-metrics incident, this time against the
Tekton controller.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRAPE_MANIFEST = (
    REPO / "apps" / "tekton" / "manifests" / "vmservicescrape-pipelines-controller.yaml"
)
SERIES_CENSUS = (
    REPO / "scripts" / "tests" / "fixtures" / "tekton" / "controller-series-census.json"
)
ALERT_RULES_CM = REPO / "apps" / "grafana-alerting" / "manifests" / "alert-rules-cm.yaml"

CONTROLLER_METRICS_PORT = "http-metrics"
CONTROLLER_SELECTOR = {"app": "tekton-pipelines-controller"}
CONTROLLER_NAMESPACE = "tekton-pipelines"

# The ConfigMap key holding the Grafana provisioning document. The document is
# embedded as a YAML *string* under this key, so reading a rule out of
# `alert-rules-cm.yaml` takes two `yaml.safe_load`s — one for the ConfigMap,
# one for the value under this key. See
# `test_feature_health_workload_metrics.py`, which documents this shape and
# whose folder-wide guards (uid uniqueness, known severity, explicit
# noDataState/execErrState, the `frank-ops#N` github_issue label, the 15m
# DaemonSet-only window) apply to any rule added to that same folder,
# including the one this file adds below.
PROVISIONING_KEY = "alert-rules.yaml"

FEATURE_HEALTH_FOLDER = "feature-health"
FAILURE_RATIO_GROUP = "layer-25-pipeline-outcomes"
FAILURE_RATIO_UID = "layer-25-pipeline-failing"

# The share a metric's series must hold of the controller's total before this
# suite treats it as "the unbounded one" worth dropping. Set well above any
# plausible legitimate histogram/summary metric's share (the runner-up in the
# 2026-09-13 census is a bucket metric at 104/6572 ≈ 1.6%).
UNBOUNDED_SHARE_FLOOR = 0.50


def _load_yaml(path: pathlib.Path) -> Any:
    """Parse a single-document YAML manifest at a repo-relative path."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: pathlib.Path) -> Any:
    """Parse a JSON fixture at a repo-relative path."""
    return json.loads(path.read_text(encoding="utf-8"))


def _scrape_manifest() -> dict[str, Any]:
    assert SCRAPE_MANIFEST.exists(), (
        f"{SCRAPE_MANIFEST} does not exist — the tekton-pipelines-controller "
        "VMServiceScrape has not been created yet"
    )
    return _load_yaml(SCRAPE_MANIFEST)


def test_the_scrape_manifest_targets_the_controller_metrics_port():
    manifest = _scrape_manifest()

    assert manifest.get("apiVersion") == "operator.victoriametrics.com/v1beta1", (
        f"{SCRAPE_MANIFEST} must be an `operator.victoriametrics.com/v1beta1` "
        f"resource, got {manifest.get('apiVersion')!r}"
    )
    assert manifest.get("kind") == "VMServiceScrape", (
        f"{SCRAPE_MANIFEST} must be a VMServiceScrape, got {manifest.get('kind')!r}"
    )

    metadata = manifest.get("metadata", {})
    assert metadata.get("namespace") == CONTROLLER_NAMESPACE, (
        f"{SCRAPE_MANIFEST} must live in namespace {CONTROLLER_NAMESPACE!r} "
        f"(the controller's own namespace), got {metadata.get('namespace')!r}"
    )

    spec = manifest.get("spec", {})
    selector = spec.get("selector", {}).get("matchLabels", {})
    assert selector == CONTROLLER_SELECTOR, (
        f"{SCRAPE_MANIFEST} selector must match {CONTROLLER_SELECTOR!r} — the "
        "labels on the tekton-pipelines-controller SERVICE, which is what a "
        "VMServiceScrape selects (it discovers targets through a Service's "
        "Endpoints, never through a Deployment) — got "
        f"{selector!r}"
    )

    endpoints = spec.get("endpoints", [])
    assert len(endpoints) == 1, (
        f"{SCRAPE_MANIFEST} must declare exactly one endpoint, found "
        f"{len(endpoints)}: {endpoints!r}"
    )
    port = endpoints[0].get("port")
    assert port == CONTROLLER_METRICS_PORT, (
        f"{SCRAPE_MANIFEST} endpoint must scrape port name "
        f"{CONTROLLER_METRICS_PORT!r}, not {port!r} — the controller Service "
        "also publishes `http-profiling` (8008) and `probes` (8080), and "
        "the VM operator resolves the port by NAME, so scraping the wrong "
        "one comes up Ready with zero Tekton metrics and no error anywhere"
    )


def _largest_metric_by_series(census: dict[str, Any]) -> tuple[str, int, int]:
    """Return (metric_name, series_count, total_series) for the metric
    holding the largest share of `total_series` in the census.

    Deriving this from the fixture — rather than hardcoding the metric name
    as the premise — is the point: re-capturing the census after a Tekton
    upgrade re-checks whether the same metric is still the offender instead
    of silently preserving a stale assumption.
    """
    series_by_metric: dict[str, int] = census["series_by_metric"]
    total_series: int = census["total_series"]
    metric_name = max(series_by_metric, key=series_by_metric.get)
    return metric_name, series_by_metric[metric_name], total_series


def test_the_scrape_drops_the_unbounded_metric():
    census = _load_json(SERIES_CENSUS)
    metric_name, metric_series, total_series = _largest_metric_by_series(census)

    share = metric_series / total_series
    assert share > UNBOUNDED_SHARE_FLOOR, (
        f"{SERIES_CENSUS} no longer shows a single metric dominating the "
        f"controller's series — largest is {metric_name!r} at {share:.1%} "
        f"({metric_series}/{total_series}), below the "
        f"{UNBOUNDED_SHARE_FLOOR:.0%} floor this test uses to decide a drop "
        "is warranted. Re-evaluate whether the scrape still needs a "
        "metricRelabelConfigs drop before changing this test."
    )

    manifest = _scrape_manifest()
    endpoints = manifest.get("spec", {}).get("endpoints", [])
    assert endpoints, f"{SCRAPE_MANIFEST} has no endpoints to carry metricRelabelConfigs"
    relabel_configs = endpoints[0].get("metricRelabelConfigs", [])

    matching = [
        cfg
        for cfg in relabel_configs
        if cfg.get("action") == "drop"
        and cfg.get("source_labels") == ["__name__"]
        and cfg.get("regex") == metric_name
    ]
    assert matching, (
        f"{SCRAPE_MANIFEST} endpoint has no `metricRelabelConfigs` entry "
        f"dropping {metric_name!r} ({metric_series}/{total_series} = "
        f"{share:.1%} of the controller's series, per {SERIES_CENSUS}). Add "
        "`{action: drop, source_labels: [__name__], regex: "
        f"{metric_name}"
        "}` to the endpoint — without it this one metric grows one "
        "permanent series per TaskRun ever reconciled, the same unbounded-"
        "cardinality shape that took kube-state-metrics to 21.6 MiB and "
        "silently blinded every `kube_*` alert rule on 2026-07-27. Found: "
        f"{relabel_configs!r}"
    )


# ---------------------------------------------------------------------------
# The failure-ratio rule — `layer-25-pipeline-failing`, group
# `layer-25-pipeline-outcomes`, folder `feature-health`.
# ---------------------------------------------------------------------------


def _provisioning_document() -> dict[str, Any]:
    """Return the inner Grafana provisioning document (double YAML load)."""
    configmap = _load_yaml(ALERT_RULES_CM)
    assert configmap.get("kind") == "ConfigMap", (
        f"{ALERT_RULES_CM} is expected to be a ConfigMap wrapping the Grafana "
        "provisioning document"
    )
    data = configmap.get("data", {})
    assert PROVISIONING_KEY in data, (
        f"{ALERT_RULES_CM} has no `data.{PROVISIONING_KEY}` key — the "
        f"provisioning document moved. Keys present: {sorted(data)}"
    )
    return yaml.safe_load(data[PROVISIONING_KEY])


def _all_rules() -> list[dict[str, Any]]:
    """Every rule in the document, flattened, each enriched with `_group`/
    `_folder` from its enclosing group.

    Extracted at P4.T1.S3: `_rule_by_uid`, `_idle_rules` and `_rules_in_group`
    each used to walk `groups[].rules[]` and enrich independently — three
    copies of the same loop, one per way of *finding* a rule. This is the
    same collapse `test_feature_health_workload_metrics.py` already made
    (its own `_all_rules`); the three functions below are now filters over
    one parse instead of three re-implementations of it.
    """
    rules: list[dict[str, Any]] = []
    for group in _provisioning_document().get("groups", []):
        for rule in group.get("rules", []):
            enriched = dict(rule)
            enriched["_group"] = group.get("name")
            enriched["_folder"] = group.get("folder")
            rules.append(enriched)
    return rules


def _rule_by_uid(uid: str) -> dict[str, Any]:
    """Return a rule (enriched with `_group`/`_folder` from its enclosing
    group) by uid, or raise if no rule carries it.

    Mirrors the private helper shape in `test_feature_health_workload_metrics.py`
    (`_all_rules` + a uid lookup) — extracted here because every remaining
    task in phases 2 and 3 needs to find a rule by uid, not just this one.
    """
    for rule in _all_rules():
        if rule.get("uid") == uid:
            return rule
    raise AssertionError(f"no rule with uid {uid!r} found in {ALERT_RULES_CM}")


def _query_expr(rule: dict[str, Any]) -> str:
    """Return the refId-A datasource query's `model.expr` for a rule.

    RefId A is where this rule's whole filter lives (see the module-level
    note in the design spec: Grafana's server-side expressions can't express
    `unless`, so A carries it and B/C only reduce and threshold on top).
    """
    for datum in rule.get("data", []):
        if datum.get("refId") == "A":
            return datum.get("model", {}).get("expr", "")
    raise AssertionError(f"rule {rule.get('uid')!r} has no refId-A datasource query")


def test_the_failure_ratio_rule_is_routed_and_identified():
    rule = _rule_by_uid(FAILURE_RATIO_UID)

    assert rule["_group"] == FAILURE_RATIO_GROUP, (
        f"{FAILURE_RATIO_UID} must live in group {FAILURE_RATIO_GROUP!r}, "
        f"got {rule['_group']!r}"
    )
    assert rule["_folder"] == FEATURE_HEALTH_FOLDER, (
        f"{FAILURE_RATIO_UID}'s group must live in folder "
        f"{FEATURE_HEALTH_FOLDER!r}, got {rule['_folder']!r}"
    )

    labels = rule.get("labels") or {}
    assert labels.get("severity") == "warning", (
        f"{FAILURE_RATIO_UID} severity must be 'warning' (routes through the "
        f"existing Telegram warning policy), got {labels.get('severity')!r}"
    )
    assert labels.get("github_issue") == "frank-ops#25", (
        "the folder-wide guard "
        "test_layer_tracker_rules_carry_a_well_formed_github_issue_label "
        "requires every layer-* uid to carry a frank-ops#N label — got "
        f"{labels.get('github_issue')!r}"
    )

    assert rule.get("noDataState"), (
        f"{FAILURE_RATIO_UID} must set noDataState explicitly — Grafana "
        "defaults an omitted value to NoData, which fires the rule"
    )
    assert rule.get("execErrState"), (
        f"{FAILURE_RATIO_UID} must set execErrState explicitly"
    )


def test_the_failure_ratio_rule_uses_unless_rather_than_a_zero_comparison():
    """`unless`, not `failed >= 3 and success == 0`.

    For a pipeline that has never succeeded since controller start there is
    NO `success` series at all for it. `and ... == 0` is a vector match: the
    right-hand side has to return a series (with value 0) for the match to
    hold, and an absent series is not a zero-valued one. So `failed >= 3 and
    success == 0` silently drops the entire result for exactly the pipelines
    this rule exists to catch — the ones that have never once succeeded. This
    is the same family as the `metric == 0` trap already in
    `frank-gotchas.md`, where `== 0` is a *filter* over existing series
    rather than a comparison that can be true or false for an absent one.
    `unless` is PromQL's set-difference operator: "every series on the left
    whose label set has no match on the right", which is true whether the
    right side returns zero series or a nonzero-count one — so an absent
    success series behaves exactly like the "no successes" case it needs to.
    """
    expr = _query_expr(_rule_by_uid(FAILURE_RATIO_UID))

    assert "unless" in expr, (
        f"{FAILURE_RATIO_UID} refId-A expression must use `unless`, not an "
        f"`and ... == 0` comparison — got: {expr!r}"
    )
    assert 'status="failed"' in expr, (
        f"{FAILURE_RATIO_UID} refId-A expression must select "
        f'status="failed", got: {expr!r}'
    )
    assert 'status="success"' in expr, (
        f"{FAILURE_RATIO_UID} refId-A expression must also select "
        f'status="success" (the unless right-hand side), got: {expr!r}'
    )
    assert expr.count("sum by (pipeline)") >= 2, (
        f"{FAILURE_RATIO_UID} refId-A expression must aggregate BOTH the "
        f"failed and success sides with `sum by (pipeline)`, got: {expr!r}"
    )
    assert "== 0" not in expr and "==0" not in expr, (
        f"{FAILURE_RATIO_UID} refId-A expression must not compare against "
        "`== 0` anywhere — an absent series is not a zero-valued one, so "
        "`and success == 0` can never fire for a pipeline with zero "
        f"successes ever recorded. Got: {expr!r}"
    )


def test_the_failure_threshold_lives_in_the_query_not_in_the_expression_threshold():
    """Regression tripwire, not a red-green pair (see plan journal
    `no-refactor-because: P2.T3`).

    Grafana's server-side expressions cannot express `unless`, so refId A
    carries the WHOLE filter — including the `>= 3` noise floor — and
    returns one series per OFFENDING pipeline (value = its failure count).
    C asking `gt 0` means "did A return anything at all". Moving the `>= 3`
    out of A and into C as `gt 2` reads like a tidy-up and breaks the rule:
    A would then return every pipeline with zero successes, INCLUDING those
    with zero failures in the window (0 is still "no successes"), and C
    could never distinguish them from a genuinely failing pipeline.
    """
    rule = _rule_by_uid(FAILURE_RATIO_UID)
    expr = _query_expr(rule)

    assert ">= 3" in expr, (
        f"{FAILURE_RATIO_UID} refId-A expression must carry the `>= 3` "
        f"noise floor itself, not defer it to C's threshold. Got: {expr!r}"
    )

    condition_c = next(
        (datum for datum in rule.get("data", []) if datum.get("refId") == "C"),
        None,
    )
    assert condition_c is not None, f"{FAILURE_RATIO_UID} has no refId-C condition"
    conditions = condition_c.get("model", {}).get("conditions", [])
    evaluators = [c.get("evaluator") for c in conditions]
    assert {"type": "gt", "params": [0]} in evaluators, (
        f"{FAILURE_RATIO_UID} refId-C evaluator must be {{type: gt, params: "
        f"[0]}} — \"did A return anything at all\" — got: {evaluators!r}"
    )


# ---------------------------------------------------------------------------
# The idle dead-man rules — one per watched pipeline, same group.
# ---------------------------------------------------------------------------

IDLE_UID_STOA_STATUS_BRIDGE = "layer-25-idle-stoa-status-bridge"
IDLE_UID_GITHUB_PULL_SYNC = "layer-25-idle-github-pull-sync"
IDLE_UID_PREFIX = "layer-25-idle-"

PIPELINES_DIR = REPO / "apps" / "tekton" / "pipelines"


def _idle_rules() -> dict[str, dict[str, Any]]:
    """Return every feature-health rule whose uid starts with
    `layer-25-idle-`, keyed by uid.

    Mirrors `_rule_by_uid` above; extracted (P3.T1.S3) so tasks 2 and 3
    don't each re-walk the provisioning document looking for the same two
    rules. Filters `_all_rules()` (P4.T1.S3) rather than re-walking the
    document itself.
    """
    return {
        rule["uid"]: rule
        for rule in _all_rules()
        if rule.get("uid", "").startswith(IDLE_UID_PREFIX)
    }


def test_each_idle_rule_watches_exactly_one_pipeline():
    """The obvious shape is broken in a way that passes review.

    A single rule of the shape
    `sum by (pipeline) (increase(...{pipeline=~"a|b"}[24h])) or vector(0)`
    looks like a dead-man for both watched pipelines and is not one.
    `vector(0)` produces a series with NO labels, and PromQL's `or` returns
    its right-hand side only where the left has no matching series AT ALL.
    If `stoa-status-bridge` still has a series and `github-pull-sync` does
    not, the left side is non-empty, the union keeps it unchanged, and the
    dead pipeline contributes nothing to the result. It would be a switch
    that only fires when BOTH watched pipelines die simultaneously — which
    is exactly the failure mode a per-pipeline dead-man exists to avoid.

    So this asserts the split itself, not just that alerting "exists":
    exactly two idle rules, each carrying exactly one `pipeline="..."`
    equality selector and NO `pipeline=~` regex selector.
    """
    rules = _idle_rules()

    assert set(rules) == {IDLE_UID_STOA_STATUS_BRIDGE, IDLE_UID_GITHUB_PULL_SYNC}, (
        f"expected exactly two idle rules, {IDLE_UID_STOA_STATUS_BRIDGE!r} and "
        f"{IDLE_UID_GITHUB_PULL_SYNC!r}, got uids: {sorted(rules)}"
    )

    for uid, rule in rules.items():
        expr = _query_expr(rule)
        assert "pipeline=~" not in expr, (
            f"{uid} refId-A expression must not use a `pipeline=~` regex "
            "selector — that is the broken one-rule-with-a-regex shape "
            f"documented above. Got: {expr!r}"
        )
        equality_matches = re.findall(r'pipeline="[^"]+"', expr)
        assert len(equality_matches) == 1, (
            f"{uid} refId-A expression must contain exactly ONE "
            f'`pipeline="..."` equality selector, got {equality_matches!r} '
            f"in: {expr!r}"
        )


def test_each_idle_rule_carries_a_zero_fallback():
    """`or vector(0)`, over a bare `sum(` — not `sum by (`.

    Both halves matter and the second is the subtle one. `sum()` over an
    absent series returns an EMPTY vector, not zero, which is the only
    condition under which `or vector(0)` engages. Add `by (pipeline)` and
    the aggregation still returns empty for an absent series — but a
    reviewer reading `sum by (pipeline) (...) or vector(0)` sees a labelled
    fallback that does not exist, which is exactly how the broken
    one-rule-with-a-regex shape (see
    `test_each_idle_rule_watches_exactly_one_pipeline`) survived the first
    draft. Asserting the bare `sum(` keeps the rule readable as what it is.

    Without the fallback, the one state the dead-man exists to detect
    produces no data, `noDataState: OK` swallows it, and the switch is
    silently disarmed — the same defect class as the `longhorn-manager-.*`
    selector that matched nothing and passed every structural assertion.

    Expected GREEN immediately — P3.T1.S2 already wrote the fallback when
    it wrote the rules. This is a regression tripwire, not a red/green
    pair (plan journal: `no-refactor-because: P3.T2`).
    """
    for uid, rule in _idle_rules().items():
        expr = _query_expr(rule)
        assert "or vector(0)" in expr, (
            f"{uid} refId-A expression must fall back to `or vector(0)` — "
            "without it an absent series produces no data at all, which "
            f"`noDataState: OK` swallows silently. Got: {expr!r}"
        )
        assert "sum by (" not in expr, (
            f"{uid} refId-A expression must aggregate with a bare `sum(`, "
            "not `sum by (...)` — a labelled aggregation still collapses "
            "to empty over an absent series (so the rule would still "
            "work), but reads as carrying a fallback that isn't actually "
            f"reachable. Got: {expr!r}"
        )
        assert re.search(r"\bsum\(", expr), (
            f"{uid} refId-A expression must aggregate with `sum(` at all, "
            f"got: {expr!r}"
        )


def test_the_idle_rules_fire_below_a_floor_not_above_a_ceiling():
    """A dead-man counting RUNS is a floor question: `lt 1`, not `gt 0`.

    `frank-gotchas.md` records that `gt 0` is the convention for
    UNAVAILABILITY COUNTERS in this folder and explicitly warns against
    generalising it — folder-wide there are 27 `gt` against 12 `lt`, and
    probes, heartbeats and cert countdowns all ask "below a floor?".
    "Tidying" this rule to `gt 0` would invert it into one that fires
    whenever the pipeline is healthy and goes silent when it dies.
    """
    for uid, rule in _idle_rules().items():
        condition_c = next(
            (datum for datum in rule.get("data", []) if datum.get("refId") == "C"),
            None,
        )
        assert condition_c is not None, f"{uid} has no refId-C condition"
        conditions = condition_c.get("model", {}).get("conditions", [])
        evaluators = [c.get("evaluator") for c in conditions]
        assert {"type": "lt", "params": [1]} in evaluators, (
            f"{uid} refId-C evaluator must be {{type: lt, params: [1]}} — "
            f"a floor, not a ceiling — got: {evaluators!r}"
        )


def test_every_watched_pipeline_exists_in_the_repo():
    """The `cilium-.*` / `longhorn-manager-.*` lesson, re-applied here.

    A selector that matches nothing returns no series, passes every
    structural assertion, and is a rule deleted in all but name — and
    under `noDataState: OK` it is perfectly quiet about it. Matching the
    metric label against the Pipeline resource committed in git is the
    only offline check that can catch a rename or deletion — a live
    cluster check would also work, but this file's guards stay offline by
    convention.
    """
    for uid, rule in _idle_rules().items():
        expr = _query_expr(rule)
        matches = re.findall(r'pipeline="([^"]+)"', expr)
        assert len(matches) == 1, (
            f"{uid} refId-A expression must name exactly one pipeline by "
            f"equality, got {matches!r} in: {expr!r}"
        )
        pipeline_name = matches[0]

        pipeline_manifest = PIPELINES_DIR / f"{pipeline_name}.yaml"
        assert pipeline_manifest.exists(), (
            f"{uid} watches pipeline {pipeline_name!r}, but "
            f"{pipeline_manifest} does not exist — a renamed or deleted "
            "Pipeline resource silently disarms this dead-man rather than "
            f"failing a PR. Files present in {PIPELINES_DIR}: "
            f"{sorted(p.name for p in PIPELINES_DIR.glob('*.yaml'))}"
        )

        manifest = _load_yaml(pipeline_manifest)
        assert manifest.get("kind") == "Pipeline", (
            f"{pipeline_manifest} must be a Pipeline resource, got "
            f"{manifest.get('kind')!r}"
        )
        actual_name = manifest.get("metadata", {}).get("name")
        assert actual_name == pipeline_name, (
            f"{uid} watches pipeline {pipeline_name!r} via its metric "
            f"selector, but {pipeline_manifest} declares metadata.name: "
            f"{actual_name!r} — these must match, or the rule is watching "
            "a name the Pipeline resource no longer carries."
        )


# ---------------------------------------------------------------------------
# Cross-cutting guards (phase 4) — re-assert the 2026-05-14 lesson at this
# rule's own scope, and close the loop between the scrape and the rules.
# ---------------------------------------------------------------------------

CONTROLLER_METRICS_SAMPLE = (
    REPO / "scripts" / "tests" / "fixtures" / "tekton" / "controller-metrics-sample.txt"
)

_METRIC_NAME_BEFORE_BRACE = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]*(?=\{)")


def _rule_text(rule: dict[str, Any]) -> str:
    """A rule serialised back to YAML, for substring checks over its queries.

    Mirrors the identically-named helper in `test_feature_health_workload_metrics.py`.
    """
    return yaml.safe_dump(rule, default_flow_style=False, sort_keys=False)


def _rules_in_group(group_name: str) -> list[dict[str, Any]]:
    """Every rule whose enclosing group is named `group_name`, each carrying
    `_group`/`_folder` like `_rule_by_uid` and `_idle_rules` above. Filters
    `_all_rules()` (P4.T1.S3) rather than re-walking the document itself."""
    return [rule for rule in _all_rules() if rule["_group"] == group_name]


def test_the_new_rules_never_ask_about_pod_readiness():
    """The folder-wide `test_no_feature_health_rule_uses_pod_readiness` guard
    in `test_feature_health_workload_metrics.py` already forbids
    `kube_pod_status_ready` anywhere in the `feature-health` folder — so on
    its face this is redundant. It earns its place anyway: that guard
    protects the twelve rules MIGRATED in 2026-08, and it protects them as a
    fact about the folder *as it stood* when it was written. This one is
    attached to the `layer-25-pipeline-outcomes` group specifically, so it
    keeps failing even in a hypothetical future where the folder-wide guard
    is narrowed, relaxed, or scoped away from a new rule added here.

    The scenario it exists to catch is not hypothetical phrasing: it is
    precisely the mistake the 2026-05-14 `layer-25-cicd-down` rewrite was
    made to escape (Tekton task pods report `Ready=False` by design once
    complete, so counting them floods with false positives), and the
    resulting hole is what let a 100%-failing pipeline run silently for 39
    days (#790). A future edit to THIS group that "improves" pipeline
    detection by going back to counting task pods would be reintroducing
    the exact defect the group's own scrape was built to route around.
    """
    offenders = [
        rule["uid"]
        for rule in _rules_in_group(FAILURE_RATIO_GROUP)
        if "kube_pod_status_ready" in _rule_text(rule)
    ]
    assert not offenders, (
        f"a rule in group {FAILURE_RATIO_GROUP!r} references "
        "kube_pod_status_ready — this group exists specifically to answer "
        "pipeline-outcome questions from the controller's own metrics "
        "instead of from pod readiness, which is the exact trap the "
        "2026-05-14 layer-25-cicd-down rewrite escaped. Offending uid(s): "
        f"{offenders}"
    )


def _pipeline_outcome_rule_uids() -> list[str]:
    return [
        FAILURE_RATIO_UID,
        IDLE_UID_STOA_STATUS_BRIDGE,
        IDLE_UID_GITHUB_PULL_SYNC,
    ]


def _referenced_metric_names() -> set[str]:
    """Every metric name immediately followed by `{` in any of the three new
    rules' refId-A expressions.

    The character class stops at `(`, so this naturally skips PromQL
    functions (`sum(`, `increase(`) and only matches identifiers that are
    themselves being selected — i.e. metric names, not operators.
    """
    names: set[str] = set()
    for uid in _pipeline_outcome_rule_uids():
        expr = _query_expr(_rule_by_uid(uid))
        found = _METRIC_NAME_BEFORE_BRACE.findall(expr)
        assert found, f"{uid} refId-A expression has no metric selector at all: {expr!r}"
        names.update(found)
    return names


def _dropped_metric_regexes() -> list[str]:
    manifest = _scrape_manifest()
    endpoints = manifest.get("spec", {}).get("endpoints", [])
    assert endpoints, f"{SCRAPE_MANIFEST} has no endpoints"
    return [
        cfg["regex"]
        for cfg in endpoints[0].get("metricRelabelConfigs", [])
        if cfg.get("action") == "drop" and cfg.get("source_labels") == ["__name__"]
    ]


def test_the_scrape_and_the_rules_agree_on_the_metric_name():
    """Both halves of this change are in git — the scrape manifest and the
    alert rules — and nothing forces them to stay consistent with each
    other. A rule querying a metric the scrape's `metricRelabelConfigs`
    drops is a rule that can never fire, and nothing else in the repo would
    notice: the manifest would still apply cleanly, the rule would still
    parse and pass every other structural guard, and Grafana would report
    it `Error`-free while it silently evaluates against a metric that never
    lands in VictoriaMetrics. That is the same "passes every structural
    assertion while doing nothing" shape as the `longhorn-manager-.*`
    selector and the `cilium-.*` pod-vs-workload regex documented in
    `frank-gotchas.md`.

    This closes the loop two ways, both offline and exact because both
    halves are committed:

    1. every metric name the three new rules query must appear in the
       captured scrape fixture (`controller-metrics-sample.txt`) — proving
       the controller actually emits it;
    2. none of those metric names may match the scrape's own drop regex —
       proving the scrape does not discard the one thing the rules need.
    """
    metric_names = _referenced_metric_names()
    sample_text = CONTROLLER_METRICS_SAMPLE.read_text(encoding="utf-8")
    dropped_regexes = _dropped_metric_regexes()
    assert dropped_regexes, (
        f"{SCRAPE_MANIFEST} carries no drop `metricRelabelConfigs` to check "
        "against — has the mandatory cardinality drop been removed?"
    )

    for name in sorted(metric_names):
        assert f"{name}{{" in sample_text, (
            f"{name!r} is queried by a layer-25 pipeline-outcome rule but "
            f"does not appear in {CONTROLLER_METRICS_SAMPLE} — a rule "
            "querying a metric the scrape never sees can never fire, and "
            "nothing else in the repo would notice."
        )
        for regex in dropped_regexes:
            assert not re.fullmatch(regex, name), (
                f"{name!r} is queried by a layer-25 pipeline-outcome rule "
                f"AND matches the scrape's drop regex {regex!r} "
                f"({SCRAPE_MANIFEST}) — that rule can never fire because "
                "the scrape discards the only series it depends on."
            )
