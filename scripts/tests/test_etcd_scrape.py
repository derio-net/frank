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
* `apps/victoria-metrics/values.yaml` points a **static** `Endpoints` object at
  the three control-plane minis on that port. Applied by ArgoCD.

Nothing else in the repo connects them. A port typo in either file, or a node
IP that moves, reproduces exactly the silent-empty-target failure being fixed —
which is why the cross-file assertions here are written as *derivations* (parse
the port out of the ConfigPatch URL, parse the IPs out of the repo's own
machine table) rather than as a third hardcoded copy of the same values.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
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
        "kubeEtcd.endpoints needs revisiting, not this regex."
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
# The GitOps half: chart values pointing a STATIC Endpoints object at the three
# control-plane minis.
#
# The negative assertions below matter more than the positive ones. The chart's
# DEFAULT `vmScrape` uses `scheme: https` plus a ServiceAccount bearer token and
# is aimed at port 2379 — the kubeadm layout, where etcd's client port is what
# you scrape. Inheriting any part of that default against 2381 produces a target
# that fails forever while the configuration looks entirely plausible in a diff.
# ---------------------------------------------------------------------------

METRICS_PORT_NAME = "http-metrics"


def _vm_values() -> dict[str, Any]:
    return yaml.safe_load(VM_VALUES.read_text(encoding="utf-8"))


def _kube_etcd() -> dict[str, Any]:
    values = _vm_values()
    assert "kubeEtcd" in values, (
        f"{VM_VALUES.relative_to(REPO)} has no `kubeEtcd` block. The chart "
        "defaults it to enabled with a pod selector that can never match on "
        "Talos, which is how this scrape stayed inert and silent for 148 days "
        f"— leaving it unstated is the bug. Top-level keys: {sorted(values)}"
    )
    return values["kubeEtcd"]


def _kube_etcd_scrape_endpoints() -> list[dict[str, Any]]:
    kube_etcd = _kube_etcd()
    endpoints = (
        ((kube_etcd.get("vmScrape") or {}).get("spec") or {}).get("endpoints")
    )
    assert endpoints, (
        "kubeEtcd.vmScrape.spec.endpoints is missing or empty — without an "
        "explicit override the chart's default endpoint applies, which scrapes "
        "https with a ServiceAccount bearer token and can never succeed "
        "against etcd's plain-HTTP metrics listener"
    )
    return list(endpoints)


def test_kube_etcd_values_target_the_control_planes():
    """The scrape points at a static Endpoints object on the metrics port.

    Supplying `endpoints:` is what switches the chart from selector-based pod
    discovery to a static `Endpoints` object — the only shape that can address
    a host system service. Everything else here exists to stop the chart
    default leaking back in.
    """
    kube_etcd = _kube_etcd()

    assert kube_etcd.get("enabled") is True, (
        "kubeEtcd.enabled must be explicitly True. It is the chart default, "
        "but stating it is what makes this block's intent legible next to the "
        f"kubeControllerManager disable above it. Got: {kube_etcd.get('enabled')!r}"
    )

    service = kube_etcd.get("service") or {}
    assert service.get("port") == 2381 and service.get("targetPort") == 2381, (
        "kubeEtcd.service.port and .targetPort must both be 2381, etcd's "
        "dedicated metrics listener. The chart default is 2379, the mutual-TLS "
        f"client port. Got port={service.get('port')!r}, "
        f"targetPort={service.get('targetPort')!r}"
    )

    assert kube_etcd.get("endpoints") == CONTROL_PLANE_IPS, (
        "kubeEtcd.endpoints must list the three control-plane minis in order. "
        "Omitting it leaves the chart on pod-selector discovery, which matches "
        "nothing on Talos and yields the empty Endpoints object this whole "
        f"change exists to fix. Got: {kube_etcd.get('endpoints')!r}"
    )

    endpoints = _kube_etcd_scrape_endpoints()
    assert len(endpoints) == 1, (
        "expected exactly one kubeEtcd.vmScrape.spec.endpoints entry; the "
        f"override REPLACES the chart default wholesale. Got {len(endpoints)}"
    )
    endpoint = endpoints[0]

    assert endpoint.get("scheme") == "http", (
        "the etcd scrape endpoint must use `scheme: http`. The metrics "
        "listener is plain HTTP by design; the chart's default `https` "
        f"produces a target that fails forever. Got: {endpoint.get('scheme')!r}"
    )
    assert endpoint.get("port") == METRICS_PORT_NAME, (
        f"the etcd scrape endpoint must name port `{METRICS_PORT_NAME}` — the "
        "port name the chart gives the Service it renders. Got: "
        f"{endpoint.get('port')!r}"
    )

    forbidden = sorted(
        key
        for key in ("bearerTokenFile", "bearerTokenSecret", "tlsConfig")
        if key in endpoint
    )
    assert not forbidden, (
        "the etcd scrape endpoint carries chart-default authentication: "
        f"{forbidden}. Port 2381 is unauthenticated plain HTTP — a bearer "
        "token or TLS config there is not merely redundant, it is the "
        "kubeadm-shaped default that makes the target fail while the values "
        "read as careful."
    )


