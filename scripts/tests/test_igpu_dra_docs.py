"""Tripwire: phase05's README must describe DRA, not the retired device plugin.

`patches/phase05-mini-config/README.md` drifted by a full API generation: its
"What This Does" step 4 said the Intel GPU Device Plugin was deployed "to
expose `gpu.intel.com/i915` as a schedulable resource" and pointed at
`apps/intel-gpu-plugin/`. Neither is true — that path does not exist, the
extended resource does not exist, and what is actually deployed is Intel's
DRA resource driver at `apps/intel-gpu-driver/`, consumed via a
`ResourceClaim`/`ResourceClaimTemplate` against DeviceClass `gpu.intel.com`.
The drift survived because the README's own *Verify* section was already
DRA-correct — only the prose above it lagged.

This also guards a second, general property: every file added to
`docs/runbooks/frank-gotchas/` must get a row in that directory's own
`README.md` index, or it is undiscoverable to anyone who doesn't already know
its filename.
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
PHASE05_README = REPO / "patches" / "phase05-mini-config" / "README.md"
GOTCHAS_DIR = REPO / "docs" / "runbooks" / "frank-gotchas"


def _phase05_text() -> str:
    return PHASE05_README.read_text(encoding="utf-8")


def test_phase05_readme_does_not_reference_the_retired_device_plugin_path():
    text = _phase05_text()
    assert "apps/intel-gpu-plugin" not in text, (
        "phase05 README still points at apps/intel-gpu-plugin/, which does "
        "not exist — the real app is apps/intel-gpu-driver/"
    )


def test_phase05_readme_does_not_present_extended_resource_as_schedulable():
    text = _phase05_text()
    # The device-plugin-era claim was that gpu.intel.com/i915 becomes a
    # schedulable extended resource. That resource does not exist under DRA
    # (resource.k8s.io/v1) — querying node.status.allocatable for it returns
    # nothing. Forbid the "expose ... as a schedulable resource" framing.
    forbidden = re.compile(
        r"gpu\.intel\.com/i915[^\n]*schedulable|schedulable[^\n]*gpu\.intel\.com/i915",
        re.IGNORECASE,
    )
    assert not forbidden.search(text), (
        "phase05 README still presents gpu.intel.com/i915 as a schedulable "
        "extended resource — that resource does not exist under DRA"
    )


# Words that mark a mention of the device plugin as historical rather than
# operative. Deliberately a small, boring list: the point is that SOME
# explicit disclaimer sits next to the name, not that a particular sentence
# was written.
_RETIRED_MARKERS = (
    "not deployed",
    "not what",
    "no longer",
    "retired",
    "replaced",
    "superseded",
    "was corrected",
    "until this document",
    "pre-dra",
)


def test_phase05_readme_may_name_the_device_plugin_only_as_retired():
    """The README is ALLOWED to say "Intel GPU Device Plugin" — it must not
    present it as what is deployed.

    The first version of this guard was `"Device Plugin" not in text`, which
    forbade the document from ever naming the thing it used to describe. The
    predictable result was vagueness: the correction talked about "the retired
    per-node device-exposure model at a since-removed app path", which is
    accurate, unsearchable, and useless to the reader who arrived here holding
    a device-plugin tutorial. A doc that cannot name the wrong answer cannot
    tell you that you are holding it.

    So the rule is contextual: every PARAGRAPH mentioning the device plugin
    must also mark it as not-what-runs-here.
    """
    text = _phase05_text()
    offenders = []
    for para in re.split(r"\n\s*\n", text):
        if not re.search(r"device plugin", para, re.IGNORECASE):
            continue
        lowered = para.lower()
        if not any(marker in lowered for marker in _RETIRED_MARKERS):
            offenders.append(" ".join(para.split())[:120])
    assert not offenders, (
        "phase05 README mentions the Intel GPU Device Plugin without marking "
        "it as retired/not-deployed in the same paragraph — a reader lands on "
        "the device-plugin model believing it is what runs on Frank. Offending "
        f"paragraph(s): {offenders}"
    )


def test_phase05_readme_names_the_device_plugin_it_replaced():
    """The correction must be findable by someone searching for the wrong thing.

    Whoever arrives here arrives with device-plugin material in hand — that is
    exactly how the drift got into this file in the first place. Naming the
    superseded model (with the disclaimer the previous test enforces) is what
    turns this README into the answer rather than a document that quietly
    disagrees with the tutorial they are following.
    """
    text = _phase05_text()
    assert re.search(r"device plugin", text, re.IGNORECASE), (
        "phase05 README no longer names the Intel GPU Device Plugin at all — "
        "the pre-DRA model it was corrected FROM. Say what is not deployed, "
        "not just what is"
    )


def test_phase05_readme_mentions_resourceclaim():
    text = _phase05_text()
    assert "ResourceClaim" in text, (
        "phase05 README must document the ResourceClaim/ResourceClaimTemplate "
        "idiom that replaces the extended-resource claim it used to describe"
    )


def test_phase05_readme_points_at_the_real_driver_app():
    text = _phase05_text()
    assert "apps/intel-gpu-driver" in text, (
        "phase05 README should point readers at the app that is actually "
        "deployed, apps/intel-gpu-driver/"
    )


def test_every_gotchas_file_has_an_index_row():
    """General guard, not just for the new file: every *.md in
    docs/runbooks/frank-gotchas/ (other than the index itself) must have a
    row in README.md, or it's invisible to anyone browsing the index."""
    index_text = (GOTCHAS_DIR / "README.md").read_text(encoding="utf-8")
    md_files = sorted(
        p.name for p in GOTCHAS_DIR.glob("*.md") if p.name != "README.md"
    )
    assert md_files, "expected at least one gotchas topic file"
    missing = [name for name in md_files if f"({name})" not in index_text]
    assert not missing, (
        f"docs/runbooks/frank-gotchas/README.md is missing an index row for: "
        f"{missing}"
    )


def test_igpu_dra_topic_file_exists():
    assert (GOTCHAS_DIR / "igpu-dra.md").exists(), (
        "expected docs/runbooks/frank-gotchas/igpu-dra.md to document the "
        "capacity.memory=0, render-node-permissions, CDI-no-auto-inject and "
        "OVMS model-acquisition gotchas"
    )
