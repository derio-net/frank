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
from typing import Any

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRAPE_MANIFEST = (
    REPO / "apps" / "tekton" / "manifests" / "vmservicescrape-pipelines-controller.yaml"
)
SERIES_CENSUS = (
    REPO / "scripts" / "tests" / "fixtures" / "tekton" / "controller-series-census.json"
)

CONTROLLER_METRICS_PORT = "http-metrics"
CONTROLLER_SELECTOR = {"app": "tekton-pipelines-controller"}
CONTROLLER_NAMESPACE = "tekton-pipelines"

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
        f"tekton-pipelines-controller Deployment's labels — got {selector!r}"
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
