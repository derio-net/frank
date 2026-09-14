"""Tripwire: Frank's etcd scrape, across the two files that must agree.

Frank did not scrape its own etcd for 148 days, and the reason is worth
restating because this guard exists to stop it recurring. `kubeEtcd.enabled`
is `true` by default in `victoria-metrics-k8s-stack` and Frank never disabled
it, so a headless Service, a `VMServiceScrape` and an `Endpoints` object have
existed since the cluster was built — the Endpoints object **empty the whole
time**, because the chart's Service selects pods labelled `component: etcd`
(the kubeadm layout) and Talos runs etcd as a host system service. Zero
endpoints, zero targets, zero series, and no error anywhere. Same family as
the kube-state-metrics `maxScrapeSize` drop written up in
`apps/victoria-metrics/values.yaml`: something silently yields nothing and the
only symptom is an absence.

The fix has two halves that live in different worlds:

* `patches/phase08-obs/omni-configpatch-etcd-metrics.yaml` opens etcd's
  dedicated metrics listener on `0.0.0.0:2381`. Applied by `omnictl`, by an
  operator, out of band.
* `apps/victoria-metrics/manifests/vmstaticscrape-kube-etcd.yaml` scrapes the
  three control-plane minis on that port. Applied by ArgoCD. (It began as a
  static `Endpoints` object from chart values, which ArgoCD's
  `resource.exclusions` silently never applied; see the GitOps-half section.)

Nothing else in the repo connects them. A port typo in either file, or a node
IP that moves, reproduces exactly the silent-empty-target failure being fixed —
which is why the cross-file assertions here are written as *derivations* (parse
the port out of the ConfigPatch URL, parse the IPs out of the repo's own
machine table) rather than as a third hardcoded copy of the same values.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any
from urllib.parse import urlparse

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]

CONFIGPATCH = (
    REPO / "patches" / "phase08-obs" / "omni-configpatch-etcd-metrics.yaml"
)
VM_VALUES = REPO / "apps" / "victoria-metrics" / "values.yaml"
INFRA_RULE = REPO / "agents" / "rules" / "frank-infrastructure.md"

# The Omni resource type and the machine set the patch must be scoped to.
# etcd runs only on control planes; a fleet-wide patch would push etcd args at
# four workers that run no etcd at all.
CONFIGPATCH_TYPE = "ConfigPatches.omni.sidero.dev"
CLUSTER_LABEL = "omni.sidero.dev/cluster"
MACHINE_SET_LABEL = "omni.sidero.dev/machine-set"
CONTROL_PLANE_MACHINE_SET = "frank-control-planes"


# The machine table in `agents/rules/frank-infrastructure.md` is the repo's own
# statement of which node is what. Deriving the control-plane addresses from it
# — rather than restating them here — is what keeps this guard from becoming
# the THIRD place Frank's node IPs live.
_MACHINE_ROW = re.compile(
    r"^\|\s*(?P<host>[\w-]+)\s*\|\s*(?P<ip>\d+\.\d+\.\d+\.\d+)\s*\|"
    r"\s*(?P<role>[\w-]+)\s*\|"
)


def _documented_control_plane_ips() -> list[str]:
    """Control-plane IPs, in table order, parsed out of the machine table."""
    text = INFRA_RULE.read_text(encoding="utf-8")
    ips: list[str] = []
    for line in text.splitlines():
        match = _MACHINE_ROW.match(line.strip())
        if match and match.group("role") == "control-plane":
            ips.append(match.group("ip"))
    assert len(ips) == 3, (
        f"expected 3 control-plane rows in {INFRA_RULE.relative_to(REPO)}'s "
        f"machine table, parsed {len(ips)}: {ips}. Either the table's shape "
        "changed and this derivation is now reading nothing, or Frank's "
        "control plane is no longer three nodes — in which case "
        "the etcd VMStaticScrape targets need revisiting, not this regex."
    )
    return ips


CONTROL_PLANE_IPS = _documented_control_plane_ips()


def _load_configpatch() -> dict[str, Any]:
    """The outer Omni ConfigPatch document."""
    assert CONFIGPATCH.exists(), (
        f"{CONFIGPATCH.relative_to(REPO)} does not exist — the Talos "
        "ConfigPatch that opens etcd's metrics listener is the half of this "
        "change that makes the scrape target reachable at all"
    )
    return yaml.safe_load(CONFIGPATCH.read_text(encoding="utf-8"))


def _configpatch_machine_config() -> dict[str, Any]:
    """The Talos machine config embedded in `spec.data`.

    `spec.data` is a YAML document carried as a *string*, so reading anything
    inside it needs two loads — the same double-load shape as the Grafana alert
    ConfigMap and the headscale config guard.
    """
    document = _load_configpatch()
    spec = document.get("spec") or {}
    data = spec.get("data")
    assert isinstance(data, str), (
        f"{CONFIGPATCH.relative_to(REPO)} has no `spec.data` YAML string — an "
        "Omni ConfigPatch carries the Talos machine config as an embedded "
        f"document, not as nested mapping keys. Got: {type(data).__name__}"
    )
    inner = yaml.safe_load(data)
    assert isinstance(inner, dict), (
        f"{CONFIGPATCH.relative_to(REPO)}'s `spec.data` does not parse to a "
        "mapping — the embedded machine config is malformed"
    )
    return inner


def _listen_metrics_urls() -> str:
    inner = _configpatch_machine_config()
    extra_args = (
        ((inner.get("cluster") or {}).get("etcd") or {}).get("extraArgs") or {}
    )
    assert "listen-metrics-urls" in extra_args, (
        f"{CONFIGPATCH.relative_to(REPO)} does not set "
        "`cluster.etcd.extraArgs.listen-metrics-urls`. Without it etcd serves "
        "/metrics only on its client port (2379) behind mutual TLS, and the "
        f"scrape has nothing to reach. Found extraArgs: {sorted(extra_args)}"
    )
    return str(extra_args["listen-metrics-urls"])


def test_configpatch_opens_the_metrics_listener():
    """The ConfigPatch is a control-plane-scoped patch opening 0.0.0.0:2381.

    Plain HTTP is deliberate and is argued in the design spec: the metrics
    listener serves `/metrics` and `/health` only and carries no key material,
    whereas scraping 2379 needs an etcd client certificate that also grants
    full read/write to cluster state.

    The machine-set assertion is the load-bearing one here.
    """
    document = _load_configpatch()
    metadata = document.get("metadata") or {}

    assert metadata.get("type") == CONFIGPATCH_TYPE, (
        f"{CONFIGPATCH.relative_to(REPO)} must declare "
        f"`metadata.type: {CONFIGPATCH_TYPE}` so `omnictl apply` recognises it "
        f"as a ConfigPatch. Got: {metadata.get('type')!r}"
    )

    labels = metadata.get("labels") or {}
    assert labels.get(CLUSTER_LABEL) == "frank", (
        f"{CONFIGPATCH.relative_to(REPO)} must be scoped to the frank cluster "
        f"via `{CLUSTER_LABEL}`. Got: {labels.get(CLUSTER_LABEL)!r}"
    )
    assert labels.get(MACHINE_SET_LABEL) == CONTROL_PLANE_MACHINE_SET, (
        f"{CONFIGPATCH.relative_to(REPO)} must be scoped to the "
        f"`{CONTROL_PLANE_MACHINE_SET}` machine set via "
        f"`{MACHINE_SET_LABEL}`. etcd runs only on control planes, so a "
        "fleet-wide patch would push etcd args to four workers that run no "
        f"etcd. Got: {labels.get(MACHINE_SET_LABEL)!r}"
    )

    assert _listen_metrics_urls() == "http://0.0.0.0:2381", (
        "expected `listen-metrics-urls: http://0.0.0.0:2381` — the dedicated "
        "read-only metrics listener. Got: " f"{_listen_metrics_urls()!r}"
    )


# ---------------------------------------------------------------------------
# The GitOps half: a VMStaticScrape aimed at the three control-plane minis.
#
# #762 first shipped this half as chart values. `kubeEtcd.endpoints` makes
# victoria-metrics-k8s-stack render a selector-less Service plus a STATIC
# `Endpoints` object. It rendered perfectly and deployed nothing. ArgoCD's
# `resource.exclusions` (apps/argocd/values.yaml, reproducing the argo-cd chart
# defaults) exclude Endpoints and EndpointSlice cluster-wide, so ArgoCD dropped
# the object on every sync and still reported the app Synced/Healthy. The Service
# moved to 2381, the Endpoints object stayed empty, `up{job="kube-etcd"}` never
# existed, and the absent() watchdog fired fifteen minutes after the merge
# (2026-09-13). The same silent empty-target failure this layer exists to fix,
# one layer further from the chart, and invisible to `helm template`.
#
# A VMStaticScrape names its targets itself and is a kind ArgoCD applies, so the
# scrape no longer depends on an object Frank's GitOps loop cannot deliver. The
# chart's own kube-etcd block is switched OFF. Left on, it keeps rendering the
# pod-selector Service that matches nothing on Talos, plus an upstream etcd
# dashboard and VMRule that follow it.
#
# The negative assertions still matter more than the positive ones. etcd's
# metrics listener is unauthenticated plain HTTP, and any borrowed
# kubeadm-shaped auth (bearer token, TLS) produces a target that fails forever
# while the manifest reads as careful.
# ---------------------------------------------------------------------------

VM_MANIFESTS = REPO / "apps" / "victoria-metrics" / "manifests"
ETCD_STATIC_SCRAPE = VM_MANIFESTS / "vmstaticscrape-kube-etcd.yaml"
ARGOCD_VALUES = REPO / "apps" / "argocd" / "values.yaml"

VM_OPERATOR_API = "operator.victoriametrics.com/v1beta1"


def _vm_values() -> dict[str, Any]:
    return yaml.safe_load(VM_VALUES.read_text(encoding="utf-8"))


def _etcd_static_scrape() -> dict[str, Any]:
    assert ETCD_STATIC_SCRAPE.exists(), (
        f"{ETCD_STATIC_SCRAPE.relative_to(REPO)} does not exist. It is the object "
        "that actually scrapes etcd: the chart's static Endpoints object can "
        "never be applied by ArgoCD (Endpoints is in resource.exclusions), so "
        "without this manifest Frank is back to zero etcd targets and no error."
    )
    documents = [
        document
        for document in yaml.safe_load_all(
            ETCD_STATIC_SCRAPE.read_text(encoding="utf-8")
        )
        if document
    ]
    assert len(documents) == 1, (
        f"{ETCD_STATIC_SCRAPE.relative_to(REPO)} should hold exactly one "
        f"document, the etcd VMStaticScrape. Found {len(documents)}."
    )
    document = documents[0]
    assert (
        document.get("apiVersion") == VM_OPERATOR_API
        and document.get("kind") == "VMStaticScrape"
    ), (
        f"{ETCD_STATIC_SCRAPE.relative_to(REPO)} must be a {VM_OPERATOR_API} "
        f"VMStaticScrape. Got apiVersion={document.get('apiVersion')!r} "
        f"kind={document.get('kind')!r}"
    )
    return document


def _etcd_target_endpoint() -> dict[str, Any]:
    spec = _etcd_static_scrape().get("spec") or {}
    endpoints = spec.get("targetEndpoints") or []
    assert len(endpoints) == 1, (
        "expected exactly one spec.targetEndpoints entry carrying the three "
        f"minis. Got {len(endpoints)}. A second entry is where a stray target "
        "with different scheme or auth would hide."
    )
    return endpoints[0]


def _etcd_targets() -> list[tuple[str | None, int | None]]:
    """(host, port) for every scrape target, parsed rather than string-matched."""
    targets = _etcd_target_endpoint().get("targets") or []
    assert targets, "the etcd VMStaticScrape lists no targets"
    parsed = []
    for target in targets:
        split = urlparse(f"//{target}")
        parsed.append((split.hostname, split.port))
    return parsed


def test_chart_kube_etcd_scrape_is_disabled():
    """The chart's kube-etcd block is explicitly OFF and carries no leftovers.

    `kubeEtcd.enabled` defaults to TRUE, with a pod selector that matches nothing
    on Talos. So "just remove the block" silently restores the 148-day inert
    scrape. It has to be stated false. Leftover `endpoints`/`service`/`vmScrape`
    keys would be dead configuration that reads as the live scrape path, and
    the `endpoints` key is exactly what renders the Endpoints object ArgoCD
    drops.
    """
    kube_etcd = _vm_values().get("kubeEtcd")
    assert isinstance(kube_etcd, dict) and kube_etcd.get("enabled") is False, (
        f"{VM_VALUES.relative_to(REPO)} must set `kubeEtcd.enabled: false`. The "
        "chart default is true, which renders a pod-selector Service matching "
        "nothing on Talos, or (with endpoints:) a static Endpoints object "
        f"ArgoCD never applies. Got kubeEtcd={kube_etcd!r}"
    )
    leftovers = sorted(
        key for key in ("endpoints", "service", "vmScrape") if key in kube_etcd
    )
    assert not leftovers, (
        f"kubeEtcd is disabled but still carries {leftovers}. Those keys drive "
        "nothing now and read as if they were the scrape. The scrape lives in "
        f"{ETCD_STATIC_SCRAPE.relative_to(REPO)}."
    )


def test_etcd_is_scraped_by_a_vmstaticscrape():
    """One VMStaticScrape, in the monitoring namespace, plain HTTP, no auth."""
    document = _etcd_static_scrape()
    metadata = document.get("metadata") or {}
    assert metadata.get("namespace") == "monitoring", (
        "the etcd VMStaticScrape must live in `monitoring`, alongside the VMAgent "
        f"that selects it. Got namespace={metadata.get('namespace')!r}"
    )

    spec = document.get("spec") or {}
    assert str(spec.get("jobName") or "").strip(), (
        "the etcd VMStaticScrape has no `spec.jobName`. Without it vmagent names "
        "the job itself, and every `up{job=...}` selector in the six rules "
        "points at a job that does not exist."
    )

    endpoint = _etcd_target_endpoint()
    assert endpoint.get("scheme") == "http", (
        "the etcd scrape must use `scheme: http`. The metrics listener is "
        f"plain HTTP by design. Got: {endpoint.get('scheme')!r}"
    )
    assert endpoint.get("path") == "/metrics", (
        f"the etcd scrape must read `/metrics`. Got: {endpoint.get('path')!r}"
    )

    forbidden = sorted(
        key
        for key in (
            "bearerTokenFile",
            "bearerTokenSecret",
            "tlsConfig",
            "basicAuth",
            "oauth2",
            "authorization",
        )
        if key in endpoint
    )
    assert not forbidden, (
        f"the etcd scrape endpoint carries authentication: {forbidden}. Port "
        "2381 is unauthenticated plain HTTP; a token or TLS config there is the "
        "kubeadm-shaped default that makes the target fail while it reads as "
        "careful."
    )


# ---------------------------------------------------------------------------
# The two halves cannot drift apart.
#
# These are the whole reason this file exists. The ConfigPatch and the scrape
# live in different directories and are applied by different tools: `omnictl`,
# by hand, by an operator, and ArgoCD, from `main`. No deploy, no sync status
# and no review of either file alone can notice that they no longer agree. A
# port typo in either, or a node IP that moves, reproduces precisely the silent
# empty-target failure this layer was written to fix.
#
# Both are written as DERIVATIONS. Restating the port or the addresses here
# would make this file a third copy that drifts alongside the other two, which
# is the opposite of a guard.
# ---------------------------------------------------------------------------


def test_listener_port_matches_the_scrape_target_port():
    """The port etcd listens on is the port every scrape target dials.

    Parsed out of the ConfigPatch's URL rather than asserted as a literal, so
    the test cannot agree with a typo it also contains.
    """
    url = _listen_metrics_urls()
    listener_port = urlparse(url).port
    assert listener_port is not None, (
        f"could not parse a port out of `listen-metrics-urls: {url}` in "
        f"{CONFIGPATCH.relative_to(REPO)}. etcd needs an explicit port here, "
        "and this guard cannot compare what it cannot read."
    )

    target_ports = sorted({port for _, port in _etcd_targets()}, key=str)

    assert target_ports == [listener_port], (
        "PORT MISMATCH between the two halves of the etcd scrape:\n"
        f"  {CONFIGPATCH.relative_to(REPO)} opens etcd's metrics listener on "
        f"port {listener_port} (listen-metrics-urls: {url})\n"
        f"  {ETCD_STATIC_SCRAPE.relative_to(REPO)} dials ports {target_ports!r}\n"
        "These files are applied by different tools and nothing else connects "
        "them, so a mismatch does not fail a deploy. It produces a scrape "
        "target that is down forever while both files look correct in "
        "isolation."
    )


def test_endpoints_match_the_documented_control_plane_ips():
    """The scrape targets exactly the nodes the repo says are the control plane.

    etcd runs on the control plane and nowhere else. An address in one list and
    not the other is either a node that is scraped but runs no etcd, or an etcd
    member that is not scraped at all. Neither shows up as an error, only as
    missing series.
    """
    documented = CONTROL_PLANE_IPS
    configured = [host for host, _ in _etcd_targets()]

    assert configured == documented, (
        "TARGET MISMATCH between the etcd scrape and the repo's machine table:\n"
        f"  {ETCD_STATIC_SCRAPE.relative_to(REPO)} targets = {configured!r}\n"
        f"  {INFRA_RULE.relative_to(REPO)} control-plane rows = {documented!r}"
    )


# ---------------------------------------------------------------------------
# ArgoCD must be able to deliver the scrape at all.
#
# This is the assertion #762 lacked. Every guard above passed while the scrape
# was undeployable, because they asserted what the manifests SAY and never
# whether ArgoCD would APPLY them. ArgoCD applies nothing of an excluded kind:
# no error, only an ExcludedResourceWarning condition on an app that still reads
# Synced/Healthy. So the exclusion list is parsed from the repo (fail-closed: a
# parser that finds no Endpoints exclusion is reading nothing) and every kind
# the scrape path depends on is checked against it.
# ---------------------------------------------------------------------------


def _argocd_in_cluster_exclusions() -> list[tuple[str, str]]:
    """(apiGroup, kind) pairs ArgoCD excludes for the in-cluster destination.

    Entries scoped to other clusters (the vCluster Pod exclusion) do not apply
    to Frank's own destination and are skipped. An entry with no `clusters` key
    applies everywhere.
    """
    values = yaml.safe_load(ARGOCD_VALUES.read_text(encoding="utf-8"))
    raw = ((values.get("configs") or {}).get("cm") or {}).get("resource.exclusions")
    assert isinstance(raw, str) and raw.strip(), (
        f"could not find configs.cm.resource.exclusions in "
        f"{ARGOCD_VALUES.relative_to(REPO)}. This guard checks the scrape against "
        "the kinds ArgoCD drops, and cannot do that if the list moved."
    )
    pairs: list[tuple[str, str]] = []
    for entry in yaml.safe_load(raw) or []:
        clusters = entry.get("clusters") or ["*"]
        if "*" not in clusters:
            continue
        for group in entry.get("apiGroups") or ["*"]:
            for kind in entry.get("kinds") or ["*"]:
                pairs.append((str(group), str(kind)))
    assert ("", "Endpoints") in pairs, (
        "parsed ArgoCD resource.exclusions without finding the chart-default "
        "Endpoints exclusion. Either the list changed shape and this parser now "
        f"reads nothing, or Endpoints is no longer excluded. Parsed: {pairs}"
    )
    return pairs


def _is_excluded(api_version: str, kind: str, pairs: list[tuple[str, str]]) -> bool:
    group = api_version.rsplit("/", 1)[0] if "/" in api_version else ""
    return any(
        ex_group in ("*", group) and ex_kind in ("*", kind)
        for ex_group, ex_kind in pairs
    )


def test_the_etcd_scrape_depends_on_no_kind_argocd_excludes():
    """Neither the scrape object nor the chart path may be an excluded kind.

    Two halves. The VMStaticScrape must itself be deliverable. And no chart
    control-plane block may be left supplying `endpoints:`, which renders the
    static Endpoints object this bug was made of.
    """
    pairs = _argocd_in_cluster_exclusions()
    document = _etcd_static_scrape()
    assert not _is_excluded(document["apiVersion"], document["kind"], pairs), (
        f"{document['kind']} ({document['apiVersion']}) is in ArgoCD's "
        "resource.exclusions, so ArgoCD will never apply the etcd scrape and "
        "will report the app Synced regardless."
    )

    rendering_endpoints = sorted(
        component
        for component, block in _vm_values().items()
        if component.startswith("kube")
        and isinstance(block, dict)
        and block.get("enabled", True) is not False
        and block.get("endpoints")
    )
    assert not rendering_endpoints, (
        f"{VM_VALUES.relative_to(REPO)} still supplies `endpoints:` on "
        f"{rendering_endpoints}. That makes the chart render a static Endpoints "
        "object, and Endpoints is in ArgoCD's resource.exclusions, so the object "
        "is silently never applied (#762, 2026-09-13). Scrape a host service "
        "with a VMStaticScrape instead."
    )


def test_no_git_manifest_is_a_kind_argocd_silently_drops():
    """Repo-wide: a manifest of an excluded kind is a deploy that never happens.

    Scoped to raw manifest directories (`apps/*/manifests/`), where every
    document with an apiVersion and kind is meant to reach the cluster. Files
    that do not parse as YAML (Helm templates) are skipped; they are not raw
    manifests.
    """
    pairs = _argocd_in_cluster_exclusions()
    offenders: list[str] = []
    for manifest in sorted((REPO / "apps").glob("*/manifests/**/*.y*ml")):
        try:
            documents = list(yaml.safe_load_all(manifest.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            continue
        for document in documents:
            if not isinstance(document, dict):
                continue
            api_version, kind = document.get("apiVersion"), document.get("kind")
            if not (isinstance(api_version, str) and isinstance(kind, str)):
                continue
            if _is_excluded(api_version, kind, pairs):
                name = (document.get("metadata") or {}).get("name")
                offenders.append(f"{manifest.relative_to(REPO)}: {kind}/{name}")
    assert not offenders, (
        "git-managed manifest(s) of a kind ArgoCD's resource.exclusions drop. "
        "ArgoCD will never apply them and will still report their app Synced:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# The signals: six Grafana-managed alert rules.
#
# A scrape that nobody alerts on is a dashboard, not observability — and the
# whole reason this layer exists is that a green dashboard is exactly what 148
# days of silence looked like. These assertions are in two halves, deliberately.
#
# The first half asserts the rules are PRESENT and STRUCTURALLY VALID: right
# folder, unique uid, the 3-step A -> B -> C SSE shape Grafana 12.x requires,
# and explicit noData/execErr states. Every one of those failures is silent in
# production — a classic-condition rule fails provisioning with `sse.parseError`
# and simply never evaluates; a duplicate uid means one rule overwrites the
# other org-wide and the loser never evaluates either.
#
# The second half asserts the rules are CORRECT rather than merely present, and
# that half is the point of the file.
# ---------------------------------------------------------------------------

ALERT_RULES_CM = (
    REPO / "apps" / "grafana-alerting" / "manifests" / "alert-rules-cm.yaml"
)

# The ConfigMap key holding the Grafana provisioning document. The document is
# carried as a YAML *string*, so reading a rule needs two loads — the same
# double-load shape as the Omni ConfigPatch above.
PROVISIONING_KEY = "alert-rules.yaml"

# The folder `notification-policy-cm.yaml` routes to the Health Bridge Webhook,
# via its last policy (`grafana_folder="feature-health"`).
FEATURE_HEALTH = "feature-health"

# Frank's VictoriaMetrics datasource. A rule pointed at any other uid provisions
# fine and then errors on every evaluation.
GRAFANA_DATASOURCE_UID = "P4169E866C3094E38"

# The sentinel uid that routes a node to Grafana's server-side expression
# engine. Nodes B and C are expressions, not queries: pointing either at the
# VictoriaMetrics uid asks VictoriaMetrics to execute `type: reduce`.
EXPRESSION_DATASOURCE_UID = "__expr__"

# Every reduce node in `alert-rules-cm.yaml` — all 48 of them — uses `last`.
# These rules alert on the CURRENT value, so `last` is the reducer that matches
# the question being asked.
REDUCER = "last"

# The job label the scrape produces. Written here only so failure messages can
# name it — NOTHING asserts against this constant. The rules are checked against
# the value DERIVED from the VMStaticScrape's jobName in
# `test_absent_watchdog_selects_the_job_the_scrape_declares`, because a constant
# and a rule that agree with each other are just the same paste twice.
ETCD_JOB = "kube-etcd"

# The two rules that reach Telegram. Loss of quorum is an operator problem;
# everything else is a tracked bug.
ETCD_PAGING_UIDS: frozenset[str] = frozenset(
    {
        "layer-2-etcd-no-leader",
        "layer-2-etcd-member-down",
    }
)

# The four that go to the Health Bridge and nowhere else.
ETCD_BRIDGE_ONLY_UIDS: frozenset[str] = frozenset(
    {
        "layer-2-etcd-scrape-absent",
        "layer-2-etcd-leader-changes",
        "layer-2-etcd-wal-fsync-slow",
        "layer-2-etcd-db-quota",
    }
)

ETCD_RULE_UIDS: frozenset[str] = ETCD_PAGING_UIDS | ETCD_BRIDGE_ONLY_UIDS

# The rule that fires when the whole scrape disappears — the guard against this
# layer silently reverting to the state it was built to fix.
ETCD_ABSENT_WATCHDOG = "layer-2-etcd-scrape-absent"

# The minimum `for:` on a paging rule. A planned Talos rolling reboot takes one
# etcd member down and elects a new leader entirely legitimately; the 2026-08-02
# control-plane roll took roughly 7 minutes and produced 48 alerts against a
# healthy cluster.
PAGING_MIN_FOR_MINUTES = 10


def _provisioning_document() -> dict[str, Any]:
    """The inner Grafana provisioning document (double YAML load)."""
    configmap = yaml.safe_load(ALERT_RULES_CM.read_text(encoding="utf-8"))
    assert configmap.get("kind") == "ConfigMap", (
        f"{ALERT_RULES_CM.relative_to(REPO)} is expected to be a ConfigMap "
        "wrapping the Grafana provisioning document"
    )
    data = configmap.get("data") or {}
    assert PROVISIONING_KEY in data, (
        f"{ALERT_RULES_CM.relative_to(REPO)} has no `data.{PROVISIONING_KEY}` "
        f"key — the provisioning document moved. Keys present: {sorted(data)}"
    )
    document = yaml.safe_load(data[PROVISIONING_KEY])
    assert document.get("apiVersion") == 1, (
        "expected a Grafana alerting provisioning document (apiVersion: 1)"
    )
    return document


def _all_alert_rules() -> list[dict[str, Any]]:
    """Every rule in the document, flattened, each carrying its group context.

    `folder` — the routing key — is a GROUP-level field, so a flat list of
    rules alone would drop exactly the property most worth asserting.
    """
    rules: list[dict[str, Any]] = []
    for group in _provisioning_document().get("groups") or []:
        for rule in group.get("rules") or []:
            enriched = dict(rule)
            enriched["_group"] = group.get("name")
            enriched["_folder"] = group.get("folder")
            rules.append(enriched)
    return rules


def _etcd_rules() -> dict[str, dict[str, Any]]:
    """The six etcd rules, by uid. Fails loudly if any is missing."""
    by_uid = {
        rule.get("uid"): rule
        for rule in _all_alert_rules()
        if rule.get("uid") in ETCD_RULE_UIDS
    }
    missing = sorted(ETCD_RULE_UIDS - set(by_uid))
    assert not missing, (
        "etcd alert rule uid(s) absent from "
        f"{ALERT_RULES_CM.relative_to(REPO)}: {missing}. A scrape with no rules "
        "on it is a dashboard, not monitoring — and a dashboard nobody opens is "
        "what 148 days of unmonitored etcd already looked like."
    )
    return by_uid


def _for_minutes(value: Any) -> int:
    """`for:` as whole minutes. Grafana accepts 0m / 30s / 10m / 1h / 3h."""
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d+)([smh])", text)
    assert match, (
        f"could not parse a duration out of `for: {value!r}` — Grafana writes "
        "these as e.g. 0m / 10m / 1h"
    )
    amount, unit = int(match.group(1)), match.group(2)
    return {"s": amount // 60, "m": amount, "h": amount * 60}[unit]


def test_the_six_etcd_rules_exist_in_the_feature_health_folder():
    """`folder` is a group-level field, so one mistyped group header silently
    moves every rule under it off the Health Bridge route.

    The failure is invisible from the rule itself: a rule in a nonexistent
    folder still evaluates and still fires — it just matches no route in
    `notification-policy-cm.yaml`, whose last entry keys on
    `grafana_folder="feature-health"`. Nothing errors; the alert goes nowhere.
    """
    wrong = {
        uid: rule["_folder"]
        for uid, rule in _etcd_rules().items()
        if rule["_folder"] != FEATURE_HEALTH
    }
    assert not wrong, (
        "etcd alert rule(s) outside the "
        f"`{FEATURE_HEALTH}` folder (uid -> folder): {wrong}. "
        "notification-policy-cm.yaml routes the Health Bridge on "
        f'grafana_folder="{FEATURE_HEALTH}", so a folder typo does not error — '
        "it silently unroutes the rule."
    )


def test_etcd_rule_uids_do_not_collide_with_any_existing_rule():
    """Grafana keys provisioned rules by uid ORG-WIDE, not per folder.

    A duplicate is not rejected at provisioning time — one rule simply
    overwrites the other, and the loser never evaluates again. Scoped to the
    six new uids on purpose: the folder-wide uniqueness guard already lives in
    `test_feature_health_workload_metrics.py`, and what this phase can newly
    break is a NEW uid landing on top of an existing rule.
    """
    counts: dict[str, int] = {}
    for rule in _all_alert_rules():
        uid = rule.get("uid")
        if uid in ETCD_RULE_UIDS:
            counts[uid] = counts.get(uid, 0) + 1

    collisions = sorted(uid for uid, count in counts.items() if count > 1)
    assert not collisions, (
        "etcd alert rule uid(s) appear more than once in the provisioning "
        f"document: {collisions}. Grafana keys rules by uid across the whole "
        "org, so one of each pair silently overwrites the other and never "
        "evaluates."
    )


def test_etcd_rules_use_the_three_step_sse_shape():
    """A -> B -> C, or the rule never evaluates at all.

    Grafana 12.x rejects a classic-condition rule with `sse.parseError` at
    provisioning time. The rule is then simply absent from the evaluator while
    still present in this file, which is the most deceptive failure available:
    the config says the alert exists and the cluster disagrees silently.

    `A` queries the datasource, `B` reduces the series to one value, `C`
    thresholds `B`, and `condition: C` names which node decides. Every existing
    rule in this folder has that shape; these six copy it.

    Three of the assertions below are about failures that are *silent no-ops*
    rather than loud rejections, and each was missing from the first draft of
    this test while this docstring already claimed to cover them:

    * **`datasourceUid: __expr__` on B and C.** The expression nodes are not
      datasource queries; `__expr__` is the sentinel that routes them to the
      server-side expression engine. Point B or C at the VictoriaMetrics uid
      instead and Grafana tries to run `type: reduce` as a PromQL query.
    * **B's `reducer`.** A reduce node with no reducer has nothing to reduce
      *with*. All 48 reduce nodes in this document use `last`; an omitted one is
      a field you cannot see missing in a diff.
    * **C's condition must carry an `evaluator` with a `type` and `params`.**
      Counting the conditions to 1 accepts `conditions: [{}]` — a threshold
      node with no threshold, which is a rule that can never fire while looking
      structurally complete.
    """
    problems: dict[str, list[str]] = {}
    for uid, rule in _etcd_rules().items():
        faults: list[str] = []
        nodes = {node.get("refId"): node for node in rule.get("data") or []}

        if sorted(nodes) != ["A", "B", "C"]:
            faults.append(f"refIds are {sorted(nodes)}, expected ['A', 'B', 'C']")
        else:
            a_model = nodes["A"].get("model") or {}
            if nodes["A"].get("datasourceUid") != GRAFANA_DATASOURCE_UID:
                faults.append(
                    "node A datasourceUid is "
                    f"{nodes['A'].get('datasourceUid')!r}, expected "
                    f"{GRAFANA_DATASOURCE_UID!r}"
                )
            if not str(a_model.get("expr") or "").strip():
                faults.append("node A carries no PromQL `expr`")

            for ref in ("B", "C"):
                if nodes[ref].get("datasourceUid") != EXPRESSION_DATASOURCE_UID:
                    faults.append(
                        f"node {ref} datasourceUid is "
                        f"{nodes[ref].get('datasourceUid')!r}, expected "
                        f"{EXPRESSION_DATASOURCE_UID!r} — the expression nodes "
                        "are evaluated server-side, not by the datasource"
                    )

            b_model = nodes["B"].get("model") or {}
            if b_model.get("type") != "reduce":
                faults.append(f"node B type is {b_model.get('type')!r}, expected 'reduce'")
            if b_model.get("expression") != "A":
                faults.append(
                    f"node B reduces {b_model.get('expression')!r}, expected 'A'"
                )
            if b_model.get("reducer") != REDUCER:
                faults.append(
                    f"node B reducer is {b_model.get('reducer')!r}, expected "
                    f"{REDUCER!r} — a reduce node with no reducer has nothing "
                    "to reduce with, and every reduce node in this document "
                    f"uses {REDUCER!r}"
                )

            c_model = nodes["C"].get("model") or {}
            if c_model.get("type") != "threshold":
                faults.append(
                    f"node C type is {c_model.get('type')!r}, expected 'threshold'"
                )
            if c_model.get("expression") != "B":
                faults.append(
                    f"node C thresholds {c_model.get('expression')!r}, expected 'B'"
                )
            conditions = c_model.get("conditions") or []
            if len(conditions) != 1:
                faults.append(
                    f"node C has {len(conditions)} threshold condition(s), expected 1"
                )
            else:
                # `conditions: [{}]` counts as one and thresholds nothing.
                evaluator = (conditions[0] or {}).get("evaluator") or {}
                if not evaluator.get("type"):
                    faults.append(
                        "node C's threshold condition has no `evaluator.type` "
                        f"(gt / lt / within_range): {conditions[0]!r} — a "
                        "threshold with no comparison never fires"
                    )
                params = evaluator.get("params")
                if not isinstance(params, list) or not params:
                    faults.append(
                        "node C's threshold condition has no non-empty "
                        f"`evaluator.params`: {conditions[0]!r} — the threshold "
                        "VALUE is missing, so the rule is decorative"
                    )

        if rule.get("condition") != "C":
            faults.append(f"`condition` is {rule.get('condition')!r}, expected 'C'")

        if faults:
            problems[uid] = faults

    assert not problems, (
        "etcd alert rule(s) are not in the 3-step A -> B -> C SSE shape. "
        "Grafana 12.x fails a classic-condition rule with `sse.parseError` at "
        "provisioning time, so the rule is missing from the evaluator while "
        f"still present in this file: {problems}"
    )


def test_etcd_rules_declare_nodata_ok_and_execerr_error():
    """`noDataState: OK` is the deliberate posture, and it has a cost.

    Grafana defaults an omitted `noDataState` to `NoData`, which FIRES. Every
    rule here that queries an `etcd_server_*` / `etcd_disk_*` / `etcd_mvcc_*`
    series is NoData whenever the scrape is failing — no scrape, no samples —
    so omitting the field would fire against a healthy cluster.

    **The `up{job=...}` rules are the asymmetric case, and an earlier version of
    this docstring stated the falsehood as fact.** It said "before the
    ConfigPatch lands the target is simply down, so every one of these rules
    sits at NoData". That is wrong for exactly one of them, and it is the one
    that pages. `up` is not exported by etcd — the SCRAPER synthesises it, once
    per configured target, every interval: `1` on a successful scrape and `0` on
    a failed one. It is never absent while the target is configured, and
    declaring the scrape's targets configures three of them the moment ArgoCD
    syncs. So with the listener still closed, `layer-2-etcd-member-down`
    (`up < 1`) is not NoData — it is `0 < 1`, true, and it pages after `for:
    10m`. That is why the ConfigPatch is a PRE-MERGE gate (see
    `patches/phase08-obs/README.md` and the design spec's "Ordering is NOT safe
    in either direction"), and why `test_the_ordering_claim_is_not_reverted`
    below guards the docs that say so.

    Live instance of the same shape on Frank, 2026-08-03:
    `count(up==0) by (job)` returns `{job="kube-scheduler"} 3` — populated
    Endpoints, failing scrape, `up=0` rather than NoData.

    The cost of `noDataState: OK` is that a scrape which disappears LATER also
    reads OK, which is precisely why `layer-2-etcd-scrape-absent` exists.
    Stating both fields is what makes that trade-off visible in the file instead
    of implied by a default.
    """
    offenders = {
        uid: {
            "noDataState": rule.get("noDataState"),
            "execErrState": rule.get("execErrState"),
        }
        for uid, rule in _etcd_rules().items()
        if rule.get("noDataState") != "OK" or rule.get("execErrState") != "Error"
    }
    assert not offenders, (
        "etcd alert rule(s) do not declare `noDataState: OK` / "
        f"`execErrState: Error`: {offenders}. An omitted noDataState defaults "
        "to NoData, which fires — and the five etcd_*-querying rules are NoData "
        "by construction until the operator applies the Talos ConfigPatch. (The "
        "up{job=...} rules are NOT: the scraper synthesises up=0 for a "
        "configured-but-unreachable target, which is why that ConfigPatch is a "
        "pre-merge gate.)"
    )


# ---------------------------------------------------------------------------
# What makes these rules CORRECT rather than merely present.
#
# Everything above would pass on six well-formed rules measuring the wrong
# thing. The assertions below are the ones that encode why this layer exists.
# ---------------------------------------------------------------------------

# etcd's own server metrics. The four families are all this layer's rules may
# use: `etcd_server_*` (leader, leader changes, backend quota), `etcd_disk_*`
# (WAL fsync, backend commit), `etcd_mvcc_*` (DB size) and `etcd_network_*`
# (peer round-trip).
_ETCD_SERVER_METRIC = re.compile(r"^etcd_(server|disk|mvcc|network)_")

# The apiserver's storage CLIENT metrics — the trap this whole layer exists to
# name. These series were in VMSingle the entire 148 days etcd went unscraped,
# which is exactly why nobody noticed: greping `etcd` in VMUI returns them, and
# they look like etcd monitoring.
_APISERVER_CLIENT_METRIC = re.compile(r"^etcd_(request|requests|lease|bookmark)")

_ETCD_METRIC_TOKEN = re.compile(r"\betcd_[a-z0-9_]+\b")

# The `up{job="..."}` form the member-down rule and the absent watchdog use.
# Extracted rather than matched loosely so a rule that selects a DIFFERENT job
# cannot pass by containing the substring `up{job=`.
_UP_JOB = re.compile(r'\bup\s*\{\s*job\s*=\s*"([^"]+)"')


def _rule_expr(rule: dict[str, Any]) -> str:
    """The PromQL on the rule's refId=A node. Only `A` carries a query."""
    for node in rule.get("data") or []:
        model = node.get("model") or {}
        if node.get("refId") == "A" and "expr" in model:
            return str(model["expr"])
    raise AssertionError(
        f"rule {rule.get('uid')!r} has no refId=A datasource query to read"
    )


def test_etcd_rules_measure_etcd_itself_not_the_apiserver_storage_client():
    """THE assertion. Everything else in this file supports it.

    `etcd_request_duration_seconds`, `etcd_request_errors_total`,
    `etcd_requests_total`, `etcd_lease_object_counts` and
    `etcd_bookmark_counts` already exist in VMSingle and always did. They are
    the **apiserver's client** to etcd — they measure the caller, from inside
    the caller's process, and they are entirely available when etcd is not
    scraped at all. They tell you the apiserver's storage calls are slow; they
    cannot tell you whether the quorum has a leader, how often it re-elected
    one, how long a WAL fsync takes, or how close the backend is to its quota.

    That distinction is the whole reason this went unnoticed for 148 days: a
    reasonable person greps `etcd` in VMUI, finds series, and concludes etcd is
    monitored.

    So the failure mode this guards is not a typo — it is a plausible future
    repair. When one of these rules breaks (a chart bump, a metric rename, a
    scrape that stops), the fastest-looking fix is to repoint it at a metric
    that demonstrably HAS data. Every such metric here is an apiserver-client
    metric. The rule would go green, the dashboard would fill in, and Frank
    would be measuring the wrong process while believing it had fixed the
    monitoring gap this layer was built to close.
    """
    offenders: dict[str, list[str]] = {}
    for uid, rule in _etcd_rules().items():
        expr = _rule_expr(rule)
        metrics = sorted(set(_ETCD_METRIC_TOKEN.findall(expr)))

        client_metrics = [m for m in metrics if _APISERVER_CLIENT_METRIC.match(m)]
        if client_metrics:
            offenders[uid] = [f"apiserver storage-client metric: {m}" for m in client_metrics]
            continue

        stray = [m for m in metrics if not _ETCD_SERVER_METRIC.match(m)]
        if stray:
            offenders[uid] = [f"metric outside the etcd server families: {m}" for m in stray]
            continue

        # A rule with no `etcd_*` metric at all is legitimate only if it is one
        # of the `up{job="kube-etcd"}` forms — target liveness and the absent
        # watchdog both ask about the SCRAPE, not about a series etcd exports.
        if not metrics and not _UP_JOB.search(expr):
            offenders[uid] = [
                "queries neither an etcd server metric nor "
                f'up{{job="{ETCD_JOB}"}}: {expr!r}'
            ]

    assert not offenders, (
        "etcd alert rule(s) do not measure etcd.\n"
        f"  allowed: metrics matching {_ETCD_SERVER_METRIC.pattern}, or the "
        f'up{{job="{ETCD_JOB}"}} / absent(...) forms\n'
        f"  FORBIDDEN: etcd_request_* / etcd_requests_* / etcd_lease_* / "
        "etcd_bookmark_* — these are the APISERVER'S STORAGE CLIENT, not "
        "etcd. They existed in VMSingle throughout the 148 days etcd was "
        "unmonitored, and mistaking them for etcd metrics is the exact reason "
        "nobody noticed. A rule repointed at one of them goes green and "
        "measures the wrong process.\n"
        f"  offenders: {offenders}"
    )


def test_only_quorum_loss_pages():
    """Routing is by label, and the labels are the entire routing decision.

    `notification-policy-cm.yaml` puts the `health_bridge_only="true"` route
    BEFORE the severity routes with `continue: false`, so that label is a hard
    diversion: a rule carrying it can never reach Telegram whatever its
    severity. That is deliberate — health-bridge's dead-to-bug-issue lifecycle
    requires `severity: critical`, and the escape hatch is what lets a critical
    alert file a tracked bug without paging.

    The consequence is that a stray `health_bridge_only` on a paging rule
    silently un-pages it, with no error and no visible difference in Grafana.
    Losing quorum on Frank's control plane would then file an issue nobody
    reads at 03:00.

    `for:` is the other half. A planned Talos rolling reboot takes one member
    down and elects a new leader legitimately; the 2026-08-02 control-plane
    roll produced 48 alerts against a completely healthy cluster and took about
    7 minutes. A paging etcd rule below 10m would fire on every planned roll,
    and an alert that fires on planned maintenance gets muted within a month —
    which is worse than no alert, because it still looks like coverage.
    """
    faults: dict[str, list[str]] = {}
    rules = _etcd_rules()

    for uid in sorted(ETCD_PAGING_UIDS):
        rule = rules[uid]
        labels = rule.get("labels") or {}
        problems: list[str] = []
        if labels.get("severity") != "critical":
            problems.append(f"severity is {labels.get('severity')!r}, expected 'critical'")
        if "health_bridge_only" in labels:
            problems.append(
                "carries health_bridge_only="
                f"{labels['health_bridge_only']!r} — the policy's escape-hatch "
                "route precedes the severity routes with continue: false, so "
                "this rule can never reach Telegram"
            )
        window = _for_minutes(rule.get("for"))
        if window < PAGING_MIN_FOR_MINUTES:
            problems.append(
                f"for: {rule.get('for')!r} is under {PAGING_MIN_FOR_MINUTES}m, "
                "so a planned control-plane roll pages"
            )
        if problems:
            faults[uid] = problems

    for uid in sorted(ETCD_BRIDGE_ONLY_UIDS):
        labels = rules[uid].get("labels") or {}
        if labels.get("health_bridge_only") != "true":
            faults[uid] = [
                "missing health_bridge_only=\"true\" — it would reach Telegram "
                f"via the severity route. Got labels: {dict(labels)}"
            ]

    assert not faults, (
        "etcd alert routing is wrong. Only quorum loss pages: "
        f"{sorted(ETCD_PAGING_UIDS)} carry severity: critical, "
        f"for: >= {PAGING_MIN_FOR_MINUTES}m and NO health_bridge_only; "
        f"{sorted(ETCD_BRIDGE_ONLY_UIDS)} carry health_bridge_only=\"true\". "
        f"Faults: {faults}"
    )


def test_no_etcd_annotation_contains_html_metacharacters():
    """`<`, `>` and `&` make the alert fire and never deliver.

    Grafana's Telegram contact point sends `parse_mode: HTML`. A bare angle
    bracket in a summary is parsed as an unclosed tag, Telegram rejects the
    whole message with 400, and the failure appears only as an
    `ngalert.notifier` line in the Grafana log. The alert is firing in the UI,
    the contact point is configured, and nothing arrives — which is
    indistinguishable from the alert not having fired.

    It bit `layer-1-nic-link-flap` on 2026-06-08 (`<node-ip>` in a runbook),
    which is why every rule near these writes `NODE_IP`.

    Asserted across ALL annotations rather than just `summary`: Grafana
    templates every annotation into the notification body, so a runbook is as
    fatal as a summary.
    """
    offenders: dict[str, dict[str, str]] = {}
    for uid, rule in _etcd_rules().items():
        bad = {
            key: value
            for key, value in (rule.get("annotations") or {}).items()
            if any(char in str(value) for char in "<>&")
        }
        if bad:
            offenders[uid] = bad
    assert not offenders, (
        "etcd alert annotation(s) contain `<`, `>` or `&`. Grafana's Telegram "
        "contact point uses HTML parse_mode, so Telegram rejects the message "
        "with 400 and the alert fires but is NEVER DELIVERED — visible only in "
        "the Grafana log. Write NODE_IP, not a bracketed placeholder, and "
        f"spell comparisons out in words: {offenders}"
    )


# ---------------------------------------------------------------------------
# The watchdog must watch the job the scrape actually declares.
#
# `absent(up{job="kube-etcd"})` is the guard against this layer silently
# reverting, and it is itself silently breakable, in a way that looks the same
# from either direction. A watchdog naming a job that never exists returns
# `absent() == 1` forever. It fires immediately and permanently against a
# perfectly healthy scrape, which reads as a broken rule and gets muted. A
# watchdog naming a job that stopped existing after a rename returns exactly the
# same thing, and gets muted for the same reason, at the moment it is right.
#
# So the job name is DERIVED, not compared with a constant. It used to come from
# the rendered chart in two hops (VMServiceScrape.spec.jobLabel naming a Service
# label). Now there is one place it is set: the VMStaticScrape's `jobName`.
# ---------------------------------------------------------------------------


def _declared_job_name() -> str:
    job = (_etcd_static_scrape().get("spec") or {}).get("jobName")
    assert job and str(job).strip(), (
        "the etcd VMStaticScrape declares no spec.jobName, so there is no job "
        "name for the rules to agree with"
    )
    return str(job)


def test_absent_watchdog_selects_the_job_the_scrape_declares():
    """The watchdog's `job` is the scrape's `jobName`, not a remembered string.

    Checked for every `up{job="..."}` selector in the six rules, not only the
    watchdog. `layer-2-etcd-member-down` fails the same way and even more
    quietly. A wrong job there yields no series at all, which under
    `noDataState: OK` reads as a healthy quorum forever.
    """
    expected = _declared_job_name()

    selectors: dict[str, list[str]] = {}
    for uid, rule in _etcd_rules().items():
        jobs = _UP_JOB.findall(_rule_expr(rule))
        if jobs:
            selectors[uid] = jobs

    assert ETCD_ABSENT_WATCHDOG in selectors, (
        f"{ETCD_ABSENT_WATCHDOG} does not select on an `up{{job=...}}` series. "
        "absent() is the only expression that fires when a series DISAPPEARS, "
        "and `up` is the only series guaranteed to exist for as long as the "
        "target does."
    )

    wrong = {
        uid: jobs
        for uid, jobs in selectors.items()
        if any(job != expected for job in jobs)
    }
    assert not wrong, (
        "etcd alert rule(s) select a job the scrape does not declare.\n"
        f"  {ETCD_STATIC_SCRAPE.relative_to(REPO)} jobName: {expected!r}\n"
        f"  rules select: {wrong}\n"
        "A selector naming a job that does not exist yields no series: for the "
        "watchdog that means `absent() == 1` permanently, and for every other "
        "rule it means NoData, which noDataState: OK reads as health."
    )


# ---------------------------------------------------------------------------
# The dashboard: a curated ConfigMap, provisioned AND mounted.
#
# A scrape with rules but no dashboard has nowhere for the acceptance re-run's
# before/under-load numbers to live. And Frank already has an UPSTREAM etcd
# dashboard — victoria-metrics-k8s-stack rendered one (title "etcd", a
# chart-generated uid) for as long as kubeEtcd.enabled was true, and it has no
# toggle of its own. kubeEtcd.enabled is now false (the scrape moved to a
# VMStaticScrape), so the chart no longer renders it, but under prune: false a
# live orphan may remain until manual op obs-etcd-chart-orphans-delete runs.
# So this guard does not assert the curated board is the ONLY etcd dashboard,
# since the cluster may still hold that orphan. It asserts it exists,
# is mounted (both halves — see below), and measures the right metrics; the
# distinct-identity requirement against the upstream board is enforced by
# reading the curated title/uid directly, not by comparison to a render.
#
# The mount assertion is the one that would otherwise be forgotten. A
# dashboard ConfigMap that exists but is not mounted into
# grafana.extraConfigmapMounts syncs green in ArgoCD (the ConfigMap applies
# fine) and renders nowhere — every provisioned dashboard on Frank needs BOTH
# a provider-yaml mount and a dashboard-json mount, which is a two-place edit
# that looks like one.
# ---------------------------------------------------------------------------

ETCD_DASHBOARD_CM = (
    REPO / "apps" / "grafana-alerting" / "manifests" / "etcd-dashboard-cm.yaml"
)

ETCD_DASHBOARD_PROVIDER_KEY = "etcd-dashboard-provider.yaml"
ETCD_DASHBOARD_JSON_KEY = "etcd-dashboard.json"

EXPECTED_ETCD_DASHBOARD_PANEL_COUNT = 5


def _etcd_dashboard_configmap() -> dict[str, Any]:
    assert ETCD_DASHBOARD_CM.exists(), (
        f"{ETCD_DASHBOARD_CM.relative_to(REPO)} does not exist — the curated "
        "etcd dashboard is where the acceptance re-run's before/under-load "
        "evidence is supposed to live. Without it the promoted acceptance row "
        "has no durable home beyond a paragraph of prose."
    )
    return yaml.safe_load(ETCD_DASHBOARD_CM.read_text(encoding="utf-8"))


def _etcd_dashboard_data() -> dict[str, str]:
    configmap = _etcd_dashboard_configmap()
    assert configmap.get("kind") == "ConfigMap", (
        f"{ETCD_DASHBOARD_CM.relative_to(REPO)} is expected to be a ConfigMap "
        "carrying a Grafana dashboard provider yaml and a dashboard json — the "
        "same shape as every other curated board on Frank."
    )
    data = configmap.get("data") or {}
    missing = [
        key
        for key in (ETCD_DASHBOARD_PROVIDER_KEY, ETCD_DASHBOARD_JSON_KEY)
        if key not in data
    ]
    assert not missing, (
        f"{ETCD_DASHBOARD_CM.relative_to(REPO)} is missing data key(s) "
        f"{missing} — a provisioned dashboard needs both a provider yaml (tells "
        "Grafana where to look) and a dashboard json (what to render). Keys "
        f"present: {sorted(data)}"
    )
    return data


def _etcd_dashboard_json() -> dict[str, Any]:
    data = _etcd_dashboard_data()
    return yaml.safe_load(data[ETCD_DASHBOARD_JSON_KEY])


def test_etcd_dashboard_is_provisioned_and_mounted():
    """The curated etcd board exists, is mounted twice, and measures etcd.

    Modelled on `secure-agent-pod-dashboard-cm.yaml` (the smallest existing
    board): a ConfigMap carrying a provider yaml (`type: file`, a folder, a
    path under /var/lib/grafana/dashboards/<folder>) and a dashboard json with
    a `uid`. The five panels are the ones the spec names as the acceptance
    row's evidence: etcd_server_has_leader per node, leader changes/1h, WAL
    fsync p99, DB size vs quota, peer round-trip p99.

    The negative metric assertion mirrors
    `test_etcd_rules_measure_etcd_itself_not_the_apiserver_storage_client`: a
    panel repointed at an `etcd_request_*` metric would render data (that
    series has existed the whole 148 blind days) and look like a fixed
    dashboard while measuring the apiserver's storage client instead of etcd.
    """
    dashboard = _etcd_dashboard_json()

    uid = dashboard.get("uid")
    title = dashboard.get("title")
    assert uid and str(uid).strip(), (
        f"{ETCD_DASHBOARD_CM.relative_to(REPO)} dashboard json has no `uid`"
    )
    assert title and str(title).strip(), (
        f"{ETCD_DASHBOARD_CM.relative_to(REPO)} dashboard json has no `title`"
    )
    # Frank used to carry an upstream etcd dashboard (chart-rendered, title
    # "etcd", a chart-generated uid) for as long as kubeEtcd.enabled was true.
    # It was retired with the VMStaticScrape move and deleted on 2026-09-14, but
    # a stray orphan could still reappear under prune: false. A near-collision
    # here is exactly how a future reader concludes the curated board is the
    # redundant copy and deletes the wrong one.
    assert str(title).strip().lower() != "etcd", (
        f"dashboard title {title!r} collides with the upstream chart-rendered "
        "etcd board's title (\"etcd\") — give the curated board an "
        "unmistakably Frank-specific title so the two are never confused."
    )

    panels = dashboard.get("panels") or []
    assert len(panels) == EXPECTED_ETCD_DASHBOARD_PANEL_COUNT, (
        f"expected exactly {EXPECTED_ETCD_DASHBOARD_PANEL_COUNT} panels (per "
        f"the spec's Half 2c), found {len(panels)}"
    )

    untitled = [i for i, panel in enumerate(panels) if not str(panel.get("title") or "").strip()]
    assert not untitled, (
        f"panel(s) at index {untitled} have no non-empty title — an untitled "
        "panel in the acceptance-evidence dashboard is useless to whoever "
        "reads it during the re-run"
    )

    offenders: dict[str, list[str]] = {}
    for panel in panels:
        panel_title = str(panel.get("title") or f"panel {panel.get('id')}")
        for target in panel.get("targets") or []:
            expr = str(target.get("expr") or "")
            if not expr.strip():
                continue
            metrics = sorted(set(_ETCD_METRIC_TOKEN.findall(expr)))
            client_metrics = [m for m in metrics if _APISERVER_CLIENT_METRIC.match(m)]
            if client_metrics:
                offenders[panel_title] = [
                    f"apiserver storage-client metric: {m}" for m in client_metrics
                ]
                continue
            stray = [m for m in metrics if not _ETCD_SERVER_METRIC.match(m)]
            if stray:
                offenders[panel_title] = [
                    f"metric outside the etcd server families: {m}" for m in stray
                ]
    assert not offenders, (
        "etcd dashboard panel(s) do not measure etcd.\n"
        f"  allowed: metrics matching {_ETCD_SERVER_METRIC.pattern}\n"
        "  FORBIDDEN: etcd_request_* / etcd_requests_* / etcd_lease_* / "
        "etcd_bookmark_* — the apiserver's storage client, present in "
        "VMSingle throughout the 148 days etcd itself was unmonitored. A panel "
        "repointed at one of them renders data and looks fixed while measuring "
        f"the wrong process.\n  offenders: {offenders}"
    )

    # The mount: BOTH the provider mount and the json mount must exist, or
    # the ConfigMap syncs green in ArgoCD and renders nowhere.
    configmap_name = (_etcd_dashboard_configmap().get("metadata") or {}).get("name")
    assert configmap_name, (
        f"{ETCD_DASHBOARD_CM.relative_to(REPO)} has no metadata.name"
    )

    values = _vm_values()
    mounts = ((values.get("grafana") or {}).get("extraConfigmapMounts")) or []
    matching = [
        mount
        for mount in mounts
        if isinstance(mount, dict) and mount.get("configMap") == configmap_name
    ]
    subpaths = sorted(str(m.get("subPath")) for m in matching)
    assert subpaths == sorted([ETCD_DASHBOARD_PROVIDER_KEY, ETCD_DASHBOARD_JSON_KEY]), (
        f"{VM_VALUES.relative_to(REPO)} grafana.extraConfigmapMounts must carry "
        f"exactly two mounts referencing configMap: {configmap_name} — one for "
        f"{ETCD_DASHBOARD_PROVIDER_KEY} (provider) and one for "
        f"{ETCD_DASHBOARD_JSON_KEY} (dashboard json). Every other dashboard on "
        "Frank needs this two-place edit; a ConfigMap that exists but is not "
        "mounted syncs green in ArgoCD and renders nowhere. Found subPaths: "
        f"{subpaths}"
    )


# ---------------------------------------------------------------------------
# The manual operation exists in two places, and has to, so it must agree.
#
# `/sync-runbook` scans ONLY `docs/superpowers/plans/`. A `# manual-operation`
# block written only in `patches/phase08-obs/README.md` — where an operator
# about to apply the patch would actually look for it — would therefore never
# reach `docs/runbooks/manual-operations.yaml`, silently: the sync reports
# nothing missing, because it never saw it.
#
# So the block is deliberately duplicated: the plan copy is what the runbook is
# generated from, the README copy is what a human reads next to the patch. That
# duplication is a drift risk of exactly the kind this file exists to catch, and
# it drifts in the worst direction — someone corrects the apply procedure in the
# README, the plan keeps the old one, and the NEXT `/sync-runbook` overwrites the
# central runbook with the stale version.
# ---------------------------------------------------------------------------

PATCH_README = REPO / "patches" / "phase08-obs" / "README.md"

PLAN_SLUG = "2026-08-03--obs--etcd-scrape-control-plane"
PLAN_PHASE_FILE = "05.yaml"

# The plan moves once its work lands: `docs/superpowers/plans/` while active,
# `docs/superpowers/implemented/plans/` afterwards. Hardcoding the active path
# would turn this guard RED on the archival commit — a failure with nothing
# wrong behind it, which is the fastest way to get a guard deleted.
_PLAN_ROOTS = (
    REPO / "docs" / "superpowers" / "plans",
    REPO / "docs" / "superpowers" / "implemented" / "plans",
    REPO / "docs" / "superpowers" / "archived-plans",
)


def _plan_phase_5() -> pathlib.Path:
    candidates = [root / PLAN_SLUG / PLAN_PHASE_FILE for root in _PLAN_ROOTS]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise AssertionError(
        f"could not find {PLAN_SLUG}/{PLAN_PHASE_FILE} under any of "
        f"{[str(p.relative_to(REPO)) for p in _PLAN_ROOTS]}. That phase file "
        "carries the `# manual-operation` block /sync-runbook reads, so it is "
        "not optional to this guard — if the plan moved somewhere new, add the "
        "root here rather than deleting the check."
    )

MANUAL_OP_ID = "obs-etcd-metrics-listener-apply"

# The fields `agents/rules/repo-manual-ops.md` requires of every block.
MANUAL_OP_REQUIRED_FIELDS = (
    "id",
    "layer",
    "app",
    "plan",
    "when",
    "why_manual",
    "commands",
    "verify",
    "status",
)

_MANUAL_OP_BLOCK = re.compile(r"```yaml\n(# manual-operation\n.*?)```", re.DOTALL)


def _manual_op_block_in(text: str, source: str) -> str:
    """The single `# manual-operation` fenced block in `text`, verbatim."""
    blocks = _MANUAL_OP_BLOCK.findall(text)
    assert len(blocks) == 1, (
        f"expected exactly one `# manual-operation` fenced block in {source}, "
        f"found {len(blocks)}. Two blocks in one place means one of them is a "
        "copy nobody will keep current."
    )
    return blocks[0]


def _readme_manual_op_block() -> str:
    return _manual_op_block_in(
        PATCH_README.read_text(encoding="utf-8"),
        f"{PATCH_README.relative_to(REPO)}",
    )


def _plan_manual_op_block() -> str:
    """The block as it survives the plan YAML's `text: |` round-trip.

    Read through `yaml.safe_load` rather than off the raw file, because the
    block is indented inside a step's literal scalar — reading it raw would
    compare the indentation rather than the content, and would pass or fail for
    reasons that have nothing to do with the operation.
    """
    plan_phase_5 = _plan_phase_5()
    document = yaml.safe_load(plan_phase_5.read_text(encoding="utf-8"))
    texts = [
        step.get("text") or ""
        for task in document.get("tasks") or []
        for step in task.get("steps") or []
    ]
    # Selected by the operation's id, not by "the only manual-operation block in
    # the phase". Phase 5 legitimately carries others. The post-merge
    # obs-etcd-chart-orphans-delete op lives in P5.T2.S1, and /sync-runbook
    # needs it in the plan too. A count-based selector would turn this guard
    # red for a correct plan, and a guard that fails on correct input gets
    # deleted.
    matching = [
        block
        for text in texts
        for block in _MANUAL_OP_BLOCK.findall(text)
        if (yaml.safe_load(block) or {}).get("id") == LISTENER_APPLY_OP_ID
    ]
    assert len(matching) == 1, (
        f"expected exactly one `# manual-operation` block with id "
        f"{LISTENER_APPLY_OP_ID} in {plan_phase_5.relative_to(REPO)}, found "
        f"{len(matching)}. `/sync-runbook` reads the plan, so the plan is where "
        "the runbook entry comes from, and two copies of the same id would sync "
        "whichever it meets last."
    )
    return matching[0]


LISTENER_APPLY_OP_ID = "obs-etcd-metrics-listener-apply"


def test_the_manual_operation_block_is_complete_and_says_what_it_asserts():
    """Required fields present, and `verify:` asserts an outcome.

    `omnictl apply` exiting 0 proves the ConfigPatch was ACCEPTED by Omni. It
    does not prove etcd restarted with it, that the listener opened, or that a
    single series arrived — and Omni is documented to wedge on a cold-boot clock
    jump while still serving cached reads, so "the apply succeeded" is exactly
    the reassurance that failure mode gives you. A verify section that checks
    the exit status of the thing it just ran is not a verification.
    """
    block = _readme_manual_op_block()
    entry = yaml.safe_load(block)

    missing = [field for field in MANUAL_OP_REQUIRED_FIELDS if field not in entry]
    assert not missing, (
        f"the `# manual-operation` block is missing required field(s) {missing} "
        "(see agents/rules/repo-manual-ops.md). `/sync-runbook` merges by `id`, "
        "so an incomplete block becomes an incomplete runbook entry."
    )
    assert entry["id"] == MANUAL_OP_ID, (
        f"expected id {MANUAL_OP_ID!r}, got {entry['id']!r} — the id is the "
        "runbook's merge key, so renaming it appends a second entry rather "
        "than updating the first."
    )

    verify = "\n".join(str(line) for line in entry.get("verify") or [])
    assert "2381" in verify, (
        "`verify:` never mentions the metrics listener port — it has to assert "
        "the listener actually responds on the three minis, not merely that "
        "omnictl exited 0"
    )
    assert 'job="kube-etcd"' in verify or "kube-etcd" in verify, (
        '`verify:` never asserts the scrape target came up (up{job="kube-etcd"} '
        "= 3 series at 1). A patch that applies cleanly and produces no series "
        "is precisely the state this layer exists to make visible."
    )


def test_the_two_copies_of_the_manual_operation_agree():
    """The README copy and the plan copy are the same operation.

    They cannot be collapsed into one: `/sync-runbook` reads only the plan, and
    an operator about to run `omnictl apply` reads the README. So the guard is
    that they never diverge — a correction made in one place and not the other
    means the central runbook is regenerated from the stale half, quietly.
    """
    readme_block = _readme_manual_op_block()
    plan_block = _plan_manual_op_block()

    assert readme_block == plan_block, (
        "the `# manual-operation` block has DRIFTED between its two homes:\n"
        f"  {PATCH_README.relative_to(REPO)}  (what an operator reads)\n"
        f"  {_plan_phase_5().relative_to(REPO)}  (what /sync-runbook reads)\n"
        "Both must carry the block verbatim. /sync-runbook scans only "
        "docs/superpowers/plans/, so the plan copy is the one that reaches "
        "docs/runbooks/manual-operations.yaml — meaning a fix applied only to "
        "the README is silently discarded on the next sync, and a fix applied "
        "only to the plan leaves the operator reading the old procedure at the "
        "moment they are restarting the quorum."
    )


MANUAL_OPS_RUNBOOK = REPO / "docs" / "runbooks" / "manual-operations.yaml"


def test_the_manual_operation_reached_the_central_runbook():
    """The two copies agreeing with each other is not the point — the SYNC is.

    The entire justification for duplicating this block into the plan phase file
    and guarding the duplication with a byte-equality test is "so /sync-runbook
    picks it up". On the first pass it was duplicated, guarded — and never
    synced: `obs-etcd-metrics-listener-apply` was absent from
    `docs/runbooks/manual-operations.yaml`, the single registry an operator
    actually consults, while two copies of it sat in this branch agreeing
    perfectly with each other.

    That is the same shape as the empty `Endpoints` object this whole layer
    exists to name: every artefact present and internally consistent, and the
    one thing that had to happen never happened, with nothing reporting it.

    Asserted on the FIELDS, not merely on the id. `/sync-runbook` refreshes
    every field except `status` (human-set), so a runbook entry whose `when:` or
    `verify:` disagrees with the plan means the block was edited and never
    re-synced — and the operator is then reading a stale procedure from the
    place they were told was authoritative. If this fails, run `/sync-runbook`.
    """
    assert MANUAL_OPS_RUNBOOK.exists(), (
        f"{MANUAL_OPS_RUNBOOK.relative_to(REPO)} is missing — it is the central "
        "registry every manual operation on Frank is supposed to reach"
    )
    runbook = yaml.safe_load(MANUAL_OPS_RUNBOOK.read_text(encoding="utf-8"))
    operations = runbook.get("operations") or []
    matches = [op for op in operations if op.get("id") == MANUAL_OP_ID]

    assert matches, (
        f"{MANUAL_OP_ID!r} is not in "
        f"{MANUAL_OPS_RUNBOOK.relative_to(REPO)}. The block exists in "
        f"{PATCH_README.relative_to(REPO)} and in "
        f"{_plan_phase_5().relative_to(REPO)}, and those two agree — but the "
        "sync that is the whole reason for the duplication never ran. Run "
        "`/sync-runbook`. Two copies that agree with each other and not with "
        "the registry they feed is the empty-Endpoints failure in documentation "
        f"form. Runbook currently holds {len(operations)} operations."
    )
    assert len(matches) == 1, (
        f"{MANUAL_OP_ID!r} appears {len(matches)} times in the runbook; `id` is "
        "the merge key, so a duplicate means one of them is unreachable"
    )

    entry = matches[0]
    plan_entry = yaml.safe_load(_plan_manual_op_block())
    drifted = {
        field: {"runbook": entry.get(field), "plan": value}
        for field, value in plan_entry.items()
        # `status` is deliberately human-owned: /sync-runbook never overwrites
        # it, so the plan can say `pending` while the runbook records `done`.
        if field != "status" and entry.get(field) != value
    }
    assert not drifted, (
        f"{MANUAL_OPS_RUNBOOK.relative_to(REPO)} is out of date with the plan "
        f"block for {MANUAL_OP_ID!r} — run `/sync-runbook`. The registry is "
        "what an operator reads when they are not reading the plan, so a stale "
        f"entry there is a stale procedure at the moment it matters: {drifted}"
    )


# ---------------------------------------------------------------------------
# The ordering claim is load-bearing, was WRONG, and must not silently revert.
#
# Every ordering statement in this branch originally said the ConfigPatch could
# be applied before or after the merge, on the reasoning that "the target is
# simply down and the rules sit at NoData with noDataState: OK — nothing fires".
# That is false. `up` is not a series etcd exports: the SCRAPER synthesises one
# per configured target, every interval, `1` on success and `0` on failure. It is
# never absent while the target is configured — and declaring the scrape's targets
# (the VMStaticScrape) is exactly what configures three of them.
#
# So merging first does not produce a quiet NoData window. It produces three
# `up=0` targets, `layer-2-etcd-member-down` firing at `for: 10m`, and Telegram
# paged every 3 minutes (the notification policy's root repeat_interval) against
# a perfectly healthy quorum, until an operator applies a patch the plan had
# deferred. Frank already contains a live instance of the shape: `kube-scheduler`
# has three POPULATED Endpoints and a scrape that fails on TLS/auth against
# 10259, and `max_over_time(up{job="kube-scheduler"}[90d])` is 0 — not NoData —
# on all three.
#
# This guard exists because the defect WAS a documentation claim. Nothing in the
# manifests was wrong; seven prose statements were, and they were what the
# implementation trusted. So the tripwire is on the prose, deliberately, and it
# is anchored to the manifest fact that makes the prose necessary.
# ---------------------------------------------------------------------------

DESIGN_SPEC = (
    REPO
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-03--obs--etcd-scrape-control-plane-design.md"
)

_SPEC_ROOTS = (
    REPO / "docs" / "superpowers" / "specs",
    REPO / "docs" / "superpowers" / "implemented" / "specs",
)

PLAN_PROSE_FILE = "_prose.md"

# The affirmative claim that was wrong. Case-sensitive on the capitalised form
# so the corrected documents can still QUOTE the old sentence in lower case
# while explaining why it was false — which every one of them now does.
_REVERTED_ORDERING_CLAIMS = (
    "Ordering is safe in either direction",
    "Ordering is safe either way",
)

# What a document that gets this right must contain: the conclusion (a pre-merge
# gate) and the MECHANISM (up is synthesised by the scraper). Requiring both is
# what stops the correction decaying into an unexplained assertion that the next
# reader has no way to evaluate and therefore no reason to keep.
_PRE_MERGE = re.compile(r"pre-?merge", re.IGNORECASE)
_SYNTHESISED = re.compile(r"synthesis", re.IGNORECASE)


def _spec_path() -> pathlib.Path:
    for root in _SPEC_ROOTS:
        candidate = root / DESIGN_SPEC.name
        if candidate.exists():
            return candidate
    raise AssertionError(
        f"could not find {DESIGN_SPEC.name} under "
        f"{[str(p.relative_to(REPO)) for p in _SPEC_ROOTS]} — the design spec is "
        "the ordering authority; if it moved, add the root here rather than "
        "deleting the check"
    )


def _plan_prose() -> pathlib.Path:
    for root in _PLAN_ROOTS:
        candidate = root / PLAN_SLUG / PLAN_PROSE_FILE
        if candidate.exists():
            return candidate
    raise AssertionError(
        f"could not find {PLAN_SLUG}/{PLAN_PROSE_FILE} under "
        f"{[str(p.relative_to(REPO)) for p in _PLAN_ROOTS]}"
    )


def _paging_rules_built_on_up() -> dict[str, str]:
    """Paging rules whose query is `up{job=...}` — not `absent(up{...})`.

    These are the rules that make the ordering load-bearing: only a rule that
    reads the SYNTHESISED `up` value (rather than its presence) can fire while
    the listener is closed, and only a rule with no `health_bridge_only` label
    can reach Telegram when it does.
    """
    found: dict[str, str] = {}
    for uid, rule in _etcd_rules().items():
        if uid not in ETCD_PAGING_UIDS:
            continue
        expr = _rule_expr(rule)
        if "absent" in expr:
            continue
        if _UP_JOB.search(expr):
            found[uid] = expr
    return found


def test_the_ordering_claim_is_not_reverted():
    """The docs must say pre-merge gate, and say WHY, for as long as a paging
    rule reads `up{job=...}` directly.

    Anchored to the manifests rather than free-floating: the requirement on the
    prose is derived from the existence of a rule that pages on a synthesised
    `up=0`. If a future redesign removes that rule, this guard's premise is gone
    and it says so loudly rather than passing vacuously — a test that keeps
    going green after the thing it guards has been deleted is how a tripwire
    becomes decoration.
    """
    paging_on_up = _paging_rules_built_on_up()
    assert paging_on_up, (
        "no paging etcd rule queries `up{job=...}` any more, so the premise of "
        "this guard — that merging the values block before the ConfigPatch is "
        "applied pages Telegram — no longer holds.\n"
        f"  paging uids: {sorted(ETCD_PAGING_UIDS)}\n"
        "If that is a deliberate redesign, the ordering documentation (which "
        "currently declares a PRE-MERGE GATE in the design spec, the patches "
        "README, the ConfigPatch header and the plan) has to be revisited in "
        "the same change, and this test deleted with it. If it is not "
        "deliberate, a rule has been repointed away from target liveness and "
        "the member-down signal is gone."
    )

    documents = {
        _spec_path(): "the design authority",
        PATCH_README: "what an operator reads next to the patch",
        CONFIGPATCH: "the file being applied",
        _plan_prose(): "the plan's narrative",
        _plan_phase_5(): "the phase the operator executes",
    }

    faults: dict[str, list[str]] = {}
    for path, role in documents.items():
        text = path.read_text(encoding="utf-8")
        problems: list[str] = []

        reverted = [claim for claim in _REVERTED_ORDERING_CLAIMS if claim in text]
        if reverted:
            problems.append(
                f"carries the reverted claim(s) {reverted} — `up` is "
                "synthesised per configured target and reads 0, not absent, on "
                "a failed scrape, so the order is NOT free"
            )
        if not _PRE_MERGE.search(text):
            problems.append(
                "never says the ConfigPatch is a pre-merge gate"
            )
        if not _SYNTHESISED.search(text):
            problems.append(
                "states the ordering without the mechanism (that the scraper "
                "SYNTHESISES `up` for every configured target) — an "
                "unexplained ordering constraint is one a future reader has no "
                "way to evaluate, and this constraint has already been "
                "reasoned away once"
            )
        if problems:
            faults[f"{path.relative_to(REPO)} ({role})"] = problems

    assert not faults, (
        "the etcd ordering documentation has reverted or lost its reasoning.\n"
        "  The rule that makes ordering load-bearing: "
        f"{sorted(paging_on_up)}\n"
        "  `up` is NOT exported by etcd. vmagent synthesises one series per "
        "CONFIGURED target every interval — 1 on a successful scrape, 0 on a "
        "failed one — and never omits it while the target is configured. "
        "Declaring the scrape's targets is what creates them, so merging "
        "before the listener is open gives three targets at up=0 (not NoData), "
        "layer-2-etcd-member-down fires at for: 10m, and the notification "
        "policy's root repeat_interval: 3m pages Telegram every 3 minutes "
        "against a healthy quorum.\n"
        "  Live instance on Frank, 2026-08-03: count(up==0) by (job) returns "
        "{job=\"kube-scheduler\"} 3, and max_over_time(up{job=\"kube-scheduler\"}"
        "[90d]) is 0 on all three — populated Endpoints, failing scrape, up=0.\n"
        f"  faults: {faults}"
    )
