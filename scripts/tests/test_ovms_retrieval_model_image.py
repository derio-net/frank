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

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
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
    """Name-based AND structural.

    The name list alone is a weak guard: `COPY --from=export
    /usr/local/lib/python3.12 /opt/py` drags the entire export toolchain into
    the shipped image while mentioning none of the forbidden words. So the
    final stage is also required to contain exactly ONE `COPY --from=`, the
    `/out` one — anything else is toolchain, cache or credentials arriving by
    a path this list cannot enumerate.
    """
    stages = _stages(_dockerfile_text())
    _final_from, final_body = stages[-1]
    lowered = final_body.lower()
    for forbidden in ("optimum", "nncf", "torch", "pip install"):
        assert forbidden not in lowered, (
            f"final stage must not contain {forbidden!r} — the export toolchain "
            "(optimum-intel/nncf/torch) must never reach the cluster"
        )

    cross_stage_copies = re.findall(r"^\s*COPY\s+--from=\S+\s+(\S+)", final_body, re.M)
    assert cross_stage_copies == ["/out"], (
        "the final stage must copy /out and nothing else from the export "
        f"stage; found copies of {cross_stage_copies} — a second COPY --from "
        "is how the export toolchain reaches the cluster without ever naming "
        "itself"
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
    """POLARITY, not just the presence of the word `pull_request`.

    The first version of this assertion was `"pull_request" in push_val`,
    which is satisfied by `!=`, by `==`, by `... || true` and by
    `true # pull_request` alike. The inverted form is the damaging one and it
    is silent in the direction that matters: on `push: main` the expression
    evaluates false, so the image is never published, the Deployment's pinned
    tag ImagePullBackOffs on first sync, and the PR that caused it merged
    green with the build job passing.
    """
    doc = _workflow_doc()
    step = _build_step(doc)
    push_val = str(step["with"]["push"])
    assert push_val.replace(" ", "") == "${{github.event_name!='pull_request'}}", (
        "the build step's `push:` must be exactly "
        "`${{ github.event_name != 'pull_request' }}` — publish on push:main, "
        "never from a PR (a fork PR gets a read-only token and no registry "
        f"secrets). Got: {push_val!r}"
    )


def test_published_tag_is_the_immutable_rev_and_never_latest():
    """One tag, the rev. `:latest` is deliberately NOT published.

    Nothing consumes it — the Deployment pins the rev and
    test_both_images_are_tag_pinned_and_never_latest forbids it from doing
    anything else — and on an image whose whole premise is "new contents get a
    new rev" a floating tag is an attractive nuisance: it makes republishing
    under an unchanged rev feel survivable, which is precisely the drift
    test_models_rev_moves_when_the_dockerfile_changes exists to refuse.
    """
    doc = _workflow_doc()
    step = _build_step(doc)
    tags = str(step["with"]["tags"])
    assert "MODELS_REV" in tags, (
        "published tags must embed MODELS_REV so the published tag is immutable"
    )
    assert "latest" not in tags, (
        f"`:latest` must not be published for the model image: {tags!r}"
    )


def test_pull_request_and_push_path_filters_are_identical():
    """Asymmetric filters publish nothing on merge, and only on some PRs.

    The PR filter used to include this workflow file while the push filter did
    not. A PR that edits ONLY this file (bumping MODELS_REV, changing `tags:`)
    would then build on the PR — green, reassuring — and on merge match no
    push path, so no image is ever published and the Deployment's pinned tag
    ImagePullBackOffs. The failing half is the half that does not run, so
    there is nothing on the PR page to notice.
    """
    triggers = _triggers(_workflow_doc())
    pr_paths = (triggers.get("pull_request") or {}).get("paths")
    push_paths = (triggers.get("push") or {}).get("paths")
    assert pr_paths and push_paths, (triggers.get("pull_request"), triggers.get("push"))
    assert sorted(pr_paths) == sorted(push_paths), (
        "pull_request and push path filters must be identical — a path that "
        "builds on a PR but does not publish on merge is a silently unpublished "
        f"image. pull_request={pr_paths}, push={push_paths}"
    )


def test_the_model_image_does_not_consume_the_repo_wide_actions_cache():
    """A multi-GB model image must not sit in a 10 GB repo-wide LRU.

    GitHub's Actions cache is scoped to the REPOSITORY, so caching this
    image's layers evicts the entries build-comfyui.yml and build-openrgb.yml
    (the only other `type=gha` consumers here) depend on — a cross-workflow
    slowdown with no owner. `mode=min` is not a fix: the final stage IS the
    weights, and the expensive part (pip install + four export_model.py runs)
    lives in a stage `mode=min` does not export.
    """
    step = _build_step(_workflow_doc())
    for key in ("cache-from", "cache-to"):
        value = str(step["with"].get(key, ""))
        assert "type=gha" not in value, (
            f"{key}: {value!r} puts a multi-GB model image into the repo-wide "
            "10 GB Actions cache, evicting the sibling build workflows' entries"
        )


# ── the MODELS_REV drift gate ─────────────────────────────────────────────
#
# Three separate mechanisms assume the rev moves when the model bytes move,
# and until this gate none of them enforced it:
#   - `imagePullPolicy: IfNotPresent` (a republished tag is never re-pulled),
#   - the seed marker skip (compares MODELS_REV, not content),
#   - the deployment-tag ↔ workflow-env test above (ties the two rev
#     DECLARATIONS to each other, neither to the Dockerfile).
# Change `--weight-format int8` to `int4` and leave MODELS_REV at "1": CI
# republishes `:1` with different bytes, the manifest is byte-identical so
# ArgoCD sees nothing, the node cache serves the old image, and even if the
# new image did land the marker still reads `1` so the seed skips. Old
# weights, served indefinitely, everything green — the comfyui seed-if-absent
# bug reintroduced one layer up.


def _git(*args: str) -> tuple[int, str]:
    """Run git in this repo. Returns (127, "") if git is unavailable at all."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, proc.stdout


def _baseline_ref() -> str | None:
    # The override exists so this gate can be exercised against a chosen
    # baseline (that is how it was mutation-proven — pointing it at HEAD, then
    # editing the Dockerfile). It is not a way to disable the gate: an
    # unresolvable ref falls through to the normal search below.
    override = os.environ.get("OVMS_MODELS_REV_BASE_REF")
    for ref in ([override] if override else []) + ["origin/main", "main"]:
        code, _ = _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if code == 0:
            return ref
    return None


def _significant_dockerfile_lines(text: str) -> list[str]:
    """Instruction lines only.

    Blank lines and whole-line comments are dropped so re-wording a comment
    does not demand a rev bump, and `ARG MODELS_REV=` is dropped because the
    rev is the thing being compared, not content it should count as changing.
    """
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^ARG\s+MODELS_REV\b", stripped):
            continue
        out.append(stripped)
    return out


def dockerfile_content_changed(base_text: str, current_text: str) -> bool:
    return _significant_dockerfile_lines(base_text) != _significant_dockerfile_lines(
        current_text
    )


def rev_drift_violation(
    base_text: str, current_text: str, base_rev: str | None, current_rev: str
) -> bool:
    """True when the model contents moved and the rev did not.

    Pure, so the RULE can be tested with synthetic inputs — which matters
    because on the branch that introduces this image there is no baseline to
    diff against, and a gate whose logic is only ever exercised by the
    happy path is the kind of gate this review round exists to find.
    """
    return dockerfile_content_changed(base_text, current_text) and current_rev == base_rev


def test_rev_drift_rule_flags_a_content_change_that_keeps_the_rev():
    base = _dockerfile_text()
    int4 = base.replace("--weight-format int8", "--weight-format int4")
    assert int4 != base, "fixture no longer contains --weight-format int8"
    assert rev_drift_violation(base, int4, "1", "1"), (
        "changing the quantization without moving the rev must be a violation"
    )
    assert not rev_drift_violation(base, int4, "1", "2"), (
        "the same change WITH a rev bump is exactly the intended workflow"
    )


def test_rev_drift_rule_ignores_comment_and_rev_only_edits():
    base = _dockerfile_text()
    commented = base.replace(
        "# ── final stage", "# (reworded comment)\n# ── final stage", 1
    )
    assert commented != base
    assert not rev_drift_violation(base, commented, "1", "1"), (
        "a comment rewording is not a model-content change — demanding a rev "
        "bump for it would train people to bump reflexively"
    )
    # Read the current rev rather than naming it. This mutation uses the LIVE
    # Dockerfile as its fixture, and the one value in that file guaranteed to
    # move is the rev — so a hard-coded `ARG MODELS_REV=1` makes the
    # replacement a silent no-op the first time the gate above does its job,
    # and the test then fails on exactly the change it exists to bless.
    current = re.search(r"^\s*ARG\s+MODELS_REV=(\S+)", base, re.M)
    assert current, "Dockerfile must declare ARG MODELS_REV"
    old_rev = current.group(1).strip('"')
    new_rev = str(int(old_rev) + 1)
    rev_only = base.replace(f"ARG MODELS_REV={old_rev}", f"ARG MODELS_REV={new_rev}")
    assert rev_only != base
    assert not rev_drift_violation(base, rev_only, old_rev, new_rev), (
        "the ARG default is the rev itself, not content it should count as changing"
    )


def test_models_rev_and_the_dockerfile_arg_default_agree():
    """Always-on half of the drift gate — no git, no network.

    The Dockerfile declares `ARG MODELS_REV=<n>` and the workflow passes
    `MODELS_REV=<n>` as a build-arg. If those disagree, a `docker build`
    without the build-arg (a local reproduction, a future workflow) bakes a
    LABEL claiming a rev the image is not.
    """
    arg_default = re.search(r"^\s*ARG\s+MODELS_REV=(\S+)", _dockerfile_text(), re.M)
    assert arg_default, "Dockerfile must give ARG MODELS_REV an explicit default"
    workflow_rev = str(_workflow_doc()["env"]["MODELS_REV"])
    assert arg_default.group(1).strip('"') == workflow_rev, (
        f"Dockerfile ARG MODELS_REV default {arg_default.group(1)!r} != workflow "
        f"env MODELS_REV {workflow_rev!r}"
    )


def test_models_rev_moves_when_the_dockerfile_changes():
    """Git half: a Dockerfile that differs from the base branch must carry a
    new MODELS_REV.

    Compared against `origin/main` (or `main`), the working tree — not HEAD —
    so an uncommitted edit is caught too. SKIPS rather than errors when git is
    absent or neither ref resolves: a shallow CI checkout of a PR merge commit
    has no `origin/main`, and a guard that hard-fails there would be a guard
    nobody could keep green.
    """
    code, _ = _git("rev-parse", "--git-dir")
    if code != 0:
        pytest.skip("not a git checkout (or git unavailable) — drift gate needs a baseline")
    base = _baseline_ref()
    if base is None:
        pytest.skip("neither origin/main nor main resolves here (shallow checkout?)")

    rel_dockerfile = DOCKERFILE.relative_to(REPO).as_posix()
    rel_workflow = WORKFLOW.relative_to(REPO).as_posix()

    code, base_dockerfile = _git("show", f"{base}:{rel_dockerfile}")
    if code != 0:
        # The image does not exist on the baseline at all — this branch
        # introduces it, so any rev is by definition new.
        return

    code, base_workflow = _git("show", f"{base}:{rel_workflow}")
    base_rev = None
    if code == 0:
        base_doc = yaml.safe_load(base_workflow) or {}
        raw = (base_doc.get("env") or {}).get("MODELS_REV")
        base_rev = None if raw is None else str(raw)

    current_rev = str(_workflow_doc()["env"]["MODELS_REV"])
    assert not rev_drift_violation(
        base_dockerfile, _dockerfile_text(), base_rev, current_rev
    ), (
        f"{rel_dockerfile} differs from {base} but MODELS_REV is still "
        f"{current_rev!r}. Republishing an unchanged tag with changed bytes is "
        "invisible end to end: the manifest does not change so ArgoCD syncs "
        "nothing, imagePullPolicy: IfNotPresent reuses the node-cached image, "
        "and the seed marker compares MODELS_REV only — so the old weights "
        "keep being served with everything green. Bump MODELS_REV in "
        f"{rel_workflow} (and the Dockerfile's ARG default) and repin the "
        "Deployment's seed-models image tag."
    )


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


# ── the rerank batch guard ships INSIDE the model image ──────────────────
#
# Contract source of truth for this section:
# docs/superpowers/specs/2026-09-11--infer--ovms-rerank-batch-guard-design.md
#
# `export_model.py`'s `rerank_graph_ov_template` emits exactly three fields
# into the rerank node's options — `models_path`, `plugin_config`,
# `target_device` — so upstream's `max_allowed_chunks` keeps its proto default
# of 10000 documents, four orders of magnitude above what this container's
# memory limit can serve. The exporter is fetched from a pinned ref and is not
# forked, so the export stage rewrites each emitted rerank `graph.pbtxt` with
# `inject_rerank_guard.py` instead.
#
# The rewrite is then RE-READ by the build. That is the point of this section:
# a rewrite which matched nothing publishes a model image with the guard
# absent, and CI, ArgoCD, the pod and the `.seed-rev` marker would all still
# agree that it shipped.

GUARD_INJECTOR = "inject_rerank_guard.py"

# Measured against the live server, not chosen — see the spec's "The numbers".
MAX_ALLOWED_CHUNKS = "64"
MAX_POSITION_EMBEDDINGS = "640"

# The rev that carries the guard. Pinned as a VALUE here;
# test_models_rev_moves_when_the_dockerfile_changes already enforces the
# discipline of moving it, so re-asserting that would say nothing new.
MODELS_REV = "2"

GUARD_FIELDS = ("max_allowed_chunks", "max_position_embeddings")


def _instructions(body: str) -> list[str]:
    """Dockerfile instructions, with `\\` line continuations folded into one."""
    out: list[str] = []
    current: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        current.append(line)
        if not stripped.endswith("\\"):
            out.append("\n".join(current))
            current = []
    if current:
        out.append("\n".join(current))
    return out


def _export_stage_body(text: str) -> str:
    for from_line, body in _stages(text):
        if re.search(r"\bAS\s+export\b", from_line, re.IGNORECASE):
            return body
    raise AssertionError("Dockerfile declares no stage named `export`")


def _guard_instruction(text: str) -> str:
    """The RUN instruction that rewrites the exported rerank graphs."""
    for instruction in _instructions(_export_stage_body(text)):
        if instruction.lstrip().startswith("RUN") and GUARD_INJECTOR in instruction:
            return instruction
    raise AssertionError(
        f"the export stage must RUN {GUARD_INJECTOR} over the exported rerank "
        "graphs — without it the servable keeps upstream's 10000-document "
        "default and one oversized call takes the whole server down"
    )


def _resolve_guard_flag(text: str, flag: str) -> str:
    """Value passed for `flag`, following one level of `ARG` indirection."""
    instruction = _guard_instruction(text)
    match = re.search(rf'{re.escape(flag)}[=\s]+"?\$?\{{?([A-Za-z0-9_]+)\}}?"?', instruction)
    assert match, f"{flag} is not passed to {GUARD_INJECTOR}: {instruction!r}"
    value = match.group(1)
    if value.isdigit():
        return value
    default = re.search(rf"^\s*ARG\s+{re.escape(value)}=(\S+)", text, re.MULTILINE)
    assert default, f"{flag} is given as ${value}, but no `ARG {value}=` default exists"
    return default.group(1).strip('"')


def test_export_stage_copies_the_guard_injector():
    text = _dockerfile_text()
    export_body = _export_stage_body(text)
    assert re.search(rf"^\s*COPY\s+(?!--from=)[^\n]*{re.escape(GUARD_INJECTOR)}", export_body, re.M), (
        f"the export stage must COPY {GUARD_INJECTOR} from the build context "
        "(the build context is apps/ovms-retrieval/docker, where it lives)"
    )
    _final_from, final_body = _stages(text)[-1]
    assert GUARD_INJECTOR not in final_body, (
        f"{GUARD_INJECTOR} is build tooling — it rewrites graphs during export "
        "and has no business in the shipped model-only image"
    )


def test_guard_is_injected_into_both_exported_repositories():
    """GPU and CPU, not just the served one.

    `/out/cpu` is the benchmark's control arm, and a control arm that is
    guarded differently from the arm it controls is not a like-for-like
    comparison — it would silently measure the guard instead of the device.
    """
    instruction = _guard_instruction(_dockerfile_text())
    for repository in ("/out/gpu", "/out/cpu"):
        assert repository in instruction, (
            f"{repository} is not rewritten: {instruction!r}"
        )
    assert "graph.pbtxt" in instruction, "the guard is written into graph.pbtxt"
    assert "RERANK_MODEL_NAME" in instruction, (
        "the rewritten path must be derived from ${RERANK_MODEL_NAME}, not a "
        "second hand-written copy of the model name"
    )


def test_guard_injection_runs_after_the_exports():
    """Order is load-bearing: `export_model.py` writes the file being rewritten."""
    instructions = _instructions(_export_stage_body(_dockerfile_text()))
    exports = [i for i, ins in enumerate(instructions) if "export_model.py rerank_ov" in ins]
    guards = [i for i, ins in enumerate(instructions) if GUARD_INJECTOR in ins and ins.lstrip().startswith("RUN")]
    assert exports and guards, (exports, guards)
    assert min(guards) > max(exports), (
        "the guard must be injected AFTER the last export_model.py invocation — "
        "an earlier rewrite is overwritten by the export that follows it"
    )


def test_guard_ships_the_pair_measured_against_the_live_server():
    text = _dockerfile_text()
    assert _resolve_guard_flag(text, "--max-allowed-chunks") == MAX_ALLOWED_CHUNKS
    assert _resolve_guard_flag(text, "--max-position-embeddings") == MAX_POSITION_EMBEDDINGS


def test_the_build_re_reads_the_graphs_it_rewrote():
    """The build must not take the rewrite on trust.

    `inject_rerank_guard.py` raises on every shape it does not understand, so
    this is belt and braces — but the failure it backstops is the one with no
    other witness. A graph that reaches the registry without both fields is
    indistinguishable, from every downstream signal, from one that has them.
    """
    instruction = _guard_instruction(_dockerfile_text())
    verification = instruction[instruction.rindex(GUARD_INJECTOR) :]
    for field in GUARD_FIELDS:
        assert field in verification, (
            f"nothing in the build re-reads {field} out of the emitted graph "
            f"after the rewrite: {instruction!r}"
        )
    for repository in ("/out/gpu", "/out/cpu"):
        assert repository in verification, (
            f"the verification pass must cover {repository} too"
        )
    assert re.search(r"\bexit\s+1\b", verification), (
        "the verification must FAIL the build when a field is absent — a "
        "report that is only printed is a report nobody reads"
    )


def test_the_dockerfile_says_why_the_exporter_cannot_emit_these_fields():
    """Otherwise a future reader `simplifies` this into a flag that does not exist.

    The issue behind this work proposed `--max_doc_length` as the batch cap. It
    is not one: it never reaches graph.pbtxt at all, it sets the exported
    tokenizer's `model_max_length`. Both that and the template's three-field
    output need to be written down beside the rewrite.
    """
    body = _export_stage_body(_dockerfile_text())
    comments = "\n".join(line for line in body.splitlines() if line.strip().startswith("#"))
    assert "rerank_graph_ov_template" in comments, (
        "the export stage must name the upstream template whose output is being "
        "rewritten, so the rewrite is traceable to what it compensates for"
    )
    assert "max_doc_length" in comments, (
        "the export stage must record that --max_doc_length is NOT this knob — "
        "it sets the tokenizer's model_max_length and never reaches the graph"
    )


def test_models_rev_is_the_rev_that_carries_the_guard():
    text = _dockerfile_text()
    arg_default = re.search(r"^\s*ARG\s+MODELS_REV=(\S+)", text, re.M)
    assert arg_default, "Dockerfile must give ARG MODELS_REV an explicit default"
    assert arg_default.group(1).strip('"') == MODELS_REV, (
        f"Dockerfile ARG MODELS_REV must be {MODELS_REV} — the guard changes the "
        "emitted graphs, so the published tag and the Deployment pin must move"
    )
    assert str(_workflow_doc()["env"]["MODELS_REV"]) == MODELS_REV, (
        f"workflow env MODELS_REV must be {MODELS_REV} too — it is the value that "
        "actually tags the published image"
    )


# The graph.pbtxt this pod was actually serving before the guard existed —
# captured verbatim, never hand-written (see the plan journal entry on its
# missing trailing newline, which is upstream's template and not a capture
# artefact).
LIVE_RERANK_GRAPH = REPO / "scripts/tests/fixtures/ovms-retrieval/rerank-graph.live.pbtxt"
INJECTOR = REPO / "apps/ovms-retrieval/docker" / GUARD_INJECTOR


def _expand_build_args(text: str, value: str) -> str:
    """Substitute `${NAME}` with the Dockerfile's `ARG NAME=` default."""
    def repl(match: re.Match[str]) -> str:
        default = re.search(rf"^\s*ARG\s+{re.escape(match.group(1))}=(\S+)", text, re.M)
        assert default, f"${match.group(1)} has no ARG default"
        return default.group(1).strip('"')

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, value)


