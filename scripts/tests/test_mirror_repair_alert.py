"""layer-25-mirror-repair-recurring: the per-repo signal the shared pipeline hides.

`derio-homelab-pull-sync` serves five repos, so one repo failing on it is
satisfied by another's success under `layer-25-pipeline-failing`'s
`unless success > 0` (frank#798/#850). mirror-reconcile logs one
`mirror-reconcile repaired <repo> ...` line per ref it had to repair; a repo
needing repair more than once in 6h is the per-repo failure signal.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ci_outcome_alert_repeat import _rules  # noqa: E402  shared rule loader

REPO = Path(__file__).resolve().parents[2]
RECONCILE = REPO / "apps/tekton/manifests/mirror-reconcile.yaml"
RULES_CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
UID = "layer-25-mirror-repair-recurring"


def _rule() -> dict:
    return _rules()[UID]


def _data(rule: dict, ref: str) -> dict:
    return next(d for d in rule["data"] if d["refId"] == ref)


def test_rule_lives_in_the_pipeline_outcomes_group() -> None:
    import yaml

    cm = yaml.safe_load(RULES_CM.read_text())
    groups = {}
    for blob in cm["data"].values():
        for grp in yaml.safe_load(blob).get("groups", []):
            groups[grp["name"]] = [r["uid"] for r in grp["rules"]]
    assert UID in groups["layer-25-pipeline-outcomes"]


def test_query_shape() -> None:
    rule = _rule()
    a = _data(rule, "A")
    assert a["datasourceUid"] == "affdoo4s9258gc"
    assert a["model"]["queryType"] == "stats"
    assert a["relativeTimeRange"]["from"] == 21600
    expr = a["model"]["expr"]
    for part in (
        '_msg:"mirror-reconcile repaired"',
        "kubernetes.namespace_name:tekton-pipelines",
        # p1a-r3: only mirror-reconcile Jobs run a container named push;
        # Tekton step containers are step-*, so PipelineRun code cannot spoof.
        "kubernetes.container_name:push",
        'extract "mirror-reconcile repaired <repo> "',
        "stats by (repo) count()",
    ):
        assert part in expr, part


def test_summary_renders_the_count_not_the_value_struct() -> None:
    summary = _rule()["annotations"]["summary"]
    assert "$values.B.Value" in summary, summary


def test_threshold_and_states() -> None:
    rule = _rule()
    cond = _data(rule, "C")["model"]["conditions"][0]["evaluator"]
    assert cond == {"type": "gt", "params": [1]}
    assert rule["noDataState"] == "OK"
    assert rule["execErrState"] == "Error"
    assert rule["labels"]["severity"] == "warning"
    assert rule["labels"]["ci_outcome"] == "true"
    assert len(UID) <= 40, "Grafana rejects a rule uid over 40 chars and crashes"


def test_runbook_is_namespace_agnostic() -> None:
    rb = _rule()["annotations"]["runbook"]
    assert "-n tekton-pipelines" not in rb
    assert "grep pull-sync" in rb


def test_extract_pattern_captures_the_repo_from_the_real_log_line() -> None:
    expr = _data(_rule(), "A")["model"]["expr"]
    pattern = re.search(r'extract "([^"]+)"', expr).group(1)
    regex = re.sub(r"<(\w+)>", r"(?P<\1>\\S+)", re.escape(pattern).replace(r"\ ", " ").replace(r"\<", "<").replace(r"\>", ">"))
    echoed = next(
        ln for ln in RECONCILE.read_text().splitlines() if 'echo "mirror-reconcile repaired' in ln
    )
    assert echoed.strip() == 'echo "mirror-reconcile repaired $repo $dst $have -> $want"'
    line = "mirror-reconcile repaired derio-homelab/kid-laptops sync-pr-4 abc -> def"
    m = re.search(regex, line)
    assert m and m.group("repo") == "derio-homelab/kid-laptops"


def test_sync_failing_runbook_no_longer_claims_kid_laptops_is_unreconciled() -> None:
    rb = _rules()["layer-25-mirror-sync-failing"]["annotations"]["runbook"]
    assert "not reconciled" not in rb
    assert UID in rb
