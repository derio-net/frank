"""Every dependency resolves to exactly one update path (spec R5)."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import life_policy  # noqa: E402
import render_all_images  # noqa: E402

pytestmark = pytest.mark.slow
PATHS = {"auto-merge", "batch-approve", "session", "operator-runbook"}
UPDATE_TYPES = ("patch", "minor", "major")
FIX = ROOT / "scripts/tests/fixtures/life"
POLICY = yaml.safe_load((ROOT / "update-policy.yaml").read_text())


def _apps():
    """(cluster, name) for every Application in both root charts (shared enumeration)."""
    return [tuple(k.split("/")) for k in life_policy.app_keys()]


FACTS = yaml.safe_load((FIX / "app-facts.yaml").read_text())


def test_schema_and_every_path_is_one_of_the_four():
    assert POLICY["version"] == 1
    assert set(POLICY["defaults"]) == set(UPDATE_TYPES)
    assert set(POLICY["defaults"].values()) <= PATHS
    for rule in POLICY["rules"]:
        assert rule["path"] in PATHS, rule
        assert rule["reason"].strip(), rule
        assert len(set(rule["match"]) & {"app", "image", "chart", "dep"}) == 1, rule


def test_every_application_resolves_for_every_update_type():
    for cluster, name in _apps():
        for ut in UPDATE_TYPES:
            assert life_policy.resolve({"app": f"{cluster}/{name}"}, ut) in PATHS


def test_facts_cover_exactly_the_applications():
    assert set(FACTS["apps"]) == {f"{c}/{n}" for c, n in _apps()}


def test_every_rendered_image_resolves():
    images = [l.strip() for l in (FIX / "rendered-images.txt").read_text().splitlines()
              if l.strip() and not l.startswith("#")]
    owned = {i for a in FACTS["apps"].values() for i in a["images"]}
    assert set(images) <= owned, sorted(set(images) - owned)
    for image in images:
        for ut in UPDATE_TYPES:
            assert life_policy.resolve({"image": image}, ut) in PATHS


def test_os_and_omni_dependencies_resolve():
    for dep in ("talos:frank", "kubernetes:frank", "talos:hop", "kubernetes:hop"):
        for ut in UPDATE_TYPES:
            assert life_policy.resolve({"dep": dep}, ut) == "session"
    for ut in UPDATE_TYPES:
        assert life_policy.resolve({"dep": "omni"}, ut) == "operator-runbook"


def test_stateful_and_rollout_apps_are_session_for_all_update_types():
    must = {"frank/paperclip", "frank/paperclip-db", "frank/authentik", "frank/gitea", "frank/longhorn"}
    detected = {k for k, v in FACTS["apps"].items() if v["stateful"] or v["rollout"]}
    assert must <= detected, must - detected
    for app in sorted(detected | must):
        for ut in UPDATE_TYPES:
            assert life_policy.resolve({"app": app}, ut) == "session", (app, ut)


def test_stateful_apps_images_are_session_too():
    for app, facts in FACTS["apps"].items():
        if not (facts["stateful"] or facts["rollout"]):
            continue
        for image in facts["images"]:
            assert life_policy.resolve({"image": image}, "patch") == "session", (app, image)


def test_facts_match_git_resident_rendering():
    """A stale facts file must fail: re-detect PVC/Rollout offline for git-resident sources."""
    seen = life_policy.detect_offline()
    for app, (stateful, rollout) in seen.items():
        f = FACTS["apps"][app]
        assert (not stateful) or f["stateful"], app
        assert (not rollout) or f["rollout"], app


def test_the_tools_that_update_the_cluster_never_update_themselves_unattended():
    for image in ("renovate/renovate:44.198.3@sha256:" + "0" * 64,
                  "ghcr.io/derio-net/cluster-update-fr:1.2.3",
                  "ghcr.io/derio-net/upgrade-session:1.2.3"):
        for ut in UPDATE_TYPES:
            assert life_policy.resolve({"image": image}, ut) == "session", (image, ut)
    cfg = life_policy.renovate_config()
    pinned = [r for r in cfg["packageRules"] if "renovate/renovate" in r.get("matchPackageNames", [])]
    assert pinned and all(r["labels"] == ["path:session"] for r in pinned)


def test_stateful_apps_charts_are_session_too():
    for app, facts in FACTS["apps"].items():
        if not (facts["stateful"] or facts["rollout"]):
            continue
        for chart in facts["charts"]:
            for ut in UPDATE_TYPES:
                assert life_policy.resolve({"chart": chart}, ut) == "session", (app, chart, ut)


def test_facts_have_not_drifted_from_a_full_render():
    """Regenerates the facts (remote charts included) and compares: a stale fixture fails.

    Needs the network for remote charts. CI sets CI=true and must run it; locally an
    unreachable chart repository skips with the reason instead.
    """
    import os

    try:
        fresh = life_policy.collect_facts()
    except Exception as exc:  # noqa: BLE001 - network/tooling failure, not drift
        if os.environ.get("CI") == "true":
            raise
        pytest.skip(f"cannot render remote charts here: {exc}")
    assert fresh == FACTS["apps"], "app-facts.yaml is stale: run scripts/life_policy.py --emit-facts"
