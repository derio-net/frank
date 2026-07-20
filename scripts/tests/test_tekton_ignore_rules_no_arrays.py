"""Tripwire: no array-item jqPathExpressions in tekton-extras ignoreDifferences.

With RespectIgnoreDifferences=true, an ignoreDifferences jqPathExpression that
addresses ARRAY ITEMS (e.g. `.spec.triggers[]?...`) makes ArgoCD carry the
LIVE array into every apply — updates to that array are silently discarded
while syncs report Succeeded. Incident 2026-07-20: both EventListeners were
frozen at their Jun 13 state for five weeks (cnc triggers, gitea-actions
triggers never went live) because of `.spec.triggers[]?` rules added Jul 6.

Defaulted per-item fields must instead be set explicitly in the manifests
(bindings `kind: TriggerBinding`, cel refs `kind: ClusterInterceptor`) so no
ignore rule is needed. This test also pins that convention.

Known debt: the Pipeline/Task rules in the same file still use array-item
expressions (`.spec.tasks[]?`, `.spec.results[]?`) and are exempted below —
they carry the same freeze risk for Pipeline/Task UPDATES and need the same
explicit-defaults treatment (tracked as follow-up).
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TEKTON_EXTRAS = REPO_ROOT / "apps/root/templates/tekton-extras.yaml"

# TODO(follow-up): shrink to empty by fixing Pipeline/Task the same way.
EXEMPT_KINDS = {"Pipeline", "Task"}


def _app():
    text = TEKTON_EXTRAS.read_text()
    # Application template contains Helm-isms; neutralize before parsing
    for ph in ("{{ .Values.repoURL }}", "{{ .Values.targetRevision }}", "{{ .Values.destination.server }}"):
        text = text.replace(ph, "PLACEHOLDER")
    return yaml.safe_load(text)


def test_no_array_item_ignore_rules_outside_exemptions():
    offenders = []
    for rule in _app()["spec"].get("ignoreDifferences", []):
        if rule.get("kind") in EXEMPT_KINDS:
            continue
        for expr in rule.get("jqPathExpressions", []) or []:
            if "[]" in expr:
                offenders.append((rule.get("kind"), expr))
    assert not offenders, (
        "array-item jqPathExpressions silently freeze array updates under "
        f"RespectIgnoreDifferences — set defaults explicitly instead: {offenders}"
    )


def test_eventlistener_manifests_carry_explicit_defaults():
    for f in ("eventlistener-github.yaml", "eventlistener.yaml"):
        for doc in yaml.safe_load_all(
            (REPO_ROOT / "apps/tekton/triggers" / f).read_text()
        ):
            if not doc or doc.get("kind") != "EventListener":
                continue
            for trig in doc["spec"]["triggers"]:
                for b in trig.get("bindings", []):
                    assert b.get("kind") == "TriggerBinding", (f, trig["name"], b)
                for i in trig.get("interceptors", []):
                    assert i["ref"].get("kind") == "ClusterInterceptor", (
                        f, trig["name"], i["ref"],
                    )
