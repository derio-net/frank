"""Tripwire: no array-item jqPathExpressions in ANY Application's ignoreDifferences.

With RespectIgnoreDifferences=true, an ignoreDifferences jqPathExpression that
addresses ARRAY ITEMS (e.g. `.spec.triggers[]?...`) makes ArgoCD carry the
LIVE array into every apply — updates to that array are silently discarded
while syncs report Succeeded. Incident 2026-07-20: both EventListeners were
frozen at their Jun 13 state for five weeks (cnc triggers, gitea-actions
triggers never went live) because of `.spec.triggers[]?` rules added Jul 6.

Defaulted fields must instead be set explicitly in the manifests so no ignore
rule is needed. This test also pins that convention for EventListeners,
Pipelines, and Tasks.

Known debt, exempted below with reasons:
  - stoa-live-mirror-sync still has `.spec.triggers[]?` and
    `.spec.results[]?` rules on its externally sourced EventListener and Task.
    Found 2026-07-26 only because this test was widened from a single file to
    every Application; the fix is cross-repo.

The widening is the lesson: this file had forbidden `.spec.triggers[]?` since
July while a second Application carried exactly that pattern, unseen, because
the guard hard-coded one path. A tripwire scoped to one instance of a class
gives the reassurance of coverage without the fact of it.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# Scan EVERY Application template, not just tekton-extras.
#
# This test guarded exactly one file until 2026-07-26, which is how
# apps/root/templates/stoa-live-mirror-sync.yaml kept `.spec.triggers[]?` rules
# on its own EventListener — the identical pattern this file exists to forbid,
# in a different Application, invisible to the guard. A tripwire that covers one
# instance of a class gives the reassurance of coverage without the fact of it.
APP_TEMPLATE_DIRS = [
    REPO_ROOT / "apps/root/templates",
    REPO_ROOT / "clusters/hop/apps/root/templates",
]

# Per-offender exemptions, each with the reason it is tolerated. Keyed by
# "<template>::<kind>". An entry here is a deliberate, reviewable act — the
# alternative (a silent blanket exemption) is what let the live-mirror-sync
# rules sit unnoticed while this file claimed to forbid exactly that pattern.
EXEMPT_RULES = {
    # DELIBERATE and unrelated to trigger freezing: the VictoriaMetrics chart
    # regenerates its webhook caBundle on every render (genCA), so without this
    # the app never converges. Documented in frank-gotchas.md. The array here is
    # a webhook list whose contents we never edit, so freezing costs nothing.
    "apps/root/templates/victoria-metrics.yaml::ValidatingWebhookConfiguration":
        "chart genCA regenerates caBundle each render; array contents never hand-edited",

    # NOT deliberate — a REAL latent instance of the freeze bug, found 2026-07-26
    # when this test was widened beyond tekton-extras. `.spec.triggers[]?` rules
    # on the live-mirror-sync EventListener mean any future edit to its trigger
    # array would be silently discarded while syncs report Succeeded, exactly as
    # happened to the other two listeners for five weeks (Jun 13 -> Jul 20).
    #
    # Latent rather than active: the one trigger it carries (companies-main-push)
    # works today, and the freeze only bites on UPDATES.
    #
    # Not fixed here because the fix is cross-repo: the remedy is to set the
    # defaulted per-item fields (bindings kind, interceptor ref kind) explicitly
    # in the EventListener manifest, which this Application sources from
    # `stoa/ci/tekton/live-mirror-sync` in ANOTHER repository. Dropping the rules
    # from frank alone would unfreeze the array but leave the app permanently
    # OutOfSync on those defaults — trading a silent failure for a noisy one that
    # people learn to ignore. Do both halves together.
    "apps/root/templates/stoa-live-mirror-sync.yaml::EventListener":
        "FREEZE RISK, tracked: fix needs explicit defaults in the stoa repo's EventListener manifest",
    "apps/root/templates/stoa-live-mirror-sync.yaml::Task":
        "FREEZE RISK, tracked: fix needs explicit result types in the stoa repo's Task manifest",
}


def _apps():
    """Every Application in the root charts, Helm-isms neutralised."""
    out = []
    for d in APP_TEMPLATE_DIRS:
        for f in sorted(d.glob("*.yaml")):
            text = f.read_text()
            # Values interpolations are not YAML; blank them before parsing.
            text = re.sub(r"\{\{[^}]*\}\}", "PLACEHOLDER", text)
            try:
                docs = list(yaml.safe_load_all(text))
            except yaml.YAMLError:
                continue
            for doc in docs:
                if doc and doc.get("kind") == "Application":
                    out.append((f.relative_to(REPO_ROOT), doc))
    assert out, "no Application templates parsed — did the root charts move?"
    return out


def _array_item_rules():
    """[(exemption-key, path, kind, expr)] for every array-item ignore rule."""
    out = []
    for path, app in _apps():
        for rule in app["spec"].get("ignoreDifferences", []) or []:
            for expr in rule.get("jqPathExpressions", []) or []:
                if "[]" in expr:
                    out.append((f"{path}::{rule.get('kind')}", path, rule.get("kind"), expr))
    return out


def test_no_array_item_ignore_rules_outside_exemptions():
    offenders = [f"{p}  {k}  {e}" for key, p, k, e in _array_item_rules()
                 if key not in EXEMPT_RULES]
    assert not offenders, (
        "array-item jqPathExpressions silently freeze array updates under "
        "RespectIgnoreDifferences: ArgoCD carries the LIVE array into every "
        "apply, so edits are discarded while syncs report Succeeded. Set the "
        "defaulted per-item fields explicitly in the manifests instead.\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


def test_eventlistener_manifests_carry_explicit_defaults():
    for f in ("eventlistener-github.yaml", "eventlistener.yaml"):
        for doc in yaml.safe_load_all(
            (REPO_ROOT / "apps/tekton/triggers" / f).read_text()
        ):
            if not doc or doc.get("kind") != "EventListener":
                continue
            assert "namespaceSelector" in doc["spec"], f
            pod_template = doc["spec"]["resources"]["kubernetesResource"]["spec"]["template"]
            assert pod_template.get("metadata", {}).get("creationTimestamp", "ABSENT") is None, f
            assert pod_template["spec"].get("containers", "ABSENT") is None, f
            for trig in doc["spec"]["triggers"]:
                for b in trig.get("bindings", []):
                    assert b.get("kind") == "TriggerBinding", (f, trig["name"], b)
                for i in trig.get("interceptors", []):
                    assert i["ref"].get("kind") == "ClusterInterceptor", (
                        f, trig["name"], i["ref"],
                    )


def test_pipeline_and_task_manifests_carry_explicit_defaults():
    for f in sorted((REPO_ROOT / "apps/tekton").rglob("*.yaml")):
        if "vendor" in f.parts:
            continue
        for doc in yaml.safe_load_all(f.read_text()):
            if not doc or doc.get("kind") not in {"Pipeline", "Task"}:
                continue
            spec = doc["spec"]
            if doc["kind"] == "Task":
                for result in spec.get("results", []):
                    assert "type" in result, (f, result)
                continue

            for task in [*spec.get("tasks", []), *spec.get("finally", [])]:
                if "taskRef" in task:
                    assert "kind" in task["taskRef"], (f, task)
                if "taskSpec" not in task:
                    continue
                task_spec = task["taskSpec"]
                assert "metadata" in task_spec, (f, task["name"])
                assert "spec" in task_spec, (f, task["name"])
                if "stepTemplate" in task_spec:
                    assert "computeResources" in task_spec["stepTemplate"], (
                        f, task["name"], "stepTemplate"
                    )
                for step in task_spec.get("steps", []):
                    assert "computeResources" in step, (f, task["name"], step["name"])


def test_exempt_rules_are_all_still_present():
    """A stale exemption silently re-opens the pattern it was granted for."""
    present = {key for key, *_ in _array_item_rules()}
    dead = sorted(set(EXEMPT_RULES) - present)
    assert not dead, (
        "EXEMPT_RULES entries whose rule no longer exists — delete them so the "
        "exemption list keeps meaning something:\n" + "\n".join(f"  - {d}" for d in dead)
    )
