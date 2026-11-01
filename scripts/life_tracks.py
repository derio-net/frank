"""OS upgrade tracks: the ordered single-minor steps from declared to target versions.

Matrix-driven (versions/support-matrix.yaml), never hard-coded. One Talos minor or
one Kubernetes minor per step; a step must leave the cluster inside the Talos <->
Kubernetes support window. The console's internal/tracks implements the same rules;
keep them in step (spec R19, Part 4).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    cluster: str
    kind: str  # talos | kubernetes
    position: int
    to_minor: str  # the minor this step lands on, e.g. "1.13"
    to: str  # the target string for the step ("1.13.x", or the exact target on the target minor)
    talos_minor: str  # Talos minor once the step is applied
    k8s_minor: str  # Kubernetes minor once the step is applied
    one_way: bool
    rollback: str  # omni-revert | talosctl-rollback | one-way


def _minor(v: str) -> tuple[int, int]:
    parts = str(v).split(".")
    return int(parts[0]), int(parts[1])


def _s(m: tuple[int, int]) -> str:
    return f"{m[0]}.{m[1]}"


def _supported(matrix: dict, talos: tuple[int, int], k8s: tuple[int, int]) -> bool:
    return _s(k8s) in [str(x) for x in matrix["talos"].get(_s(talos), [])]


def next_steps(cluster_versions: dict, target: dict, matrix: dict) -> list[Step]:
    cluster = cluster_versions["cluster"]
    talos, k8s = _minor(cluster_versions["talos"]), _minor(cluster_versions["kubernetes"])
    t_goal, k_goal = _minor(target["talos"]), _minor(target["kubernetes"])
    talos_rollback = "talosctl-rollback" if cluster == "hop" else "omni-revert"
    steps: list[Step] = []

    def add(kind: str, to: tuple[int, int]) -> None:
        nonlocal talos, k8s
        goal = t_goal if kind == "talos" else k_goal
        exact = str(target[kind if kind == "talos" else "kubernetes"])
        minor_move = to != (talos if kind == "talos" else k8s)
        label = exact if to == goal else f"{_s(to)}.x"
        if kind == "talos":
            talos = to
        else:
            k8s = to
        steps.append(Step(
            cluster=cluster, kind=kind, position=len(steps) + 1, to_minor=_s(to), to=label,
            talos_minor=_s(talos), k8s_minor=_s(k8s),
            one_way=minor_move and kind == "kubernetes",
            rollback=talos_rollback if kind == "talos" else ("one-way" if minor_move else "forward-fix"),
        ))

    # Patch-level move inside the current minor (target patch differs): one step.
    prefer_k = False
    for _ in range(40):
        if talos >= t_goal and k8s >= k_goal:
            break
        nt = (talos[0], talos[1] + 1)
        nk = (k8s[0], k8s[1] + 1)
        can_t = talos < t_goal and _supported(matrix, nt, k8s)
        can_k = k8s < k_goal and _supported(matrix, talos, nk)
        if can_k and (prefer_k or not can_t):
            add("kubernetes", nk)
            prefer_k = False
        elif can_t:
            add("talos", nt)
            prefer_k = True
        else:
            raise ValueError(
                f"no step keeps Talos {_s(talos)} / Kubernetes {_s(k8s)} inside the support "
                f"window toward Talos {_s(t_goal)} / Kubernetes {_s(k_goal)}"
            )
    else:
        raise ValueError("track did not converge")

    # Patch-only move at the current minor: only when the target patch is numerically greater.
    for kind, cur in (("talos", talos), ("kubernetes", k8s)):
        if any(s.kind == kind for s in steps):
            continue
        want = str(target[kind])
        if want.endswith(".x") or not _patch_greater(want, cluster_versions[kind]):
            continue
        add(kind, cur)
    return steps


def _patch_greater(want: str, have: str) -> bool:
    w = [int(x) for x in str(want).split(".")[:3]]
    h = [int(x) for x in str(have).split(".")[:3]]
    return len(w) == 3 and w > h
