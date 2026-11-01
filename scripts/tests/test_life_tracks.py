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
