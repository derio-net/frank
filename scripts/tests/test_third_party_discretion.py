"""Tripwire: the ovms-retrieval artefacts must not leak the private consumer.

This repo is PUBLIC. The work in `apps/ovms-retrieval/` was requested by a
repo that is not, and `agents/rules/third-party-privacy.md` plus the design
spec's own "Scope discipline" section set the line: name no consumer repo,
product or corpus; reproduce no benchmark queries, document titles or corpus
statistics; refer to the requester only as an external client. The spec calls
a breach "a blocking finding" — and then, in its Test Plan, breached it
itself. Prose that asks reviewers to be vigilant is not a control; this file
is.

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

# Everything this branch adds that a reader outside Frank can see.
SCANNED_PATHS = [
    REPO / "docs/superpowers/specs" / f"{PLAN_SLUG}-design.md",
    REPO / "docs/superpowers/plans" / PLAN_SLUG,
    REPO / "docs/superpowers/journals/plans" / f"{PLAN_SLUG}.md",
    REPO / "docs/superpowers/journals/specs" / f"{PLAN_SLUG}.md",
    REPO / "apps/ovms-retrieval",
    REPO / "scripts/ovms-retrieval-bench.py",
    REPO / "scripts/tests/test_ovms_retrieval_bench.py",
    REPO / "scripts/tests/test_ovms_retrieval_manifests.py",
    REPO / "scripts/tests/test_ovms_retrieval_model_image.py",
    REPO / "scripts/tests/test_igpu_dra_docs.py",
    REPO / "scripts/tests/test_ovms_retrieval_phase5_plan.py",
    REPO / "docs/runbooks/frank-gotchas/igpu-dra.md",
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
    """
    number = re.compile(r"#\d+")
    context = re.compile(_REQUESTER_CONTEXT, re.IGNORECASE)
    offenders = []
    for path in _files():
        text = _scannable(path.read_text(encoding="utf-8", errors="replace"), path)
        for match in number.finditer(text):
            window = text[
                max(0, match.start() - _WINDOW) : match.end() + _WINDOW
            ]
            if context.search(window):
                offenders.append(f"{_rel(path)}: …{' '.join(window.split())}…")
    assert not offenders, (
        "an issue number sits next to words identifying the requester — drop "
        f"the number: {offenders}"
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