def _guard_verification_patterns(text: str) -> list[str]:
    patterns = re.findall(r'grep\s+-qE\s+"([^"]+)"', _guard_instruction(text))
    assert patterns, (
        "the guard's verification pass must use `grep -qE \"<pattern>\"` so the "
        "pattern it asserts on is readable from the Dockerfile"
    )
    return [_expand_build_args(text, p) for p in patterns]


def test_the_builds_verification_matches_what_the_injector_writes(tmp_path):
    """The two halves of the guard are written in different languages.

    `inject_rerank_guard.py` decides the emitted spelling — indentation,
    the space after the colon, which of the two fields carries the trailing
    comma — and the Dockerfile decides what to grep for. Nothing else compares
    them, so a change to either side alone gives a build whose verification
    can never match, or (worse, and the reason this exists) one whose patterns
    are loose enough to pass over a graph the calculator will not read.

    Run against the live capture, with the real `grep`, rather than a
    hand-written expected file: the emitted bytes have no trailing newline and
    a whole-file comparison would fail on a byte nobody added.
    """
    text = _dockerfile_text()
    graph = tmp_path / "graph.pbtxt"
    graph.write_text(LIVE_RERANK_GRAPH.read_text())

    injected = subprocess.run(
        [
            sys.executable,
            str(INJECTOR),
            str(graph),
            "--max-allowed-chunks",
            _resolve_guard_flag(text, "--max-allowed-chunks"),
            "--max-position-embeddings",
            _resolve_guard_flag(text, "--max-position-embeddings"),
        ],
        capture_output=True,
        text=True,
    )
    assert injected.returncode == 0, injected.stderr

    patterns = _guard_verification_patterns(text)
    assert len(patterns) == len(GUARD_FIELDS), (
        f"expected one verification pattern per guard field, got {patterns}"
    )
    for pattern in patterns:
        found = subprocess.run(["grep", "-qE", pattern, str(graph)])
        assert found.returncode == 0, (
            f"the build greps for {pattern!r}, which matches nothing in the "
            f"graph the injector produced:\n{graph.read_text()}"
        )
