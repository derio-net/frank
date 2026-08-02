"""Tests for the OVMS retrieval model image — the CI-built OpenVINO IR bundle
for an embeddings model and a rerank model, served by a STOCK
`openvino/model_server` image.

Contract source of truth:
docs/superpowers/specs/2026-08-02--infer--igpu-embedding-rerank-design.md
("The runtime gate", "Model acquisition — a CI-built model image", "Images")

Why this file exists: the spec's live gate proved `ovms --pull` cannot convert
these models at runtime — no published OVMS image carries `optimum-intel`, and
the pre-converted `OpenVINO/` HF org only has English variants. So the
OpenVINO IR is built ONCE in CI, with OVMS's own `export_model.py` (not raw
`optimum-cli`, which does not also emit the tokenizer XML / graph.pbtxt /
merged config.json OVMS needs), and shipped as a model-only image. The
runtime stays stock; this image is the only thing Frank maintains.

These tests assert SHAPE only — no docker build, no network, no cluster. The
export itself is exercised live by the CI workflow this Dockerfile feeds.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "apps/ovms-retrieval/docker/Dockerfile"
WORKFLOW = REPO / ".github/workflows/build-ovms-retrieval-models.yml"

# Kept generic/technical on purpose — see agents/rules/third-party-privacy.md
# and the spec's "Scope discipline": this is the driver for the model choice,
# not anything about the private requester or its corpus.
EMBEDDINGS_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

FLOATING_REFS = {"main", "master", "HEAD", "latest", "trunk", "develop"}
PINNED_REF_RE = re.compile(r"^v?\d+\.\d+(\.\d+)?[a-zA-Z0-9]*$|^[0-9a-f]{40}$")


def _dockerfile_text() -> str:
    assert DOCKERFILE.exists(), f"{DOCKERFILE} must exist"
    return DOCKERFILE.read_text()


def _stages(text: str) -> list[tuple[str, str]]:
    """Split a Dockerfile into (FROM line, stage body) pairs, in order."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^\s*FROM\s", line)]
    assert starts, "Dockerfile has no FROM instruction"
    stages = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(lines)
        stages.append((lines[start], "\n".join(lines[start:end])))
    return stages


def _workflow_doc() -> dict:
    assert WORKFLOW.exists(), f"{WORKFLOW} must exist"
    doc = yaml.safe_load(WORKFLOW.read_text())
    assert doc, "workflow YAML did not parse"
    return doc


def _triggers(doc: dict) -> dict:
    # PyYAML (1.1 bool resolution) parses the bare `on:` key as boolean True.
    return doc.get("on", doc.get(True))


def _build_step(doc: dict) -> dict:
    for step in doc["jobs"]["build"]["steps"]:
        if "build-push-action" in step.get("uses", ""):
            return step
    raise AssertionError("no docker/build-push-action step found in build-ovms-retrieval-models.yml")


# ── Task 1.S1: multi-stage, no export toolchain in final stage, pinned FROMs,
#    export_model.py pinned ──────────────────────────────────────────────


def test_dockerfile_is_multi_stage():
    stages = _stages(_dockerfile_text())
    assert len(stages) >= 2, (
        "Dockerfile must be multi-stage: an export stage (optimum-intel/nncf/torch) "
        "and a minimal final stage that ships only the model artifacts"
    )


def test_every_from_is_version_pinned():
    text = _dockerfile_text()
    for line in text.splitlines():
        if re.match(r"^\s*FROM\s", line):
            assert not re.search(r":latest\b", line), f"bare :latest FROM is not pinned: {line!r}"
            assert re.search(r":\S+", line) or "@sha256:" in line, (
                f"FROM instruction carries no tag or digest: {line!r}"
            )


def test_final_stage_carries_no_export_toolchain():
    stages = _stages(_dockerfile_text())
    _final_from, final_body = stages[-1]
    lowered = final_body.lower()
    for forbidden in ("optimum", "nncf", "torch", "pip install"):
        assert forbidden not in lowered, (
            f"final stage must not contain {forbidden!r} — the export toolchain "
            "(optimum-intel/nncf/torch) must never reach the cluster"
        )


def test_final_stage_only_copies_out_directory():
    stages = _stages(_dockerfile_text())
    _final_from, final_body = stages[-1]
    assert re.search(r"COPY\s+--from=\S+\s+/out\s+/models-src", final_body), (
        "final stage must be a bare COPY --from=<export stage> /out /models-src"
    )


def test_export_model_py_fetched_at_pinned_ref():
    text = _dockerfile_text()
    assert "export_model.py" in text
    m = re.search(
        r"openvinotoolkit/model_server/([^/\s\"']+)/demos/common/export_models/export_model\.py",
        text,
    )
    assert m, (
        "export_model.py must be fetched from openvinotoolkit/model_server "
        "(OVMS's own exporter — the gate showed raw optimum-cli output is not "
        "servable) at an explicit ref"
    )
    ref = m.group(1)
    if "$" in ref:
        # fetched via a build ARG interpolation — resolve the ARG's default.
        arg_name = re.sub(r"[{}$]", "", ref)
        default = re.search(rf"ARG\s+{re.escape(arg_name)}=(\S+)", text)
        assert default, f"ARG {arg_name} is referenced but has no pinned default"
        ref = default.group(1)
    assert ref not in FLOATING_REFS, f"export_model.py ref {ref!r} is a floating branch — pin it"
    assert PINNED_REF_RE.match(ref), (
        f"export_model.py ref {ref!r} must be a version tag (vN.N[.N]) or a 40-hex commit SHA"
    )


