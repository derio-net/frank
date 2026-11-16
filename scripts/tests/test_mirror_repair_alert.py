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


# The whole stream filter, compared by EQUALITY (l-tests-r3): a substring check
# lets an appended `OR _msg:"repaired"` broaden the count with tests green.
# `container_name:="push"` is the EXACT-match form (l-tests-r2): LogsQL's
# `container_name:push` is a word filter and also matches Tekton's
# `step-pull-from-github-push-to-gitea`, whose repo-driven output could mint a page.
FILTER = (
    'kubernetes.namespace_name:tekton-pipelines'
    ' AND kubernetes.container_name:="push"'
    ' AND _msg:"mirror-reconcile repaired"'
)
PIPES = ['extract "mirror-reconcile repaired <repo> "', "stats by (repo) count() as value"]


def test_query_shape() -> None:
    rule = _rule()
    a = _data(rule, "A")
    assert a["datasourceUid"] == "affdoo4s9258gc"
    assert a["model"]["queryType"] == "stats"
    stages = [part.strip() for part in a["model"]["expr"].split("|")]
    assert stages[0] == FILTER, stages[0]
    assert stages[1:] == PIPES, stages[1:]


def test_expression_chain_windows_and_pending_period() -> None:
    """l-tests-r1: `condition: B` (a threshold-less reduce) would page on a
    single repair, reversing operator decision q3; a dangling expression ref,
    a shortened window or a `for:` hold changes what the rule means."""
    rule = _rule()
    assert rule["condition"] == "C"
    b, c = _data(rule, "B"), _data(rule, "C")
    assert b["model"]["type"] == "reduce" and b["model"]["expression"] == "A"
    assert b["model"]["reducer"] == "last"
    assert c["model"]["type"] == "threshold" and c["model"]["expression"] == "B"
    for ref in ("A", "B", "C"):
        assert _data(rule, ref)["relativeTimeRange"] == {"from": 21600, "to": 0}, ref
    assert rule["for"] == "0s"


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


def _reconcile_docs() -> list:
    import yaml

    return [d for d in yaml.safe_load_all(RECONCILE.read_text()) if d]


def test_the_filtered_container_runs_the_script_that_echoes_the_repair_line() -> None:
    """l-tests-r4: the rule is blind unless the container it filters on is the
    one that prints the line. Follow container -> command -> ConfigMap script."""
    docs = _reconcile_docs()
    cronjob = next(d for d in docs if d["kind"] == "CronJob" and d["metadata"]["name"] == "mirror-reconcile")
    container_name = re.search(r'container_name:="([^"]+)"', FILTER).group(1)
    pod = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = next(c for c in pod["containers"] if c["name"] == container_name)
    script_path = next(a for a in container["command"] if a.startswith("/scripts/"))
    vol = next(m for m in container["volumeMounts"] if m["mountPath"] == "/scripts")["name"]
    cm_name = next(v for v in pod["volumes"] if v["name"] == vol)["configMap"]["name"]
    cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == cm_name)
    script = cm["data"][script_path.removeprefix("/scripts/")]
    assert 'echo "mirror-reconcile repaired $repo $dst $have -> $want"' in script
    # and no initContainer echoes it, which would put the lines on another stream
    for init in pod.get("initContainers", []):
        init_script = next((a for a in init.get("command", []) if a.startswith("/scripts/")), None)
        if init_script:
            assert "mirror-reconcile repaired" not in cm["data"].get(init_script.removeprefix("/scripts/"), "")


def test_extract_pattern_captures_the_repo_from_the_echoed_line_shape() -> None:
    expr = _data(_rule(), "A")["model"]["expr"]
    pattern = re.search(r'extract "([^"]+)"', expr).group(1)
    regex = re.escape(pattern).replace(re.escape("<repo>"), r"(?P<repo>\S+)")
    for line, repo in [
        ("mirror-reconcile repaired derio-homelab/kid-laptops refs/heads/sync-pr-4 - -> def", "derio-homelab/kid-laptops"),
        ("mirror-reconcile repaired derio-net/willikins refs/heads/main abc -> def", "derio-net/willikins"),
    ]:
        m = re.search(regex, line)
        assert m and m.group("repo") == repo, line
    # the result summary line must not be counted as a repair
    assert not re.search(regex, "mirror-reconcile result dry_run=0 drift=1 repaired=1 skipped=0 failed=0 plan_errors=0")


def test_sync_failing_runbook_no_longer_claims_kid_laptops_is_unreconciled() -> None:
    rb = _rules()["layer-25-mirror-sync-failing"]["annotations"]["runbook"]
    assert "not reconciled" not in rb
    assert UID in rb
