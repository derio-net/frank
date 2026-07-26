"""Guard the kid-laptops CI namespace and its VirtualMachineInstance RBAC.

Requirement 5 of `derio-homelab/kid-laptops` issue #43: the molecule tasks need
a ServiceAccount that can create and delete VMIs, bound per-task so clone and
lint stay unprivileged.

Two things here are easy to get wrong and silent when wrong:

  - **The verb set.** The request asks for exactly get/list/watch/create/delete.
    A later "just make it work" widening to `*` would grant the CI runner the
    ability to modify VMIs in flight. The test asserts the SET, not a subset.

  - **The EventListener's own RoleBinding.** `tekton-triggers-sa` has a
    namespace-scoped RoleBinding in `tekton-pipelines` only. Creating a
    PipelineRun in `kid-laptops-ci` therefore fails with a Forbidden that
    surfaces only in the EventListener pod log — the webhook returns 202 and
    nothing else complains.

Note this RBAC is valid before KubeVirt is installed: RBAC rules are opaque
strings and the API server does not resolve them against installed CRDs. That
is deliberate, not an oversight — see
`docs/superpowers/specs/2026-07-26--cicd--kid-laptops-tekton-ci-design.md`.
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
NS_TEMPLATE = REPO / "apps/root/templates/ns-kid-laptops-ci.yaml"
RBAC = REPO / "apps/tekton/manifests/kid-laptops-ci-rbac.yaml"

NAMESPACE = "kid-laptops-ci"
SA_NAME = "kid-laptops-ci-kubevirt"
TRIGGERS_SA = "tekton-triggers-sa"
TRIGGERS_SA_NS = "tekton-pipelines"
TRIGGERS_CLUSTERROLE = "tekton-triggers-eventlistener-roles"

EXPECTED_VERBS = {"get", "list", "watch", "create", "delete"}


def _docs(path: Path) -> list[dict]:
    assert path.exists(), f"missing manifest: {path.relative_to(REPO)}"
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _of_kind(docs: list[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def test_namespace_template_declares_kid_laptops_ci() -> None:
    namespaces = _of_kind(_docs(NS_TEMPLATE), "Namespace")
    names = [ns["metadata"]["name"] for ns in namespaces]
    assert names == [NAMESPACE], f"expected exactly [{NAMESPACE}], got {names}"


def test_service_account_exists_in_ci_namespace() -> None:
    accounts = _of_kind(_docs(RBAC), "ServiceAccount")
    matching = [
        sa
        for sa in accounts
        if sa["metadata"]["name"] == SA_NAME
        and sa["metadata"].get("namespace") == NAMESPACE
    ]
    assert matching, (
        f"no ServiceAccount {SA_NAME} in namespace {NAMESPACE}; "
        "the PipelineRun's taskRunSpecs reference it by name"
    )


def test_vmi_role_grants_exactly_the_requested_verbs() -> None:
    roles = _of_kind(_docs(RBAC), "Role")
    vmi_rules = [
        rule
        for role in roles
        for rule in role.get("rules", [])
        if "virtualmachineinstances" in rule.get("resources", [])
    ]
    assert len(vmi_rules) == 1, (
        f"expected exactly one rule covering virtualmachineinstances, "
        f"found {len(vmi_rules)}"
    )
    rule = vmi_rules[0]
    assert rule["apiGroups"] == ["kubevirt.io"], rule["apiGroups"]
    assert rule["resources"] == ["virtualmachineinstances"], rule["resources"]
    assert set(rule["verbs"]) == EXPECTED_VERBS, (
        f"verb set drifted from the request: {sorted(rule['verbs'])} "
        f"!= {sorted(EXPECTED_VERBS)}"
    )


def test_eventlistener_sa_can_create_pipelineruns_in_ci_namespace() -> None:
    bindings = _of_kind(_docs(RBAC), "RoleBinding")
    for rb in bindings:
        if rb["metadata"].get("namespace") != NAMESPACE:
            continue
        if rb["roleRef"]["name"] != TRIGGERS_CLUSTERROLE:
            continue
        subjects = rb.get("subjects", [])
        if any(
            s.get("kind") == "ServiceAccount"
            and s.get("name") == TRIGGERS_SA
            and s.get("namespace") == TRIGGERS_SA_NS
            for s in subjects
        ):
            assert rb["roleRef"]["kind"] == "ClusterRole", rb["roleRef"]
            return
    raise AssertionError(
        f"no RoleBinding in {NAMESPACE} granting {TRIGGERS_CLUSTERROLE} to "
        f"{TRIGGERS_SA_NS}/{TRIGGERS_SA} — the EventListener would get a "
        "Forbidden visible only in its pod log"
    )