# ---------------------------------------------------------------------------
# The two halves cannot drift apart.
#
# These are the whole reason this file exists. The ConfigPatch and the chart
# values live in different directories and are applied by different tools —
# `omnictl`, by hand, by an operator; and ArgoCD, from `main` — so no deploy,
# no sync status and no review of either file alone can notice that they no
# longer agree. A port typo in either, or a node IP that moves, reproduces
# precisely the silent empty-target failure this layer was written to fix:
# configuration that looks complete, produces no error, and yields no data.
#
# Both are written as DERIVATIONS. Restating the port or the addresses here
# would make this file a third copy that drifts alongside the other two, which
# is the opposite of a guard.
# ---------------------------------------------------------------------------


def test_listener_port_matches_the_scrape_target_port():
    """The port etcd listens on is the port the scrape dials.

    Parsed out of the ConfigPatch's URL rather than asserted as a literal, so
    the test cannot agree with a typo it also contains.
    """
    url = _listen_metrics_urls()
    listener_port = urlparse(url).port
    assert listener_port is not None, (
        f"could not parse a port out of `listen-metrics-urls: {url}` in "
        f"{CONFIGPATCH.relative_to(REPO)} — etcd needs an explicit port here, "
        "and this guard cannot compare what it cannot read"
    )

    target_port = (_kube_etcd().get("service") or {}).get("targetPort")

    assert listener_port == target_port, (
        "PORT MISMATCH between the two halves of the etcd scrape:\n"
        f"  {CONFIGPATCH.relative_to(REPO)} opens etcd's metrics listener on "
        f"port {listener_port} (listen-metrics-urls: {url})\n"
        f"  {VM_VALUES.relative_to(REPO)} dials kubeEtcd.service.targetPort = "
        f"{target_port!r}\n"
        "These files are applied by different tools and nothing else connects "
        "them, so a mismatch does not fail a deploy — it produces a scrape "
        "target that is down forever while both files look correct in "
        "isolation. That is the exact failure this layer exists to fix."
    )


