"""Tripwires for phase 5 of the igpu-embedding-rerank plan.

Phase 5 is the MANUAL phase: it is executed by a person reading step text, so
its steps are the only place several failure modes are caught at all. Nothing
else in the repo can assert them — there is no manifest for "check the package
is public before you conclude the sync is broken" — which is exactly why the
step text is worth guarding.

Each assertion below corresponds to something that, if the step were quietly
reworded away, would waste an operator's time or produce a number that is
wrong in a way the number itself cannot show:

1. **GHCR first-publish visibility.** The package does not exist yet, and
   GHCR creates it PRIVATE on first push from Actions. The pod carries no
   imagePullSecret, so first sync is an ImagePullBackOff that NO manifest
   change fixes — and it reads exactly like a broken build.
2. **`/v1/config` before trusting Ready.** The runtime gate proved
   `/v2/health/ready` is server-level, but only against a CLASSIC model. The
   per-model endpoint was never exercised against a MediaPipe-graph servable,
   which is what this deployment serves. If it answers 200 unconditionally,
   the silent-green failure the probes exist to prevent is back.
3. **The probes gate exactly two servables, by name.** A third would be
   ungated, and the pod would go Ready with it dead.
4. **The CPU control arm is a committed, hand-applied manifest.** Improvising
   it at measurement time is where "no ResourceClaim" and "seed the CPU
   repository" get forgotten — and both failures produce a plausible number.
5. **The measurement's scope.** One pod, hostname-pinned to one control-plane
   node. Reported without that, it becomes a general claim about Frank.
"""
from __future__ import annotations

import pathlib

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]

# Resolve the plan in EITHER location. `fr archive` git-mv's a finished plan from
# docs/superpowers/plans/ to docs/superpowers/implemented/plans/, which would
# otherwise turn every assertion in this file red the moment the plan shipped --
# a guard that breaks on success is worse than no guard.
_PLAN_REL = "2026-08-02--infer--igpu-embedding-rerank/05.yaml"
_CANDIDATES = [
    REPO / "docs/superpowers/plans" / _PLAN_REL,
    REPO / "docs/superpowers/implemented/plans" / _PLAN_REL,
    REPO / "docs/superpowers/archived-plans" / _PLAN_REL,
]
PHASE5 = next((c for c in _CANDIDATES if c.is_file()), _CANDIDATES[0])


def _phase() -> dict:
    doc = yaml.safe_load(PHASE5.read_text(encoding="utf-8"))
    assert doc["phase"]["number"] == 5, doc["phase"]
    return doc


def _steps() -> list[tuple[str, str]]:
    """Step texts with whitespace normalised.

    The plan stores them as wrapped block scalars, so any phrase long enough
    to be worth asserting on is split across a newline in the file and would
    never match a substring check taken literally.
    """
    out = []
    for task in _phase()["tasks"]:
        for step in task["steps"]:
            out.append((step["id"], " ".join(step["text"].split())))
    return out


def _text() -> str:
    return "\n".join(text for _id, text in _steps())


def test_every_step_has_a_state_entry():
    """A step with no state row cannot be ticked and silently drops out."""
    declared = {sid for sid, _ in _steps()}
    tracked = set(_phase()["state"]["steps"])
    assert declared == tracked, (
        f"step ids and state rows disagree: only-in-steps={sorted(declared - tracked)}, "
        f"only-in-state={sorted(tracked - declared)}"
    )


def test_package_visibility_is_settled_before_the_sync_check():
    """Order matters: this is the step that stops an hour of debugging ArgoCD."""
    steps = _steps()
    visibility = [i for i, (_id, t) in enumerate(steps) if "visibility" in t.lower()]
    assert visibility, (
        "phase 5 never tells the operator to make the first-published GHCR "
        "package pullable — it is created PRIVATE, the pod has no "
        "imagePullSecret, and the resulting ImagePullBackOff cannot be fixed "
        "by any change to this repo"
    )
    sync = [i for i, (_id, t) in enumerate(steps) if "ArgoCD synced" in t]
    assert sync, "phase 5 no longer has a sync-verification step"
    assert min(visibility) < min(sync), (
        "the package-visibility step must come BEFORE the sync check, or the "
        "operator debugs a sync that was never the problem"
    )
    assert "imagePullSecret" in _text(), (
        "name the alternative (a pull secret) — 'make it public' is a decision, "
        "and a decision needs its other option written down"
    )


def test_v1_config_is_checked_before_ready_is_trusted():
    text = _text()
    assert "/v1/config" in text, "phase 5 must check /v1/config, not just Ready"
    lowered = text.lower()
    assert "mediapipe" in lowered, (
        "phase 5 must state the UNVERIFIED assumption: /v2/models/<name>/ready "
        "was proven against a CLASSIC model, never against a MediaPipe-graph "
        "servable, which is what embeddings_ov/rerank_ov emit. If it returns "
        "200 unconditionally the probes are decorative and only /v1/config "
        "would show it"
    )


def test_the_two_servable_probe_limit_is_written_down():
    text = _text()
    assert "bge-m3" in text and "bge-reranker-v2-m3" in text, (
        "name both gated servables — the startup/readiness split covers "
        "exactly these two, BY NAME"
    )
    lowered = text.lower()
    assert "third" in lowered and "ungated" in lowered, (
        "phase 5 must say that a THIRD servable would be UNGATED: the pod "
        "would go Ready with it dead, which is the same silent-green failure "
        "the probe design exists to prevent, one model down"
    )


def test_the_cpu_control_arm_points_at_the_committed_manifest():
    text = _text()
    assert "cpu-arm-pod.yaml" in text, (
        "phase 5 must apply the committed CPU-arm manifest rather than "
        "improvising a pod: the three properties that make the comparison "
        "valid (no ResourceClaim, CPU repository, same node) are exactly the "
        "ones a hand-typed pod loses"
    )
    assert "ResourceClaim" in text, "the 'no ResourceClaim' property must be stated"


def test_the_measurement_scope_is_reported_with_the_number():
    lowered = _text().lower()
    assert "kubernetes.io/hostname" in lowered or "hostname-pinned" in lowered, (
        "phase 5 must state that the number comes from a hostname-pinned pod"
    )
    assert "rescheduled" in lowered, (
        "phase 5 must say the figure is NOT what a rescheduled or scaled "
        "deployment would see — the pin is what makes it repeatable, and "
        "dropping it invalidates the number rather than generalising it"
    )
