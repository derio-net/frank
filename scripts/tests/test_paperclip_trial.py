"""Render the inactive trial contract without credentials or cluster access."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "apps/paperclip-trial"
SHA = "a" * 40
DIGEST = "b" * 64


def helm(chart, *args):
    return subprocess.run(
        ["helm", "template", "trial", str(chart), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def resources(result):
    assert result.returncode == 0, result.stderr
    return [resource for resource in yaml.safe_load_all(result.stdout) if resource]


@pytest.fixture
def qualified_values(tmp_path):
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    values["enabled"] = True
    values["storageClassName"] = "test-storage"
    for component in ("app", "database"):
        values[component].update(
            image=f"example.invalid/{component}@sha256:{DIGEST}",
            sourceRevision=SHA,
            configSecret=f"trial-{component}-config",
            runAsUser=1000,
            mountPath=f"/data/{component}",
        )
    path = tmp_path / "values.json"
    path.write_text(json.dumps(values))
    return path


def test_defaults_render_no_trial_resources(tmp_path):
    assert resources(helm(CHART)) == []
    root = ROOT / "apps/root"
    actual = helm(root)
    documents = resources(actual)
    assert not any(
        "paperclip-trial" in json.dumps(document) for document in documents
    )
    baseline = tmp_path / "root"
    shutil.copytree(root, baseline)
    (baseline / "templates/paperclip-trial.yaml").unlink()
    values = yaml.safe_load((baseline / "values.yaml").read_text())
    values.pop("paperclipTrial")
    (baseline / "values.yaml").write_text(yaml.safe_dump(values))
    assert resources(helm(baseline)) == documents


def test_registration_is_manual_and_child_stays_disabled():
    result = helm(
        ROOT / "apps/root",
        "--set", "paperclipTrial.enabled=true",
        "--set", f"paperclipTrial.targetRevision={SHA}",
    )
    application = next(
        item for item in resources(result)
        if item.get("metadata", {}).get("name") == "paperclip-trial"
    )
    assert application["metadata"]["finalizers"] == ["resources-finalizer.argocd.argoproj.io"]
    assert "automated" not in application["spec"]["syncPolicy"]
    assert application["spec"]["source"]["targetRevision"] == SHA
    assert application["spec"]["source"]["path"] == "apps/paperclip-trial"
    assert "helm" not in application["spec"]["source"]
    assert resources(helm(CHART)) == []
    unpinned = helm(
        ROOT / "apps/root", "--set", "paperclipTrial.enabled=true",
        "--set", "paperclipTrial.targetRevision=main",
    )
    assert unpinned.returncode != 0


def test_preparation_cannot_start_or_expose_workloads(qualified_values):
    documents = resources(helm(CHART, "-f", str(qualified_values)))
    forbidden = {
        "Secret", "Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding",
        "Ingress", "IngressRoute", "DaemonSet", "Job", "CronJob",
    }
    assert not forbidden.intersection(item["kind"] for item in documents)
    for item in documents:
        if item["kind"] != "Namespace":
            assert item["metadata"]["namespace"] == "paperclip-trial"
    namespace = next(item for item in documents if item["kind"] == "Namespace")
    assert namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"
    policies = [item["spec"] for item in documents if item["kind"] == "NetworkPolicy"]
    assert len(policies) == 1
    assert policies[0] == {
        "podSelector": {}, "policyTypes": ["Ingress", "Egress"],
        "ingress": [], "egress": [],
    }
    services = [item for item in documents if item["kind"] == "Service"]
    assert len(services) == 2
    assert all(item["spec"]["type"] == "ClusterIP" for item in services)
    for item in documents:
        if item["kind"] == "ServiceAccount":
            assert item["automountServiceAccountToken"] is False
        if item["kind"] != "Deployment":
            continue
        assert item["spec"]["replicas"] == 0
        pod = item["spec"]["template"]["spec"]
        assert pod["automountServiceAccountToken"] is False
        assert not any(pod[key] for key in ("hostNetwork", "hostPID", "hostIPC"))
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert pod["securityContext"]["runAsUser"] > 0
        assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
        assert not any("hostPath" in volume for volume in pod["volumes"])
        assert "initContainers" not in pod
        container, = pod["containers"]
        assert container["securityContext"] == {
            "allowPrivilegeEscalation": False, "privileged": False,
            "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]},
        }
        assert "@sha256:" in container["image"]
        assert "env" not in container
        assert "secretRef" in container["envFrom"][0]
        expected = {"cpu": "2", "memory": "4Gi"} if container["name"] == "app" else {"cpu": "1", "memory": "2Gi"}
        assert container["resources"]["limits"] == expected
    claims = [item for item in documents if item["kind"] == "PersistentVolumeClaim"]
    assert sorted(item["spec"]["resources"]["requests"]["storage"] for item in claims) == ["10Gi", "5Gi"]


@pytest.mark.parametrize("override", [
    "app.image=example.invalid/app:latest",
    "database.image=example.invalid/db:latest",
    "app.sourceRevision=main",
    "database.sourceRevision=main",
    "app.runAsUser=0",
    "database.runAsUser=0",
    "app.configSecret=",
    "app.mountPath=/",
    "database.mountPath=/tmp",
    "storageClassName=",
    "namespace=paperclip-system",
    "network.profile=allow-all",
    "app.password=must-not-be-accepted",
    "database.password=must-not-be-accepted",
    "app.replicas=1",
])
def test_unsafe_or_incomplete_inputs_refuse(qualified_values, override):
    result = helm(CHART, "-f", str(qualified_values), "--set", override)
    assert result.returncode != 0, result.stdout


def test_enable_without_pins_refuses():
    assert helm(CHART, "--set", "enabled=true").returncode != 0