# ── Task 1.S2: both models exported, int8, two device repositories,
#    MODELS_REV build arg ────────────────────────────────────────────────


def test_exports_both_models_with_int8_weight_format():
    text = _dockerfile_text()
    assert "embeddings_ov" in text, "must export the embeddings model via the embeddings_ov task"
    assert EMBEDDINGS_MODEL in text, f"must export {EMBEDDINGS_MODEL}"
    assert "rerank_ov" in text, "must export the rerank model via the rerank_ov task"
    assert RERANK_MODEL in text, f"must export {RERANK_MODEL}"
    assert text.count("--weight-format int8") >= 2, (
        "both models must be exported at --weight-format int8 "
        "(the gate showed export without a weight-format does not produce a servable model)"
    )


def test_exports_two_device_repositories_gpu_and_cpu():
    text = _dockerfile_text()
    assert "--target_device GPU" in text, "must produce a GPU-targeted repository"
    assert "--target_device CPU" in text, (
        "must produce a CPU-targeted repository — the benchmark's control arm, "
        "since target_device is baked into graph.pbtxt at export time"
    )
    assert "/out/gpu" in text, "GPU exports must land under /out/gpu"
    assert "/out/cpu" in text, "CPU exports must land under /out/cpu"


def test_both_models_exported_for_both_devices():
    text = _dockerfile_text()
    # Four export invocations total: {embeddings,rerank} x {GPU,CPU}.
    assert text.count("embeddings_ov") >= 2, "embeddings model must be exported for both devices"
    assert text.count("rerank_ov") >= 2, "rerank model must be exported for both devices"


def test_models_rev_build_arg_exists():
    text = _dockerfile_text()
    assert re.search(r"^\s*ARG\s+MODELS_REV\b", text, re.MULTILINE), (
        "Dockerfile must declare ARG MODELS_REV so the image tag moves when model contents change"
    )


# ── Task 1.S3: workflow triggers (pull_request build-only, push:main
#    build+publish), immutable tag ───────────────────────────────────────


def test_workflow_triggers_on_pull_request_and_push_to_main():
    triggers = _triggers(_workflow_doc())
    assert triggers, "workflow must declare triggers"
    assert "pull_request" in triggers, (
        "must build on pull_request — every sibling build-*.yml in this repo is "
        "push:main only, which means a Dockerfile change reaches main entirely unbuilt"
    )
    assert "push" in triggers, "must build and publish on push to main"
    assert triggers["push"].get("branches") == ["main"], "push trigger must be scoped to main"


def test_triggers_filtered_to_docker_dir():
    triggers = _triggers(_workflow_doc())
    for event in ("pull_request", "push"):
        paths = (triggers.get(event) or {}).get("paths", [])
        assert any("apps/ovms-retrieval/docker" in p for p in paths), (
            f"{event} trigger must be filtered to apps/ovms-retrieval/docker/**"
        )


def test_pull_request_builds_without_pushing_to_registry():
    doc = _workflow_doc()
    step = _build_step(doc)
    push_val = str(step["with"]["push"])
    assert "pull_request" in push_val, (
        "the build step's `push:` must be conditioned on the event not being pull_request "
        "(a fork PR also gets a read-only token with no registry secrets)"
    )


def test_published_tag_is_immutable_not_only_latest():
    doc = _workflow_doc()
    step = _build_step(doc)
    tags = step["with"]["tags"]
    assert "MODELS_REV" in tags, (
        "published tags must embed MODELS_REV so the tag is immutable, not just latest"
    )
    assert "latest" in tags, "latest should still be published alongside the immutable tag"


def test_dockerfile_receives_models_rev_as_build_arg():
    doc = _workflow_doc()
    step = _build_step(doc)
    build_args = step["with"].get("build-args", "")
    assert "MODELS_REV" in build_args, (
        "workflow must pass MODELS_REV through as a build-arg so the Dockerfile ARG "
        "actually varies with the workflow's pinned revision"
    )


def test_actions_are_pinned_to_commit_shas():
    doc = _workflow_doc()
    for step in doc["jobs"]["build"]["steps"]:
        uses = step.get("uses")
        if not uses or "/" not in uses:
            continue
        ref = uses.rsplit("@", 1)[-1]
        assert re.match(r"^[0-9a-f]{40}$", ref), (
            f"{uses!r} is not pinned to a commit SHA "
            "(see .github/workflows/repo-tripwires.yml for the `sha # vX.Y.Z` convention)"
        )
