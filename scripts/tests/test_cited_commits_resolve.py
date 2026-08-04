"""Tripwire: a commit id cited in a post must be a commit that exists.

WHY THIS EXISTS. The building series ends most posts with a `## Missteps`
table whose last column is headed **Commit**. That column is the post's
receipt: it is the one place a reader can go from "here is a mistake we made"
to "here is the change that fixed it". It is also the cheapest column in the
corpus to fake, because nothing renders it, nothing resolves it, and an
8-character hex string is indistinguishable from a real one at reading speed.

It was faked. The Phase 5+6 milestone review found **86 non-resolving values**
across **17 posts**, and the giveaway was that the same sequence repeated
post to post: `a1b2c3d4`, `e5f6g7h8`, `i9j0k1l2`, `m3n4o5p6`, `q7r8s9t0` — a
template placeholder that was never filled in, carried across nine posts
verbatim. Some were not even hexadecimal (`3456fghi`, `9h0i1j2k`, `7p8q9r0s`).
Others were hex-shaped and read as entirely genuine (`27d947d2`, `c34d065b`,
`19a2b4f1` in `building/11-agentic-control-plane`); those were checked against
the GitHub API as well as the local object store, and no commit exists for any
of them on any branch. The fix was to blank every one to an em dash, which is
the placeholder the corpus already uses (`building/30-frank-papers` has carried
`—` in that column since it was written).

This guard exists so the next one cannot be written silently. It answers one
question — does this string name a commit — and nothing else. It cannot tell
whether the commit cited is the RIGHT commit, any more than the sibling guard
`test_actionable_sections_carry_commands.py` can tell whether a command is a
good command. Both raise a floor.

FOUR DESIGN CHOICES:

1. **Keyed off the column, not the page.** Only cells under a header of
   `Commit` or `Evidence` are examined. Those are the only two headers in the
   corpus that promise provenance (measured: 31 `Commit` columns, 4
   `Evidence`). Scanning whole pages instead would drag in every backticked
   8-character identifier in prose — `Recreate`, `hostPath`, `caBundle`,
   `emptyDir`, `talosctl` — none of which claims to be a commit.

2. **Shape, not hex.** The candidate is a backticked run of 7-40 alphanumerics
   containing at least one digit. Requiring hex would miss over half the
   fabrications, which were mashed-keyboard placeholders rather than plausible
   shas. Requiring a digit is what keeps ordinary backticked words out: no
   English identifier in these columns carries one, and a real abbreviated sha
   without a digit is a 0.04% accident. Repo paths and line ranges cited as
   evidence — `apps/litellm/values.yaml:85-89`, `patches/phase13-auth/…` —
   never match, because `/`, `.`, `:` and `-` are not alphanumerics.

3. **An em dash is the accepted way to say "no commit".** Not the empty
   string, not "n/a", not a deleted row. Deleting the row would delete the
   misstep, which is the part worth keeping; the corpus convention is to keep
   the row and blank the receipt.

4. **The detector carries a self-test.** `test_the_detector_can_actually_fail`
   pins both directions on fixtures, including a fabricated id that must be
   flagged and a real commit from this repository's history that must not be.
   A guard that cannot fire reads as coverage while providing none — which is
   exactly the shape of the Commit column it is backstopping.

Resolution is `git cat-file -e <value>^{commit}` against this repository. That
is deliberately local: an id that resolves only on a remote you have to be
authenticated to reach is not a receipt a reader can redeem.
"""

from __future__ import annotations

import functools
import pathlib
import re
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTENT = ROOT / "blog" / "content" / "docs"

# Headers whose cells claim to point at provenance.
PROVENANCE_HEADERS = {"commit", "evidence"}

# The accepted way to say "there is no commit for this row".
NO_COMMIT = "—"

# A backticked run of 7-40 alphanumerics that is EITHER carrying a digit OR
# entirely hex. See design choice 2 for why the primary rule is shape-with-a-
# digit and not hex.
#
# The all-hex arm closes a gap found by probing this guard with `deadbeef`,
# which it did not catch: the digit rule was written against the 86 real
# fabrications, every one of which carried a digit, so an all-letter hex
# placeholder (`deadbeef`, `cafebabe`, `faceb00c`'s letter-only cousins) sailed
# through. It costs nothing in false positives, because the ordinary backticked
# words this guard must ignore are not valid hex — `Recreate` (r, t),
# `hostPath` (h, o, s, t, P), `caBundle` (u, n, l), `emptyDir` (m, p, t, y, i,
# r) and `talosctl` (t, l, o, s) each contain at least one non-hex letter, and
# `test_ordinary_backticked_words_are_not_candidates` pins that.
_CANDIDATE = re.compile(r"^(?=[0-9A-Za-z]{7,40}$)(?:(?=.*\d)|(?=[0-9A-Fa-f]+$)).*$")
_INLINE_CODE = re.compile(r"`([^`]*)`")