def test_endpoints_match_the_documented_control_plane_ips():
    """The scrape targets the nodes the repo says are the control plane.

    Frank's node IPs are static, fixed by Talos machine config — so this is not
    guarding against drift in the addresses so much as against the chart values
    and the machine table disagreeing about which machines run etcd. A stale IP
    here scrapes nothing and reports nothing.
    """
    documented = CONTROL_PLANE_IPS
    configured = _kube_etcd().get("endpoints")

    assert configured == documented, (
        "ENDPOINT MISMATCH between the etcd scrape and the repo's machine "
        "table:\n"
        f"  {VM_VALUES.relative_to(REPO)} kubeEtcd.endpoints = {configured!r}\n"
        f"  {INFRA_RULE.relative_to(REPO)} control-plane rows = {documented!r}\n"
        "etcd runs on the control plane and nowhere else. An address that is "
        "in one list and not the other is either a node that is scraped but "
        "runs no etcd, or an etcd member that is not scraped at all — and "
        "neither shows up as an error, only as missing series."
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

# The job label the scrape produces. Written here only so failure messages can
# name it — NOTHING asserts against this constant. The rules are checked against
# the value DERIVED from the rendered chart in
# `test_absent_watchdog_selects_the_job_the_chart_renders`, because a constant
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

            b_model = nodes["B"].get("model") or {}
            if b_model.get("type") != "reduce":
                faults.append(f"node B type is {b_model.get('type')!r}, expected 'reduce'")
            if b_model.get("expression") != "A":
                faults.append(
                    f"node B reduces {b_model.get('expression')!r}, expected 'A'"
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

    Grafana defaults an omitted `noDataState` to `NoData`, which FIRES. Before
    the ConfigPatch lands the target is simply down, so every one of these rules
    sits at NoData — omitting the field would page on merge, for a cluster that
    is perfectly healthy.

    The cost is that a scrape which disappears LATER also reads OK, which is
    precisely why `layer-2-etcd-scrape-absent` exists. Stating both fields is
    what makes that trade-off visible in the file instead of implied by a
    default.
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
        "to NoData, which fires — and these rules are NoData by construction "
        "until the operator applies the Talos ConfigPatch."
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
# The watchdog must watch the name the chart actually renders.
#
# `absent(up{job="kube-etcd"})` is the guard against this layer silently
# reverting — and it is itself silently breakable, in a way that looks the same
# from either direction. A watchdog naming a job that never exists returns
# `absent() == 1` forever: it fires immediately, permanently, against a
# perfectly healthy scrape, which reads as a broken rule and gets muted. A
# watchdog naming a job that stopped existing after a rename returns exactly the
# same thing — and gets muted for the same reason, at the moment it is right.
# Either way the guard against silent absence is itself silently wrong, which is
# the defect class this whole plan exists to stop recurring, on its third
# appearance.
#
# So the job name is DERIVED from the rendered chart rather than compared with a
# constant. The constant and the rule would only ever be the same paste twice.
# The derivation is two hops, both of which a chart bump can move independently:
#
#   VMServiceScrape.spec.jobLabel  ->  names a Service LABEL KEY ("jobLabel")
#   Service.metadata.labels[key]   ->  the job VALUE ("kube-etcd")
#
# This shells out to `helm template` against the pinned chart, following
# test_cnc_staging_host_secrets.py, and is fail-closed: a missing helm or no
# egress goes RED on infrastructure rather than green on nothing. CI installs
# helm for exactly this reason (.github/workflows/repo-tripwires.yml).
# ---------------------------------------------------------------------------

VM_APPLICATION = REPO / "apps" / "root" / "templates" / "victoria-metrics.yaml"

# The rendered objects are named `<release>-<chart>-kube-etcd`; the release name
# must match production or the Service labels the scrape selects on differ.
VM_RELEASE = "victoria-metrics"

_render_cache: dict[str, dict[str, dict[str, Any]]] = {}


def _vm_chart_pin() -> tuple[str, str, str]:
    """(repoURL, chart, version) for the k8s-stack source, from the App CR.

    Read by regex, not YAML: the Application is a Helm template and carries
    `{{ .Values.repoURL }}` in its sibling sources, so `yaml.safe_load` cannot
    parse it. Deriving the pin means a chart bump re-runs this guard against
    whatever is actually deployed instead of against a stale literal.
    """
    text = VM_APPLICATION.read_text(encoding="utf-8")
    match = re.search(
        r"repoURL:\s*(?P<repo>\S+)\s*\n\s*chart:\s*(?P<chart>\S+)\s*\n\s*"
        r"targetRevision:\s*\"?(?P<version>[0-9][^\"\s]*)\"?",
        text,
    )
    assert match, (
        f"could not find the charted source pin in "
        f"{VM_APPLICATION.relative_to(REPO)} — this guard renders the chart at "
        "the version ArgoCD actually deploys, and cannot do that if the "
        "Application's shape has changed"
    )
    return match.group("repo"), match.group("chart"), match.group("version")


def _rendered_kube_etcd_objects() -> dict[str, dict[str, Any]]:
    """`{kind: object}` for the kube-etcd objects the chart renders.

    Rendered with the real `apps/victoria-metrics/values.yaml` and the
    production release name, so the labels here are the labels the cluster has.
    """
    if "objects" in _render_cache:
        return _render_cache["objects"]

    repo, chart, version = _vm_chart_pin()
    result = subprocess.run(
        [
            "helm", "template", VM_RELEASE, chart,
            "--repo", repo,
            "--version", version,
            "-f", str(VM_VALUES),
            # The operator subchart renders CRDs and a webhook we do not need
            # and which slow the render considerably.
            "--set", "victoria-metrics-operator.enabled=false",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"`helm template {chart} --version {version}` failed, so the job label "
        "could not be derived. This guard is fail-closed on purpose: a green "
        "run must mean the chart was rendered and agreed, never that rendering "
        f"was skipped.\n{result.stderr}"
    )

    objects: dict[str, dict[str, Any]] = {}
    for document in yaml.safe_load_all(result.stdout):
        if not document:
            continue
        name = (document.get("metadata") or {}).get("name") or ""
        if name.endswith("-kube-etcd"):
            objects[document["kind"]] = document

    for kind in ("Service", "VMServiceScrape"):
        assert kind in objects, (
            f"the chart rendered no kube-etcd {kind}. Either kubeEtcd went "
            "disabled in apps/victoria-metrics/values.yaml — in which case "
            "there is no scrape and these alert rules are decoration — or the "
            f"chart renamed its objects. Rendered kinds: {sorted(objects)}"
        )
    _render_cache["objects"] = objects
    return objects


def _rendered_job_label() -> str:
    """The job name series will actually carry, derived in two hops."""
    objects = _rendered_kube_etcd_objects()

    label_key = (objects["VMServiceScrape"].get("spec") or {}).get("jobLabel")
    assert label_key, (
        "the rendered VMServiceScrape has no `spec.jobLabel`, so vmagent would "
        "fall back to its own default job naming and every selector in these "
        "rules would be wrong in a way nothing else reports"
    )

    service_labels = (objects["Service"].get("metadata") or {}).get("labels") or {}
    assert label_key in service_labels, (
        f"the VMServiceScrape takes the job name from the Service label "
        f"{label_key!r}, but the rendered Service carries no such label. "
        f"Service labels: {sorted(service_labels)}"
    )
    return str(service_labels[label_key])


def test_absent_watchdog_selects_the_job_the_chart_renders():
    """The watchdog's `job` is the chart's, not a remembered string.

    Checked for every `up{job="..."}` selector in the six rules, not only the
    watchdog: `layer-2-etcd-member-down` fails the same way and even more
    quietly. A wrong job there yields no series at all, which under
    `noDataState: OK` reads as a healthy quorum forever — a rule that cannot
    fire, reporting health.
    """
    expected = _rendered_job_label()

    selectors: dict[str, list[str]] = {}
    for uid, rule in _etcd_rules().items():
        jobs = _UP_JOB.findall(_rule_expr(rule))
        if jobs:
            selectors[uid] = jobs

    assert ETCD_ABSENT_WATCHDOG in selectors, (
        f"{ETCD_ABSENT_WATCHDOG} does not select on an `up{{job=...}}` series. "
        "absent() is the only expression that fires when a series DISAPPEARS, "
        "and `up` is the only series guaranteed to exist for as long as the "
        "target does — so the watchdog against the scrape vanishing has to be "
        "built on it."
    )

    wrong = {
        uid: jobs
        for uid, jobs in selectors.items()
        if any(job != expected for job in jobs)
    }
    assert not wrong, (
        "etcd alert rule(s) select a job the chart does not render.\n"
        f"  chart renders: job={expected!r}\n"
        f"  rules select:  {wrong}\n"
        "The name arrives by two hops — the Service carries a `jobLabel` label, "
        "and the VMServiceScrape's `spec.jobLabel` says to take the job name "
        "from it — so a rename at either end moves it. A selector naming a job "
        "that does not exist yields no series, which for the watchdog means "
        "`absent() == 1` permanently (fires against a healthy scrape, then gets "
        "muted) and for every other rule means NoData, which noDataState: OK "
        "reads as health. Both are the guard being silently wrong, which is the "
        "exact defect this layer exists to stop recurring."
    )


# ---------------------------------------------------------------------------
# The dashboard: a curated ConfigMap, provisioned AND mounted.
#
# A scrape with rules but no dashboard has nowhere for the acceptance re-run's
# before/under-load numbers to live. And Frank already has an UPSTREAM etcd
# dashboard — victoria-metrics-k8s-stack renders one (title "etcd", a
# chart-generated uid) whether or not this plan exists, because it follows
# kubeEtcd.enabled, and Grafana's grafana-sc-dashboard sidecar has been serving
# it, empty, for the same 148 days. It cannot be disabled independently
# (defaultDashboards.dashboards has no etcd toggle; the only levers remove
# either all 15 default boards or the scrape itself). So this guard does not
# assert the curated board is the ONLY etcd dashboard — it asserts it exists,
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
    # Frank already has an upstream etcd dashboard (chart-rendered, title
    # "etcd", a chart-generated uid) that cannot be disabled independently —
    # see the module docstring above this section. A near-collision here is
    # exactly how a future reader concludes the curated board is the
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
