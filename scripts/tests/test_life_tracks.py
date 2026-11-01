"""OS upgrade tracks are matrix-driven and one minor per step (spec R19, Part 4)."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import life_tracks  # noqa: E402

MATRIX = yaml.safe_load((ROOT / "versions/support-matrix.yaml").read_text())


def _kinds(steps):
    return [(s.kind, s.to_minor) for s in steps]


def test_frank_track_alternates_talos_and_kubernetes():
    steps = life_tracks.next_steps(
        {"cluster": "frank", "talos": "1.12.6", "kubernetes": "1.35.3"},
        {"talos": "1.14.x", "kubernetes": "1.37.x"},
        MATRIX,
    )
    assert _kinds(steps) == [
        ("talos", "1.13"),
        ("kubernetes", "1.36"),
        ("talos", "1.14"),
        ("kubernetes", "1.37"),
    ]
    assert [s.position for s in steps] == [1, 2, 3, 4]


def test_never_two_kubernetes_minors_in_one_step():
    steps = life_tracks.next_steps(
        {"cluster": "frank", "talos": "1.12.6", "kubernetes": "1.35.3"},
        {"talos": "1.14.x", "kubernetes": "1.37.x"},
        MATRIX,
    )
    prev = (1, 35)
    for s in steps:
        if s.kind == "kubernetes":
            minor = tuple(int(x) for x in s.to_minor.split("."))
            assert minor == (prev[0], prev[1] + 1)
            prev = minor


def test_kubernetes_steps_are_one_way_and_talos_rollback_is_per_cluster():
    frank = life_tracks.next_steps(
        {"cluster": "frank", "talos": "1.12.6", "kubernetes": "1.35.3"},
        {"talos": "1.13.x", "kubernetes": "1.36.x"},
        MATRIX,
    )
    hop = life_tracks.next_steps(
        {"cluster": "hop", "talos": "1.12.5", "kubernetes": "1.34.1"},
        {"talos": "1.13.x", "kubernetes": "1.35.x"},
        MATRIX,
    )
    for s in frank + hop:
        if s.kind == "kubernetes":
            assert s.one_way is True and s.rollback == "one-way"
        else:
            assert s.one_way is False
    assert {s.rollback for s in frank if s.kind == "talos"} == {"omni-revert"}
    assert {s.rollback for s in hop if s.kind == "talos"} == {"talosctl-rollback"}


def test_kubernetes_goes_first_when_the_next_talos_does_not_support_it():
    """Matrix-driven, not hard-coded: shrink 1.13's window and Hop moves Kubernetes first."""
    matrix = {"talos": {"1.12": ["1.33", "1.34", "1.35"], "1.13": ["1.35", "1.36"]}}
    steps = life_tracks.next_steps(
        {"cluster": "hop", "talos": "1.12.5", "kubernetes": "1.34.1"},
        {"talos": "1.13.x", "kubernetes": "1.35.x"},
        matrix,
    )
    assert _kinds(steps) == [("kubernetes", "1.35"), ("talos", "1.13")]


def test_real_matrix_lets_hop_take_talos_first():
    """Talos 1.13 supports Kubernetes 1.34 (docs), so no Kubernetes step is forced first."""
    steps = life_tracks.next_steps(
        {"cluster": "hop", "talos": "1.12.5", "kubernetes": "1.34.1"},
        {"talos": "1.13.x", "kubernetes": "1.35.x"},
        MATRIX,
    )
    assert _kinds(steps)[0] == ("talos", "1.13")


def test_every_step_stays_inside_the_support_window():
    steps = life_tracks.next_steps(
        {"cluster": "frank", "talos": "1.12.6", "kubernetes": "1.35.3"},
        {"talos": "1.14.x", "kubernetes": "1.37.x"},
        MATRIX,
    )
    for s in steps:
        assert s.k8s_minor in MATRIX["talos"][s.talos_minor], s


def test_already_at_target_has_no_steps():
    assert not life_tracks.next_steps(
        {"cluster": "frank", "talos": "1.12.6", "kubernetes": "1.35.3"},
        {"talos": "1.12.6", "kubernetes": "1.35.3"},
        MATRIX,
    )


def test_unreachable_target_raises():
    with pytest.raises(ValueError):
        life_tracks.next_steps(
            {"cluster": "frank", "talos": "1.12.6", "kubernetes": "1.35.3"},
            {"talos": "1.14.x", "kubernetes": "1.37.x"},
            {"talos": {"1.12": ["1.35"], "1.13": ["1.37"], "1.14": ["1.37"]}},
        )


def test_matrix_shape_and_sources():
    text = (ROOT / "versions/support-matrix.yaml").read_text()
    assert text.count("docs.siderolabs.com/talos/") >= 3, "cite the Talos support-matrix URLs"
    for minor in ("1.12", "1.13", "1.14"):
        assert minor in MATRIX["talos"]
        assert all(len(k.split(".")) == 2 for k in MATRIX["talos"][minor])
    assert "1.37" in MATRIX["talos"]["1.14"] and "1.36" in MATRIX["talos"]["1.13"]
    # The declared Frank/Hop versions are covered by the matrix.
    for f in ("frank", "hop"):
        v = yaml.safe_load((ROOT / f"versions/{f}.yaml").read_text())
        tm = ".".join(str(v["talos"]).split(".")[:2])
        km = ".".join(str(v["kubernetes"]).split(".")[:2])
        assert km in MATRIX["talos"][tm], f


# --- p6-r8 / p6-r9: patch moves, partial moves, bounds ---------------------------------
def _go(cur_t, cur_k, tgt_t, tgt_k, cluster="frank", matrix=MATRIX):
    return life_tracks.next_steps(
        {"cluster": cluster, "talos": cur_t, "kubernetes": cur_k},
        {"talos": tgt_t, "kubernetes": tgt_k}, matrix)


def test_patch_only_talos_step_is_not_one_way():
    steps = _go("1.12.6", "1.35.3", "1.12.8", "1.35.3")
    assert [(s.kind, s.to_minor, s.to, s.one_way) for s in steps] == [("talos", "1.12", "1.12.8", False)]
    assert steps[0].rollback == "omni-revert"


def test_patch_only_kubernetes_step_is_not_one_way():
    steps = _go("1.12.6", "1.35.3", "1.12.6", "1.35.5")
    assert [(s.kind, s.to_minor, s.to, s.one_way) for s in steps] == [("kubernetes", "1.35", "1.35.5", False)]
    assert steps[0].rollback != "one-way"


def test_talos_only_and_kubernetes_only_minor_moves():
    t = _go("1.12.6", "1.35.3", "1.13.x", "1.35.3")
    assert _kinds(t) == [("talos", "1.13")]
    k = _go("1.13.1", "1.35.3", "1.13.1", "1.36.x")
    assert _kinds(k) == [("kubernetes", "1.36")]
    with pytest.raises(ValueError):  # 1.36 is outside Talos 1.12's window
        _go("1.12.6", "1.35.3", "1.12.6", "1.36.x")


def test_x_at_the_current_minor_is_no_step():
    assert _go("1.12.6", "1.35.3", "1.12.x", "1.35.x") == []


def test_lower_patch_target_is_no_step():
    assert _go("1.12.6", "1.35.3", "1.12.2", "1.35.1") == []


def test_track_longer_than_the_bound_raises():
    matrix = {"talos": {"1.12": [f"1.{n}" for n in range(35, 120)]}}
    with pytest.raises(ValueError, match="converge"):
        _go("1.12.6", "1.35.3", "1.12.x", "1.100.x", matrix=matrix)
