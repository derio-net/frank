"""Tripwire: an acceptance row's `status` must not be contradicted by its own
`notes`.

`docs/acceptance/matrix.yaml` is the artefact a reader consults to find out
how strongly a capability is guaranteed, and `status` is the machine-readable
half of that answer. When the prose underneath disagrees, the row is worse
than either half alone: the summary counts it one way, the sentence a human
actually reads says the other, and there is nothing to reconcile them.

That happened here. `gpu-igpu-claim-documented` was moved to `status: ci`
because `.github/workflows/repo-tripwires.yml` runs `pytest scripts/tests/ -q`
on every PR — while its notes still ended "(local guard, not CI-run)", the
sentence written back when nothing ran the suite.

Deliberately narrow: this asserts only that rows CLAIMING CI enforcement do
not simultaneously deny it. Rows with other statuses are left alone — several
carry legitimately stale "local guard" prose from before repo-tripwires.yml
existed, and rewriting them is a different piece of work with a different
blast radius.
"""
from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
MATRIX = REPO / "docs" / "acceptance" / "matrix.yaml"

# Phrasings that assert the guard does NOT run in CI. Matched case-insensitively
# against the notes of `status: ci` rows only.
_DENIES_CI = re.compile(
    r"not\s+ci-run|no\s+ci\s+run|local\s+guard\s*[;,(]?\s*(?:not|no)\b|"
    r"nothing\s+runs\s+(?:these|it)|manual\s+only",
    re.IGNORECASE,
)


def _rows() -> list[dict]:
    doc = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    rows = doc.get("rows") or []
    assert rows, "acceptance matrix has no rows"
    return rows


def test_ci_rows_do_not_describe_themselves_as_not_ci_run():
    offenders = []
    for row in _rows():
        if row.get("status") != "ci":
            continue
        notes = str(row.get("notes") or "")
        if _DENIES_CI.search(notes):
            offenders.append((row.get("id"), notes.strip()[:160]))
    assert not offenders, (
        "these rows are marked status: ci but their notes say the guard is not "
        "CI-run — one of the two is wrong, and a reader has no way to tell "
        f"which: {offenders}"
    )


def test_ci_rows_name_the_evidence_that_makes_them_ci():
    """`status: ci` is a claim about automation; it needs a pointer to it.

    Without a `levels` entry the row asserts CI enforcement while naming
    nothing that could be run, which is unfalsifiable — the exact shape this
    matrix exists to avoid.
    """
    offenders = [
        row.get("id")
        for row in _rows()
        if row.get("status") == "ci" and not (row.get("levels") or {})
    ]
    assert not offenders, (
        f"status: ci with no levels entry naming the automated guard: {offenders}"
    )
