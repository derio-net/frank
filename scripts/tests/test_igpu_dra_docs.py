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


# --------------------------------------------------------------------------
# frank#793 — the rerank batch guard must be documented where an operator
# looking at an OOM-killed retrieval pod will actually find it.
#
# The failure this documents is not "a big request kills the server", which is
# how the issue framed it and what a reader will arrive believing. Measurement
# reversed that: cost is near-quadratic in document LENGTH and only linear in
# document COUNT, and memory is never released, so the resident floor ratchets
# to the high-water of the largest call the container has ever served. The
# same request therefore succeeds on a fresh pod and dies later. A gotcha that
# records only the cap values teaches the wrong model of the bug and leaves
# the reader unable to explain why a restart fixes it.
#
# Every clause below is asserted on MECHANISM WORDS with alternations, not on
# a sentence to copy: the point is that the document says the thing, in
# whatever words its author chose, not that it matches prose written here.
# --------------------------------------------------------------------------

IGPU_DRA = GOTCHAS_DIR / "igpu-dra.md"
HOT_FILE = REPO / "agents" / "rules" / "frank-gotchas.md"


def _igpu_dra_text() -> str:
    return IGPU_DRA.read_text(encoding="utf-8")


def _rerank_guard_section() -> str:
    """The `##` section(s) of igpu-dra.md documenting the rerank batch guard,
    flattened to a single line.

    Scoped to the section rather than the whole file for the same reason the
    10Gi provenance test scopes to one resources block: a whole-file scan lets
    a future edit satisfy a clause with a sentence four screens away, which is
    documentation nobody reading about the cap will ever find.

    Flattened because this file is hard-wrapped at about 76 columns, so any
    clause spanning two ideas — "`--max_doc_length`" and "not a batch cap" —
    lands on one line or two depending on where the author's sentence happened
    to break. A pattern that only matches the one-line case passes or fails on
    typography rather than on content, which is a test that can pass for the
    wrong reason and fail for no reason at all.
    """
    text = IGPU_DRA.read_text(encoding="utf-8")
    sections = re.split(r"\n(?=## )", text)
    hits = [s for s in sections if "max_allowed_chunks" in s]
    assert hits, (
        "docs/runbooks/frank-gotchas/igpu-dra.md has no section documenting "
        "`max_allowed_chunks` — the rerank batch guard shipped with no prose "
        "an operator can find from an OOM-killed retrieval pod"
    )
    return " ".join("\n".join(hits).split())


