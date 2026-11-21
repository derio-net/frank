"""VRAM budget guard for the shared 16 GB card (Ollama + speech models)."""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
BUDGET = REPO / "apps/speech/manifests/files/vram-budget.yaml"
OLLAMA_VALUES = REPO / "apps/ollama/values.yaml"
TIMESLICING = REPO / "apps/gpu-operator-extras/manifests/time-slicing-config.yaml"
GPU_OPERATOR_VALUES = REPO / "apps/gpu-operator/values.yaml"
SWITCHER = REPO / "apps/gpu-switcher/manifests/deployment.yaml"


def _budget():
    return yaml.safe_load(BUDGET.read_text())


def _largest_group_size():
    dep = yaml.safe_load(SWITCHER.read_text())
    env = {e["name"]: e["value"] for e in dep["spec"]["template"]["spec"]["containers"][0]["env"]}
    groups = {}
    for entry in env["WORKLOADS"].split(","):
        name, _ns, rest = entry.split(":")
        dep_name, _, group = rest.partition("@")
        groups.setdefault(group or name, []).append(name)
    return max(len(v) for v in groups.values())


def test_budget_fits_in_card():
    b = _budget()
    largest_ollama = max(t["vram_gb"] for t in b["ollama"]["allowlist"])
    speech = sum(m["vram_gb"] for m in b["speech"]["models"])
    assert largest_ollama + speech + b["headroom_gb"] < b["total_gb"]
    assert b["total_gb"] == 16


def test_estimates_are_marked():
    b = _budget()
    for m in b["speech"]["models"] + b["ollama"]["allowlist"]:
        assert "estimate" in m, f"{m['name']} must declare estimate: true|false"


def test_every_allowlisted_ollama_tag_exists():
    values = yaml.safe_load(OLLAMA_VALUES.read_text())
    known = {m["name"] for m in values["ollama"]["models"]["create"]}
    known |= set(values["ollama"]["models"].get("pull") or [])
    for t in _budget()["ollama"]["allowlist"]:
        assert t["name"] in known, f"{t['name']} not in apps/ollama/values.yaml"
        assert t["num_ctx"] > 0


def test_time_slicing_replicas_equal_largest_group():
    cm = yaml.safe_load(TIMESLICING.read_text())
    cfg = yaml.safe_load(cm["data"]["any"])
    res = cfg["sharing"]["timeSlicing"]["resources"][0]
    assert cfg["version"] == "v1"
    assert res["name"] == "nvidia.com/gpu"
    assert cfg["sharing"]["timeSlicing"]["renameByDefault"] is False
    assert res["replicas"] == _largest_group_size()


def test_device_plugin_references_the_configmap():
    cm = yaml.safe_load(TIMESLICING.read_text())
    values = yaml.safe_load(GPU_OPERATOR_VALUES.read_text())
    plugin = values["devicePlugin"]["config"]
    assert plugin["name"] == cm["metadata"]["name"]
    assert plugin["default"] in cm["data"]


def _modelfile_num_ctx(template):
    for line in template.splitlines():
        parts = line.split()
        if parts[:2] == ["PARAMETER", "num_ctx"]:
            return int(parts[2])
    return None


def test_every_ollama_model_is_classified_and_num_ctx_matches():
    """Allowlist is two-directional: each chart-created model is allowed or excluded,
    and the declared num_ctx equals the Modelfile PARAMETER, so the budget cannot
    drift from what Ollama actually loads."""
    values = yaml.safe_load(OLLAMA_VALUES.read_text())
    created = {m["name"]: _modelfile_num_ctx(m["template"]) for m in values["ollama"]["models"]["create"]}
    assert not (values["ollama"]["models"].get("pull") or []), "pulled models are unclassified; add them to the budget"
    b = _budget()["ollama"]
    allowed = {t["name"]: t for t in b["allowlist"]}
    excluded = {t["name"] for t in b["excluded_while_speech_up"]}
    assert set(created) == set(allowed) | excluded
    assert not (set(allowed) & excluded)
    for name, t in allowed.items():
        assert created[name] == t["num_ctx"], f"{name}: num_ctx drifted from the Modelfile"


def test_ollama_loads_one_model_at_a_time():
    values = yaml.safe_load(OLLAMA_VALUES.read_text())
    env = {e["name"]: e["value"] for e in values["extraEnv"]}
    assert env["OLLAMA_MAX_LOADED_MODELS"] == "1"