# A table row's cells, honouring `\|` escaped inside inline code.
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_SEPARATOR_CHARS = set("|-: ")


# --------------------------------------------------------------------------- scanner


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    return (fm if isinstance(fm, dict) else {}), text[end + 4 :]


def _body(post: pathlib.Path) -> str:
    return _split_frontmatter(post.read_text(encoding="utf-8"))[1]


def _cells(line: str) -> list[str]:
    parts = _UNESCAPED_PIPE.split(line.strip())
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [c.strip() for c in parts]


def _is_separator(line: str) -> bool:
    s = line.strip()
    return len(s) > 3 and s.startswith("|") and set(s) <= _SEPARATOR_CHARS


def provenance_cells(body: str) -> list[tuple[str, str]]:
    """(header, cell) for every cell under a Commit/Evidence column."""
    lines = body.splitlines()
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        if not (
            lines[i].strip().startswith("|")
            and i + 1 < len(lines)
            and _is_separator(lines[i + 1])
        ):
            i += 1
            continue
        header = _cells(lines[i])
        columns = [
            j for j, h in enumerate(header) if h.strip().lower() in PROVENANCE_HEADERS
        ]
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            row = _cells(lines[j])
            for k in columns:
                if k < len(row):
                    out.append((header[k], row[k]))
            j += 1
        i = j
    return out


def cited_commit_ids(body: str) -> list[str]:
    """Every value in a provenance column that claims to be a commit id."""
    return [
        token
        for _header, cell in provenance_cells(body)
        for token in _INLINE_CODE.findall(cell)
        if _CANDIDATE.match(token)
    ]