# (clause name, pattern, what its absence costs the reader). Patterns run
# against the FLATTENED section, so `.{0,N}` windows are character distances
# in the prose, not "same source line".
_RERANK_GUARD_CLAUSES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "both bounds, named with their shipped values",
        re.compile(
            r"max_allowed_chunks\D{0,80}64\b.{0,200}max_position_embeddings\D{0,80}640\b"
            r"|max_position_embeddings\D{0,80}640\b.{0,200}max_allowed_chunks\D{0,80}64\b"
        ),
        "a bare 64 and 640 read as arbitrary. Name each field with its value, "
        "so a reader retuning one knows which term it bounds.",
    ),
    (
        "the tensor is batch x LONGEST-document tokens",
        re.compile(
            r"(?:batch|B)\W{0,3}(?:[x×*]|by)\W{0,3}T\b"
            r"|longest\b.{0,40}\bdocument",
            re.IGNORECASE,
        ),
        "without it, a document-count cap looks sufficient — and it is not: "
        "T comes from the longest document in the request and every other "
        "document is padded up to it.",
    ),
    (
        "cost is quadratic in T, linear in count",
        re.compile(r"quadratic|T\s*[x×*]\s*T|\^\s*1\.78", re.IGNORECASE),
        "this is what makes max_position_embeddings the PRIMARY control and "
        "max_allowed_chunks the secondary one — the reverse of the issue's "
        "framing. Say which lever moves the cost.",
    ),
    (
        "upstream's default is 10000 and the exporter never emits it",
        re.compile(r"10000.{0,400}export_model\.py|export_model\.py.{0,400}10000"),
        "the guard existed upstream all along, unset. A reader who does not "
        "know that will look for a feature to add rather than a default to "
        "override.",
    ),
    (
        "--max_doc_length is NOT a batch cap",
        re.compile(
            r"max_doc_length.{0,200}\b(?:not|never|no)\b"
            r"|\b(?:not|never|no)\b.{0,200}max_doc_length",
            re.IGNORECASE,
        ),
        "it is the obvious-looking flag and it is the wrong one: it sets the "
        "exported tokenizer's model_max_length and never reaches graph.pbtxt.",
    ),
    (
        "the refusal is a 500, not a 4xx",
        re.compile(r"\b500\b.{0,300}\b4xx\b|\b4xx\b.{0,300}\b500\b"),
        "the issue asked for 4xx. Upstream raises std::runtime_error and "
        "Process() catches it into absl::InternalError, so a test asserting "
        "4xx fails on correct behaviour.",
    ),
    (
        "memory is never released — the floor ratchets",
        re.compile(
            r"ratchet|high[- ]water|never released|not released"
            r"|does not (?:fall|drop|return)",
            re.IGNORECASE,
        ),
        "this is the actual bug. memory.current after a large call equals "
        "memory.peak and stays there for the life of the container.",
    ),
    (
        "the measured floors, idle and after a large call",
        re.compile(r"2\.21\b.{0,300}4\.90\b|4\.90\b.{0,300}2\.21\b"),
        "the ratchet claim needs its evidence: 2.21 GiB idle, 4.90 GiB "
        "resident after a single large call, with no return.",
    ),
    (
        "the ratchet is why the failure is intermittent",
        re.compile(
            r"intermittent|fresh(?:ly)?[- ]restart|after a restart",
            re.IGNORECASE,
        ),
        "a single request size explains neither 'works, then doesn't' nor "
        "restarts accumulating over a week of light use. The ratchet does.",
    ),
    (
        "restarting the pod resets the floor",
        re.compile(
            r"restart\w*\b.{0,160}(?:reset|clear|floor|idle)"
            r"|(?:reset|clears)\b.{0,160}restart",
            re.IGNORECASE,
        ),
        "it is what an operator reaches for first, and it genuinely works. "
        "Say so, rather than leaving it to be rediscovered.",
    ),
    (
        "the instrument is memory.peak, not a metrics scrape",
        re.compile(r"memory\.peak", re.IGNORECASE),
        "these transients last 0.1-2.5s and vmagent scrapes at 20s, so the "
        "cluster metric cannot see them. Naming the instrument is the "
        "difference between a reproducible measurement and a guess.",
    ),
]


def test_igpu_dra_documents_the_rerank_batch_guard_mechanism():
    section = _rerank_guard_section()
    missing = [
        f"{name} — {why}"
        for name, pattern, why in _RERANK_GUARD_CLAUSES
        if not pattern.search(section)
    ]
    assert not missing, (
        "the rerank batch guard section of "
        "docs/runbooks/frank-gotchas/igpu-dra.md is missing:\n  - "
        + "\n  - ".join(missing)
    )


def test_frank_gotchas_hot_file_carries_the_rerank_guard_one_liner():
    """One-liner in the hot file, prose in the per-topic file.

    The hot file is loaded for every session in this repo; the topic file is
    read on demand. A gotcha that exists only in the topic file is invisible
    to an agent that does not already know to open it, and one that exists
    only in the hot file has nowhere to put the measurement. The convention is
    both, and this asserts the half that is easiest to forget.
    """
    text = HOT_FILE.read_text(encoding="utf-8")
    sections = re.split(r"\n(?=### )", text)
    igpu = [s for s in sections if s.startswith("### Intel iGPU / DRA")]
    assert igpu, "agents/rules/frank-gotchas.md has no `Intel iGPU / DRA` section"
    body = igpu[0]
    assert "max_allowed_chunks" in body, (
        "the `Intel iGPU / DRA` section of agents/rules/frank-gotchas.md does "
        "not mention the rerank batch guard. One line here, prose in "
        "docs/runbooks/frank-gotchas/igpu-dra.md — that is this repo's "
        "one-liner-here / prose-there convention"
    )
    line = next(ln for ln in body.splitlines() if "max_allowed_chunks" in ln)
    assert re.search(r"ratchet|high[- ]water|never released", line, re.IGNORECASE), (
        "the hot-file one-liner records the cap but not the mechanism that "
        "makes the failure intermittent. A one-liner that says only 'we set a "
        "cap' leaves the next reader without the one fact that explains why a "
        "restart fixes it: " + line.strip()[:160]
    )
