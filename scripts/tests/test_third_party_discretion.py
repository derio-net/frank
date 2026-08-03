"""Tripwire: artefacts built for the private consumer must not leak it.

This repo is PUBLIC. The work in `apps/ovms-retrieval/` (frank#748, the iGPU
retrieval tier) and the `gbrain` sidecar in `apps/hermes-agent-shell/`
(frank#759, where that client's CLI keeps its vectors) were both requested by a
repo that is not public. `agents/rules/third-party-privacy.md` plus the design
specs' own "Discretion" sections set the line: name no consumer repo, product or
corpus; reproduce no benchmark queries, document titles or corpus statistics;
refer to the requester only as an external client. The first spec called a
breach "a blocking finding" — and then, in its Test Plan, breached it itself.
Prose that asks reviewers to be vigilant is not a control; this file is.

**`SCANNED_PATHS` is the whole control surface.** The checks below are decent
patterns applied to exactly the files listed there and no others, so a follow-on
plan for the same requester that does not append its own paths gets a green run
that says nothing about its own artefacts. That happened once already: #759's
branch added a spec, a plan, a journal, a README section, three manifests and a
test file, and the list still named only #748's. Appending is the maintenance
this file needs; forgetting it is silent.

## How it is written, and why that shape

**It must not itself contain what it forbids.** A denylist of the private
strings would publish them in the repo, permanently, in a file whose whole
purpose is that they never appear — and it would be worthless the moment the
next leak used a word nobody predicted. So the checks are almost entirely
patterns for the SHAPE of a disclosure, not the disclosure:

  * a retrieval-quality FIGURE — a recall/nDCG/MRR metric name followed by a
    comparator and a number. Naming the metric is fine and often necessary;
    quoting the requester's target or achieved score is a corpus statistic;
  * a COUNT of languages — "multilingual" is the technical driver and is
    permitted; "N languages" is a property of someone else's corpus;
  * a corpus/benchmark SIZE — a number of documents, queries or notes in a
    sentence that also refers to the requester;
  * an ISSUE NUMBER near words identifying the requester — a correlatable
    identifier: anyone with access to a candidate repo confirms or eliminates
    it in one lookup, which is why the number was dropped from the spec;
  * a GitHub URL naming an org outside a small public allowlist.

The only literal token list is `_FORBIDDEN_LABELS`: generic English words for
a commercial counterparty. They are safe to write here, and they are forbidden
not because they leak by themselves but because the agreed vocabulary is
exactly one phrase — "an external client" — and every synonym is someone
starting to describe a relationship this repo has no business describing.
("tenant" and "vendor" are deliberately NOT among them — see the note above
the list: both are ordinary technical vocabulary in this repo.)

A hit is not proof of a leak; it is proof that a sentence needs rewriting to
carry less. If a match is genuinely benign, rephrase rather than widen the
allowlist — the cost of a false positive here is one sentence, and the cost of
a false negative is public and permanent.

This file scans ITSELF along with the rest, so the guard has to live by its
own rule. The handful of lines that necessarily contain what they match — the
pattern definitions and the label list — carry a per-line exemption marker,
and that marker is honoured in THIS FILE ONLY: the exemption is scoped by file
path, so another artefact can name it and gain nothing, and it cannot grow
from "the detector contains its patterns" into "this sentence is inconvenient".
A test below asserts that scoping directly.
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]

PLAN_SLUG = "2026-08-02--infer--igpu-embedding-rerank"

# frank#759: the retrieval-store sidecar that lets the same external client's
# CLI keep vectors in-cluster. Same requester, same discretion rule — and this
# list is the ONLY thing that decides what gets checked, so a follow-on plan
# that forgets to append here ships a green `test_third_party_discretion.py`
# that is evidence about a different piece of work entirely.
GBRAIN_PLAN_SLUG = "2026-08-03-hermes-retrieval-store-sidecar"
GBRAIN_SPEC_SLUG = "2026-08-03--orch--hermes-retrieval-store-sidecar"

# Everything these branches add that a reader outside Frank can see.
SCANNED_PATHS = [
    # ARCHIVED, not deleted. When #748's plan completed (frank#757) these four
    # moved under `implemented/`, and because `_files()` used to skip anything
    # that did not exist, the scan silently stopped reading the spec, the plan
    # and BOTH journals — the four most prose-heavy artefacts, i.e. exactly
    # where a leak lives — while still reporting a comfortable "6 passed".
    # `test_every_scanned_path_exists` below now fails on a rotted entry
    # instead of quietly shrinking the control surface.
    REPO / "docs/superpowers/implemented/specs" / f"{PLAN_SLUG}-design.md",
    REPO / "docs/superpowers/implemented/plans" / PLAN_SLUG,
    REPO / "docs/superpowers/implemented/journals/plans" / f"{PLAN_SLUG}.md",
    REPO / "docs/superpowers/implemented/journals/specs" / f"{PLAN_SLUG}.md",
    REPO / "apps/ovms-retrieval",
    REPO / "scripts/ovms-retrieval-bench.py",
    REPO / "scripts/tests/test_ovms_retrieval_bench.py",
    REPO / "scripts/tests/test_ovms_retrieval_manifests.py",
    REPO / "scripts/tests/test_ovms_retrieval_model_image.py",
    REPO / "scripts/tests/test_igpu_dra_docs.py",
    REPO / "scripts/tests/test_ovms_retrieval_phase5_plan.py",
    REPO / "docs/runbooks/frank-gotchas/igpu-dra.md",
    # frank#759 — the gbrain sidecar. Named file by file rather than by adding
    # `apps/hermes-agent-shell/` wholesale: that directory predates this work by
    # months, and pulling unrelated manifests into a discretion scan buys false
    # positives whose only cure is widening the allowlist.
    REPO / "docs/superpowers/specs" / f"{GBRAIN_SPEC_SLUG}-design.md",
    REPO / "docs/superpowers/plans" / GBRAIN_PLAN_SLUG,
    REPO / "docs/superpowers/journals/plans" / f"{GBRAIN_PLAN_SLUG}.md",
    REPO / "docs/superpowers/journals/specs" / f"{GBRAIN_SPEC_SLUG}.md",
    REPO / "apps/hermes-agent-shell/README.md",
    REPO / "apps/hermes-agent-shell/manifests/deployment.yaml",
    REPO / "apps/hermes-agent-shell/manifests/pvc-gbrain.yaml",
    REPO / "apps/hermes-agent-shell/manifests/configmap-gbrain-initdb.yaml",
    REPO / "scripts/tests/test_hermes_gbrain_sidecar.py",
    pathlib.Path(__file__),
]

# Words that mean "this sentence is about the requester".
_REQUESTER_CONTEXT = (
    r"(?:requester|requesting|consumer|client|private issue|their corpus|"
    r"the corpus)"
)

# Nouns that would count someone else's documents rather than this repo's
# synthetic benchmark inputs.
_CORPUS_NOUNS = r"(?:documents|docs|notes|records|articles|entries|queries|corpus)"

_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "retrieval-quality figure",
        re.compile(  # discretion-selftest
            r"\b(?:recall|ndcg|mrr|precision|f1|map)\s*@?\s*\d*\s*"  # discretion-selftest
            r"(?:of|=|==|>=|<=|>|<|≥|≤|:)\s*[\d.]+",  # discretion-selftest
            re.IGNORECASE,
        ),
        "a recall/nDCG/MRR TARGET or SCORE is the requester's benchmark "
        "statistic. Name the metric if you must; keep the number in the "
        "private issue.",
    ),
    (
        "language count",
        re.compile(
            r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+"
            r"(?:[A-Za-z-]+\s+)?languages?\b",
            re.IGNORECASE,
        ),
        "how many languages the corpus spans is a corpus statistic. "
        "'multilingual' is the whole of what this repo needs to know.",
    ),
    (
        "github org outside the public allowlist",
        # The org-settings URL shape puts a literal path segment before the
        # org name, which must not be read as the org.  # discretion-selftest
        re.compile(r"github\.com/(?:orgs/)?([A-Za-z0-9][\w.-]*)/", re.IGNORECASE),  # discretion-selftest
        "a GitHub URL naming an org — check it against _PUBLIC_ORGS; the "
        "consumer repo must never appear.",
    ),
]

# Orgs that legitimately appear in these artefacts: this repo's own, plus the
# upstreams the image and runtime are built from.
_PUBLIC_ORGS = {
    "derio-net",
    "openvinotoolkit",
    "huggingface",
    "baai",
    "openvino",
    "kubernetes",
    "intel",
    "docker",
    "actions",
    "astral-sh",
    "peaceiris",
    "azure",
}

# "tenant" (multi-tenancy) and "vendor" (a repo that vendors a dependency,
# and the papers series' vendor landscape) are deliberately absent: both are
# ordinary technical vocabulary here, and a guard that cries wolf on them is a
# guard that gets deleted.
_FORBIDDEN_LABELS = ("customer", "partner", "buyer")  # discretion-selftest

# Issue numbers in `derio-net/frank` — THIS repo, which is public. They appear
# in commit subjects, PR titles, plan front matter and manifest provenance
# comments throughout, and they correlate to nothing: looking one up lands you
# back here.
#
# The rule below exists to stop a number from the PRIVATE repo sitting next to
# words identifying the requester, because that IS a correlatable identifier.
# `#\d+` cannot tell the two apart, so the discrimination has to be a list.
# Keeping it explicit and short is the point: any OTHER number appearing next to
# "requester"/"client"/"corpus" still fails, which is exactly the shape worth
# stopping. Do not add a number here without knowing it is a frank issue.
_PUBLIC_FRANK_ISSUES = {
    748,  # the iGPU retrieval tier this work builds on
    751,  # its follow-on, cited in #759's header
    759,  # the retrieval-store sidecar; `gbrain` is the codename IT uses, publicly
}

_WINDOW = 120

# The per-line exemption marker. It is honoured in THIS FILE ONLY — the
# exemption is scoped by file path, not by a repo-wide taboo on the string, so
# another file (a journal entry describing this design, say) can name it
# freely and gain nothing by it.
_SELFTEST_MARKER = "discretion-" + "selftest"
_SELF = pathlib.Path(__file__)


def _scannable(text: str, path: pathlib.Path | None = None) -> str:
    """Blank out exempt lines, preserving line count.

    Only this file's own lines can be exempt: its pattern definitions and
    label list necessarily contain what they match. Everywhere else the marker
    is inert text.
    """
    if path is not None and path.resolve() != _SELF.resolve():
        return text
    return "\n".join(
        "" if _SELFTEST_MARKER in line else line for line in text.splitlines()
    )


def _files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for entry in SCANNED_PATHS:
        if entry.is_dir():
            out.extend(p for p in sorted(entry.rglob("*")) if p.is_file())
        elif entry.is_file():
            out.append(entry)
    assert out, "the discretion scan found no files — the path list has rotted"
    return out


def test_every_scanned_path_exists():
    """A path that no longer exists must FAIL, not be skipped.

    `_files()` walks the list and quietly ignores anything missing, which makes
    the scan shrink itself whenever an artefact is renamed or archived — and
    plans ARE archived here as a matter of routine (`docs/superpowers/plans/` ->
    `implemented/`). That is how #748's spec, plan and both journals dropped out
    of the scan while the file kept reporting green.

    The blanket `assert out` at the end of `_files()` cannot catch this: it only
    fires when EVERY entry has rotted. Coverage that degrades one path at a time
    needs a per-path assertion.
    """
    missing = [p.relative_to(REPO).as_posix() for p in SCANNED_PATHS if not p.exists()]
    assert not missing, (
        "these SCANNED_PATHS entries do not exist, so they are being silently "
        "skipped and the discretion scan is narrower than it looks. If the "
        f"artefact moved, repoint the entry; if it was deleted, remove it: {missing}"
    )


def _rel(path: pathlib.Path) -> str:
    return path.relative_to(REPO).as_posix()


def _hits(pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    found = []
    for path in _files():
        text = _scannable(path.read_text(encoding="utf-8", errors="replace"), path)
        for match in pattern.finditer(text):
            start = max(0, match.start() - 40)
            found.append((_rel(path), " ".join(text[start : match.end() + 40].split())))
    return found


def test_no_corpus_or_benchmark_statistics():
    offenders = []
    for name, pattern, why in _PATTERNS:
        if name == "github org outside the public allowlist":
            continue
        for rel, excerpt in _hits(pattern):
            offenders.append(f"[{name}] {rel}: …{excerpt}… — {why}")
    assert not offenders, (
        "discretion breach — these read as the private consumer's statistics "
        "rather than Frank's technical facts:\n  " + "\n  ".join(offenders)
    )


def test_no_github_org_outside_the_public_allowlist():
    pattern = next(p for name, p, _ in _PATTERNS if name.startswith("github org"))
    offenders = []
    for path in _files():
        text = _scannable(path.read_text(encoding="utf-8", errors="replace"), path)
        for match in pattern.finditer(text):
            org = match.group(1).lower()
            if org not in _PUBLIC_ORGS:
                offenders.append(f"{_rel(path)}: github.com/{match.group(1)}/…")
    assert not offenders, (
        "a GitHub org outside the public allowlist appears in these artefacts. "
        "If it is a legitimate public upstream, add it to _PUBLIC_ORGS with a "
        f"reason; if it is the requester, it must not be here at all: {offenders}"
    )


def test_no_issue_number_is_correlatable_with_the_requester():
    """An issue number plus "the requester" is an identifier, not a citation.

    Anyone holding a list of candidate repos confirms or eliminates one in a
    single lookup. Cite the private issue as "the private issue" — with no
    number — exactly as the spec now does.

    Numbers in `_PUBLIC_FRANK_ISSUES` are exempt, and that exemption was added
    on 2026-08-03 rather than being original: widening `SCANNED_PATHS` to cover
    #759's artefacts produced eight hits, every one of them a reference to
    frank's OWN public issues (`frank#759` in a manifest provenance comment,
    "the iGPU retrieval tier from #748" in the spec). Scrubbing those would have
    satisfied the regex while changing the actual risk not at all — and it would
    have stripped provenance that every other comment in the same file carries.
    This is a deliberate narrowing: the guard now fires on an issue number that
    nobody has accounted for, which is the shape a private-repo number would
    have.
    """
    number = re.compile(r"#(\d+)")
    context = re.compile(_REQUESTER_CONTEXT, re.IGNORECASE)
    offenders = []
    for path in _files():
        text = _scannable(path.read_text(encoding="utf-8", errors="replace"), path)
        for match in number.finditer(text):
            if int(match.group(1)) in _PUBLIC_FRANK_ISSUES:
                continue
            window = text[
                max(0, match.start() - _WINDOW) : match.end() + _WINDOW
            ]
            if context.search(window):
                offenders.append(f"{_rel(path)}: …{' '.join(window.split())}…")
    assert not offenders, (
        "an issue number sits next to words identifying the requester — drop "
        "the number (or, if it is one of frank's OWN public issues, add it to "
        f"_PUBLIC_FRANK_ISSUES with a reason): {offenders}"
    )


def test_no_corpus_size_next_to_the_requester():
    """A count of documents/queries is only sensitive when it is THEIRS.

    The harness legitimately talks about 20 passages of generated filler, so
    the count alone cannot be the trigger; proximity to requester-words is.
    """
    counted = re.compile(rf"\b\d[\d,._]*\s*(?:k|m)?\s+{_CORPUS_NOUNS}\b", re.IGNORECASE)
    context = re.compile(_REQUESTER_CONTEXT, re.IGNORECASE)
    offenders = []
    for path in _files():
        text = _scannable(path.read_text(encoding="utf-8", errors="replace"), path)
        for match in counted.finditer(text):
            window = text[
                max(0, match.start() - _WINDOW) : match.end() + _WINDOW
            ]
            if context.search(window):
                offenders.append(f"{_rel(path)}: …{' '.join(window.split())}…")
    assert not offenders, (
        "a corpus/benchmark SIZE appears next to words identifying the "
        f"requester — that is the private corpus's shape: {offenders}"
    )


def test_the_consumer_is_called_an_external_client_and_nothing_else():
    """One agreed vocabulary word, so nobody has to judge case by case.

    These synonyms do not leak by themselves. They are forbidden because each
    one is the first sentence of a description of a relationship this repo has
    no business describing, and because a single permitted phrase is a rule a
    reviewer can actually apply.
    """
    offenders = []
    for path in _files():
        text = _scannable(path.read_text(encoding="utf-8", errors="replace"), path)
        for label in _FORBIDDEN_LABELS:
            for match in re.finditer(rf"\b{label}s?\b", text, re.IGNORECASE):
                window = text[max(0, match.start() - 60) : match.end() + 60]
                offenders.append(f"{_rel(path)} [{label}]: …{' '.join(window.split())}…")
    assert not offenders, (
        'refer to the requester only as "an external client" — every synonym '
        f"invites detail this repo must not carry: {offenders}"
    )


def test_the_selftest_marker_is_honoured_in_this_file_only():
    """The exemption is scoped by file, so it cannot spread.

    A per-line opt-out is a reasonable answer to "the detector must contain
    its own patterns" and a terrible answer to "this sentence trips the
    guard". Scoping it by path means another file can NAME the marker — a
    journal entry describing this design does — without gaining an exemption
    from it. Asserted on the mechanism directly rather than by planting a
    marker in a real artefact.
    """
    breach = "a corpus of nine invented languages"  # discretion-selftest
    planted = f"{breach}  # {_SELFTEST_MARKER}"
    assert _scannable(planted, _SELF) == "", "this file's own marker must exempt the line"
    other = REPO / "docs/runbooks/frank-gotchas/igpu-dra.md"
    assert _scannable(planted, other) == planted, (
        "the marker must be inert outside this file — otherwise any artefact "
        "could opt itself out of the discretion scan one line at a time"
    )
    language_pattern = next(p for name, p, _ in _PATTERNS if name == "language count")
    assert language_pattern.search(_scannable(planted, other)), (
        "sanity: the planted line is genuinely something the scan would catch"
    )