@functools.lru_cache(maxsize=None)
def _resolves(value: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{value}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


def unresolved_commit_ids(body: str) -> list[str]:
    return [v for v in cited_commit_ids(body) if not _resolves(v)]


def scanned_posts() -> list[pathlib.Path]:
    """Every page bundle under `blog/content/docs`, papers included.

    Unlike the sibling guard there is no series filter: a fabricated commit id
    is a fabrication wherever it is printed, and papers carry Evidence columns
    of their own.
    """
    return sorted(CONTENT.glob("*/*/index.md"))


# --------------------------------------------------------------------------- fixtures

# A real commit in this repository: the Papers banner regeneration cited by
# `building/30-frank-papers`. History is immutable, so this stays resolvable.
REAL_COMMIT = "a6a83cb"

FABRICATED = """\
## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---|---|---|---|
| It broke | it was wrong | we fixed it | `a1b2c3d4` |
"""

FABRICATED_NON_HEX = """\
## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---|---|---|---|
| It broke | it was wrong | we fixed it | `3456fghi` |
"""

BLANKED = """\
## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---|---|---|---|
| It broke | it was wrong | we fixed it | — |
"""

REAL = f"""\
## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---|---|---|---|
| It broke | it was wrong | we fixed it | `{REAL_COMMIT}` |
"""

PATH_EVIDENCE = """\
## Claims

| Claim | Evidence |
|---|---|
| The gateway pins its models | `apps/litellm/values.yaml:85-89` |
| Blueprints are declarative | `apps/authentik-extras/manifests/` |
| The runbook exists | runbook `auth-grafana-oidc-secret` |
"""

PR_EVIDENCE = """\
## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---|---|---|---|
| It broke | it was wrong | we fixed it | PR #214 |
"""

PROSE_WORD_IN_A_CELL = """\
## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---|---|---|---|
| RWO deadlock | RollingUpdate | switched to `Recreate` | — |
"""

ESCAPED_PIPE = f"""\
## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---|---|---|---|
| SOPS secret | wrong path | `sops -d f \\| kubectl apply -f -` | `{REAL_COMMIT}` |
"""

OTHER_COLUMN_IS_NOT_CHECKED = """\
## Sizing

| Alias | Tag | Quant |
|---|---|---|
| gemma-12b | `gemma4a1b2` | q4_K_M |
"""


def test_the_detector_can_actually_fail() -> None:
    """Pin both directions: a fabricated id is flagged, a real one is not."""
    assert unresolved_commit_ids(FABRICATED) == ["a1b2c3d4"]
    assert unresolved_commit_ids(FABRICATED_NON_HEX) == ["3456fghi"]
    assert unresolved_commit_ids(BLANKED) == []
    assert unresolved_commit_ids(REAL) == []
    assert unresolved_commit_ids(ESCAPED_PIPE) == []


def test_evidence_that_is_not_a_commit_id_is_left_alone() -> None:
    """Repo paths, line ranges, PR numbers and prose words are not commit ids.

    The Evidence column legitimately carries `apps/…/values.yaml:85-89` and
    runbook ids; the Commit column legitimately carries `PR #214`. A guard that
    flagged those would push authors to delete real provenance to get green.
    """
    assert cited_commit_ids(PATH_EVIDENCE) == []
    assert cited_commit_ids(PR_EVIDENCE) == []
    assert cited_commit_ids(PROSE_WORD_IN_A_CELL) == []


def test_only_provenance_columns_are_read() -> None:
    """A backticked identifier in some other column is not a claimed receipt."""
    assert cited_commit_ids(OTHER_COLUMN_IS_NOT_CHECKED) == []


def test_an_all_hex_placeholder_with_no_digit_is_still_a_candidate() -> None:
    """`deadbeef` must be caught, and ordinary words must still not be.

    Found by probing this guard rather than by reading it: the digit rule was
    written against the 86 real fabrications, every one of which carried a
    digit, so an all-letter hex placeholder went straight through. Classic
    placeholders are exactly that shape. The all-hex arm costs nothing, because
    the words this guard must ignore are not valid hex.
    """
    caught = cited_commit_ids(
        "| What | Commit |\n|---|---|\n"
        "| all-letter hex placeholder | `deadbeef` |\n"
        "| another | `cafebabe` |\n"
    )
    assert caught == ["deadbeef", "cafebabe"], caught

    for word in ("Recreate", "hostPath", "caBundle", "emptyDir", "talosctl"):
        assert cited_commit_ids(
            f"| What | Commit |\n|---|---|\n| prose | `{word}` |\n"
        ) == [], f"{word} became a false positive"


def test_the_em_dash_is_the_documented_placeholder() -> None:
    """Pin the convention the fix relies on, so it cannot drift silently."""
    assert NO_COMMIT == "—"
    papers = CONTENT / "building" / "30-frank-papers" / "index.md"
    cells = [c for _h, c in provenance_cells(_body(papers))]
    assert NO_COMMIT in cells, (
        "building/30-frank-papers no longer blanks any Commit cell with an em "
        "dash — the corpus convention this guard prescribes has moved"
    )


# --------------------------------------------------------------------------- corpus


def test_the_clone_is_not_shallow() -> None:
    """A shallow clone makes this guard lie, so refuse to run in one.

    Learned from this guard's first CI run, which failed with twenty posts
    "citing commit ids that do not exist" — every one of which existed. GitHub's
    `actions/checkout` defaults to `fetch-depth: 1`, so `git cat-file -e` misses
    essentially all history and the verdict inverts: real citations read as
    fabrications.

    `test_git_can_resolve_commits_at_all` did NOT catch it, because its canary
    is reachable at depth 1 by construction — it is near HEAD. Shallowness has
    to be asked about directly.

    The repo pins `fetch-depth: 0` on the tripwires job. If that is ever
    dropped, this fails with the real reason instead of blaming the posts.
    """
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert shallow == "false", (
        f"{ROOT} is a shallow clone, so commit lookups cannot be trusted and "
        "this guard would report real citations as fabricated. Set "
        "`fetch-depth: 0` on the actions/checkout step that runs these tests."
    )


def test_git_can_resolve_commits_at_all() -> None:
    """Guard against a scanner that passes because `git` is unusable.

    If every lookup fails the corpus test screams; if every lookup ERRORS the
    same way for a real commit, the failure is the environment, not the posts.
    """
    assert _resolves(REAL_COMMIT), (
        f"{REAL_COMMIT} does not resolve in {ROOT} — this guard needs the full "
        "repository history, not a shallow clone"
    )


def test_the_corpus_has_commit_citations_to_check() -> None:
    """Guard against a scanner that silently finds nothing."""
    posts = scanned_posts()
    assert len(posts) > 50, f"only {len(posts)} posts scanned; expected the full corpus"
    cited = [v for p in posts for v in cited_commit_ids(_body(p))]
    assert len(cited) > 50, (
        f"only {len(cited)} commit citations found across the corpus; the column "
        "vocabulary or the table parser is broken"
    )


def _post_id(post: pathlib.Path) -> str:
    return f"{post.parent.parent.name}/{post.parent.name}"


@pytest.mark.parametrize("post", scanned_posts(), ids=_post_id)
def test_cited_commits_resolve(post: pathlib.Path) -> None:
    bad = unresolved_commit_ids(_body(post))
    assert not bad, (
        f"{post.relative_to(ROOT)} cites commit id(s) that do not exist in this "
        f"repository: {bad}. Cite the real commit, or blank the cell to "
        f"'{NO_COMMIT}' — the corpus convention for a misstep with no single "
        "commit behind it. Do not invent a plausible sha, and do not delete the "
        "row: the misstep is the part worth keeping."
    )
