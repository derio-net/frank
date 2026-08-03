"""Tripwire: an actionable heading must be followed by something to run.

WHY THIS EXISTS. blog-craft's educational-writing gate asks whether a post has
an actionable section, and it answers that question with a **heading regex**
(`_ACTIONABLE` in `blog/scripts/validate_educational.py`). A heading matches or
it does not; nothing looks underneath it. So the cheapest way to clear the gate
is to rename a paragraph "Verifying the Setup" and change nothing else, and the
gate cannot tell that apart from a real runbook.

That is not hypothetical. This plan's own journal records the adjacent failures
found while writing these sections: a verify section whose commands were all
observational and discriminated between no two states; three published commands
that exited 0 or printed nothing while proving nothing. Both are headings WITH
content. A heading with no content at all is the floor below those, and it is
the one a regex will always pass.

This guard raises that floor. It does not, and cannot, judge whether the
commands are good — the journal is emphatic that structure is indistinguishable
between a good verify section and a useless one. It only asserts that a section
promising the reader something to do contains at least one fenced block before
the next heading of the same or higher level.

SIX DELIBERATE DESIGN CHOICES, each with a reason that cost something to learn:

1. **Scanned independently of `quality_exempt`.** That flag is a WHOLE-POST
   opt-out: `validate_educational.py` `continue`s past both the gate and the
   lint layer for an exempt post. The exemption means "this layer has no
   operational surface", not "this post may carry hollow headings". Excluding
   exempt posts here would put a blind spot inside the guard written to remove
   blind spots. `building/06-fun-stuff` is the live case and
   `test_the_exempt_post_is_still_scanned` pins it.

2. **Mermaid fences do not count.** A diagram is not something the reader runs.
   Counting it would let a "Verify" section satisfy this guard with a picture.

3. **Same-or-higher level ends the section.** A deeper heading (`###` under
   `##`) is part of the section, so a block under any subheading counts. This
   matters because several posts put the narrative under the H2 and the commands
   under H3 subheads.

4. **The detector carries a self-test.** A guard that cannot fire reads as
   coverage while providing none, which is the same shape as the heading regex
   it is backstopping. `test_the_detector_can_actually_fail` pins both
   directions on fixtures, mirroring `test_python_toolchain_single_source.py`.

5. **A symptom/cause/fix table row counts, if it carries inline code.** The
   plan specified "at least one fenced code block". Written that way, this guard
   flagged 29 sections — and 24 of them were the building series' house
   `## Recovery Path` table (symptom | cause | fix, commands in the cells).
   Satisfying the literal rule would have meant converting two dozen good tables
   into code blocks: renaming working prose to please a regex, which is the
   exact failure this plan's own gotcha entry warns about. So a table row is an
   artefact. The inline-code requirement keeps it from degenerating: a table of
   pure prose still does not satisfy an actionable heading.

6. **A subheading inherits its parent section's artefacts.** The unit a reader
   navigates to is the H2; a subheading is a label inside it. `### Diagnosis`
   in a Symptom/Diagnosis/Fix triple, and `#### Recovery: <note>` annotating the
   commands above it, are explanatory labels, not promises of their own runbook.
   Dropping this took the residue from 6 to 2. A top-level actionable heading
   with nothing under it — the defect this guard exists for — is still caught,
   because it has no parent to inherit from.

Measured while designing it, on the corpus at the end of Phase 5:
29 hollow sections under the literal rule, 6 once tables counted, 2 once
subheadings inherited. Both survivors are in one post and are waived below with
reasons. Zero of the 29 were the defect the guard is aimed at, which is the
expected result for a tripwire: it is here to catch the next one.
"""

from __future__ import annotations

import pathlib
import re

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".blog-craft.yaml"
CONTENT = ROOT / "blog" / "content" / "docs"

# Copied verbatim from blog/scripts/validate_educational.py so this guard tests
# the SAME vocabulary the gate accepts. Divergence is pinned by
# test_vocabulary_matches_the_gate below — if blog-craft widens the gate, this
# tripwire must widen with it or it silently stops covering the new words.
_ACTIONABLE = re.compile(
    r"(reproduce|try\s+it\s+yourself|run\s*book|step[\s-]*by[\s-]*step|"
    r"\bsteps\b|\bprocedure\b|\bhow\s+to\b|\bverif\w*|\brecover\w*|"
    r"\brollback\b|\bchecklist\b|\bwalkthrough\b|\brunbook\b|"
    r"\btroubleshoot\w*|\bdiagnos\w*|\bsmoke\s*test)",
    re.IGNORECASE,
)


# Enumerated waivers. Not a predicate loosening: each entry names one heading in
# one post and says why manufacturing a command there would be worse than the
# hollow heading. Kept tiny and pinned in both directions — a waiver whose
# heading no longer exists fails, and a waiver that is no longer needed fails.
PROSE_ONLY_SECTIONS: dict[tuple[str, str], str] = {
    (
        "building/06-fun-stuff",
        "Diagnosing a device that accepts writes and does nothing",
    ): (
        "The post is `quality_exempt` because the layer has no operational "
        "surface: the LED controller accepts writes and ignores them, and no "
        "command a reader runs changes that. The section is an elimination "
        "ORDER (permissions, then autosuspend, then read the register back), "
        "which is the transferable part. Inventing commands here would "
        "manufacture the runbook this plan exists to prevent."
    ),
    ("building/06-fun-stuff", "Why there is no verification section"): (
        "A heading that declares the ABSENCE of a verification section, matched "
        "only because `\\bverif\\w*` sees the word 'verification'. Its whole "
        "argument is that this layer has no failure worth catching. A fenced "
        "block under it would contradict its own text."
    ),
}


# --------------------------------------------------------------------------- scanner

_FENCE = re.compile(r"^(`{3,}|~{3,})\s*(\S*)")
_HEADING = re.compile(r"^(#{2,6})\s+(.*?)\s*#*$")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4 :]
    return (fm if isinstance(fm, dict) else {}), body


def _body(post: pathlib.Path) -> str:
    return _split_frontmatter(post.read_text(encoding="utf-8"))[1]


def _series_values(field) -> list[str]:
    if isinstance(field, str):
        return [s.strip() for s in field.split(",") if s.strip()]
    if isinstance(field, list):
        return [s for s in field if isinstance(s, str)]
    return []


def _non_posts_series_keys() -> set[str]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return {
        s["key"]
        for s in (cfg.get("series") or [])
        if isinstance(s, dict)
        and isinstance(s.get("key"), str)
        and s.get("content_type", "posts") != "posts"
    }


def scanned_posts() -> list[pathlib.Path]:
    """Every `content_type: posts` post, INCLUDING `quality_exempt` ones.

    Mirrors `validate_educational.py`'s selection except for the exemption —
    see design choice 1 in the module docstring.
    """
    skip = _non_posts_series_keys()
    posts = []
    for p in sorted(CONTENT.glob("*/*/index.md")):
        fm, _ = _split_frontmatter(p.read_text(encoding="utf-8"))
        if set(_series_values(fm.get("series"))) & skip:
            continue
        posts.append(p)
    return posts


def _events(body: str):
    """(kind, level, text) per line, with fenced blocks masked out.

    kind is one of:
      heading — an ATX heading OUTSIDE any fence
      fence   — the OPENING line of a block, tagged with its info string
      row     — a markdown table row carrying at least one inline-code span
    """
    out = []
    fence: str | None = None
    for line in body.splitlines():
        m = _FENCE.match(line.strip())
        if fence is not None:
            # Inside a block: only a closing fence of the same character ends it.
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)
            out.append(("fence", 0, m.group(2).lower()))
            continue
        h = _HEADING.match(line)
        if h:
            out.append(("heading", len(h.group(1)), h.group(2).strip()))
            continue
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and "`" in s:
            out.append(("row", 0, s))
    return out


def actionable_headings(body: str) -> list[str]:
    return [
        text
        for kind, _lvl, text in _events(body)
        if kind == "heading" and _ACTIONABLE.search(text)
    ]


def _is_artefact(kind: str, text: str) -> bool:
    """Something the reader can act on: a command block or a fix-table row."""
    if kind == "row":
        return True
    return kind == "fence" and not text.startswith("mermaid")


def _section_has_artefact(events, start: int, level: int) -> bool:
    """Scan from `start` to the next heading of level <= `level`."""
    for kind, lvl, text in events[start + 1 :]:
        if kind == "heading":
            if lvl <= level:
                return False
            continue
        if _is_artefact(kind, text):
            return True
    return False


def hollow_actionable_sections(body: str) -> list[str]:
    """Actionable headings whose section carries nothing the reader can run.

    A section runs to the next heading of the same or higher level (design
    choice 3). It is satisfied by a non-mermaid fenced block (choice 2) or by a
    symptom/cause/fix table row carrying an inline-code span (choice 5). A
    SUBheading also inherits its parent section's artefacts (choice 6).
    """
    events = _events(body)
    hollow: list[str] = []
    for i, (kind, level, text) in enumerate(events):
        if kind != "heading" or not _ACTIONABLE.search(text):
            continue
        if _section_has_artefact(events, i, level):
            continue
        # Inherit: find the nearest enclosing heading and scan ITS section.
        parent = next(
            (
                j
                for j in range(i - 1, -1, -1)
                if events[j][0] == "heading" and events[j][1] < level
            ),
            None,
        )
        if parent is not None and _section_has_artefact(
            events, parent, events[parent][1]
        ):
            continue
        hollow.append(text)
    return hollow


# --------------------------------------------------------------------------- fixtures

GOOD = """\
## Verify the Bootstrap

Run this first.

```bash
kubectl get nodes
```
"""

HOLLOW = """\
## Verify the Bootstrap

The cluster comes up and everything is fine.

## Next Section
"""

HOLLOW_AT_EOF = """\
## Recovery Path

Reboot and hope.
"""

DIAGRAM_ONLY = """\
## Verification

```mermaid
flowchart TD
  A --> B
```
"""

BLOCK_UNDER_SUBHEADING = """\
## Verify the Bootstrap

Narrative here.

### Check the nodes

```bash
kubectl get nodes
```
"""

BLOCK_BELONGS_TO_NEXT_SECTION = """\
## Verify the Bootstrap

Nothing to run.

## Architecture

```bash
kubectl get pods
```
"""

HEADING_INSIDE_A_FENCE = """\
## Verify the Bootstrap

```bash
# Verify the Bootstrap
kubectl get nodes
```
"""

NARRATIVE_HEADING = """\
## Architecture

Just prose, no commands.
"""

FIX_TABLE = """\
## Recovery Path

| Symptom | Cause | Fix |
|---|---|---|
| Pods stuck Init | markers missing | `kubectl get ds -n gpu-operator` |
"""

TABLE_WITHOUT_CODE = """\
## Recovery Path

| Symptom | Cause | Fix |
|---|---|---|
| Pods stuck Init | markers missing | wait for the operator |
"""

SUBHEADING_INHERITS = """\
## Gotcha 3: it does not work

```bash
kubectl get cm -n monitoring
```

### Diagnosis

The chart owns the ConfigMap.

### Fix

Mount your own.
"""

SUBHEADING_WITH_NOTHING_ANYWHERE = """\
## Gotcha 3: it does not work

Prose only.

### Diagnosis

Also prose only.
"""


def test_the_detector_can_actually_fail() -> None:
    """Pin both directions: a hollow section is flagged, a real one is not."""
    assert hollow_actionable_sections(HOLLOW) == ["Verify the Bootstrap"]
    assert hollow_actionable_sections(HOLLOW_AT_EOF) == ["Recovery Path"]
    assert hollow_actionable_sections(DIAGRAM_ONLY) == ["Verification"]
    assert hollow_actionable_sections(BLOCK_BELONGS_TO_NEXT_SECTION) == [
        "Verify the Bootstrap"
    ]
    assert hollow_actionable_sections(TABLE_WITHOUT_CODE) == ["Recovery Path"]
    assert hollow_actionable_sections(SUBHEADING_WITH_NOTHING_ANYWHERE) == ["Diagnosis"]
    assert hollow_actionable_sections(GOOD) == []
    assert hollow_actionable_sections(BLOCK_UNDER_SUBHEADING) == []
    assert hollow_actionable_sections(NARRATIVE_HEADING) == []
    assert hollow_actionable_sections(FIX_TABLE) == []
    assert hollow_actionable_sections(SUBHEADING_INHERITS) == []


def test_a_heading_inside_a_fence_is_not_a_heading() -> None:
    """`# Verify ...` as a shell comment must not open or close a section.

    Every command block in this corpus is bash, and bash comments start with
    `#`. A fence-blind scanner would read them as headings, which both invents
    hollow sections and truncates real ones.
    """
    assert hollow_actionable_sections(HEADING_INSIDE_A_FENCE) == []


def test_vocabulary_matches_the_gate() -> None:
    """This tripwire must cover exactly what the gate accepts.

    The gate's vocabulary is the attack surface: any word it accepts is a word a
    hollow heading can be built from. If blog-craft widens `_ACTIONABLE` and this
    copy is not widened with it, the new words become the blind spot.
    """
    src = (ROOT / "blog" / "scripts" / "validate_educational.py").read_text(
        encoding="utf-8"
    )
    m = re.search(r"_ACTIONABLE = re\.compile\(\n(.*?)\n\s*re\.IGNORECASE", src, re.S)
    assert m, "could not locate _ACTIONABLE in blog/scripts/validate_educational.py"
    gate_pattern = "".join(
        re.findall(r'"([^"]*)"', m.group(1))
    )
    assert gate_pattern == _ACTIONABLE.pattern, (
        "blog-craft's _ACTIONABLE vocabulary has changed and this tripwire's copy "
        f"has not.\n  gate:     {gate_pattern}\n  tripwire: {_ACTIONABLE.pattern}"
    )


# --------------------------------------------------------------------------- corpus


def test_the_exempt_post_is_still_scanned() -> None:
    """`quality_exempt` must not become a hole in the anti-hollow guard.

    It removes a post from the gate AND the lint layer (a whole-post opt-out,
    unlike `diagram_exempt`). This guard deliberately ignores it.
    """
    exempt = CONTENT / "building" / "06-fun-stuff" / "index.md"
    assert exempt.exists()
    assert "quality_exempt" in exempt.read_text(encoding="utf-8")
    assert exempt in scanned_posts(), (
        "the one quality_exempt post in the corpus is not being scanned — the "
        "exemption has leaked into the tripwire built to backstop it"
    )


def test_the_corpus_has_actionable_sections_to_check() -> None:
    """Guard against a scanner that silently finds nothing."""
    posts = scanned_posts()
    assert len(posts) > 50, f"only {len(posts)} posts scanned; expected the full corpus"
    with_actionable = [p for p in posts if actionable_headings(_body(p))]
    assert len(with_actionable) > 40, (
        f"only {len(with_actionable)} posts carry an actionable heading; the "
        "vocabulary or the scanner is broken"
    )


def _post_id(post: pathlib.Path) -> str:
    return f"{post.parent.parent.name}/{post.parent.name}"


@pytest.mark.parametrize("post", scanned_posts(), ids=_post_id)
def test_actionable_sections_carry_a_fenced_block(post: pathlib.Path) -> None:
    hollow = [
        h
        for h in hollow_actionable_sections(_body(post))
        if (_post_id(post), h) not in PROSE_ONLY_SECTIONS
    ]
    assert not hollow, (
        f"{post.relative_to(ROOT)} has actionable heading(s) with nothing to run "
        f"before the next same-or-higher heading: {hollow}. The gate passes these "
        "because it only matches the heading text. Fix the section — give the "
        "reader a command, or a symptom/cause/fix table — or rename the heading "
        "to what the section actually is. Add to PROSE_ONLY_SECTIONS only if a "
        "command there would have to be invented."
    )


@pytest.mark.parametrize("key", sorted(PROSE_ONLY_SECTIONS), ids=lambda k: k[1][:40])
def test_every_waiver_is_still_real_and_still_needed(key: tuple[str, str]) -> None:
    """A waiver must name a live heading AND still be load-bearing.

    Both directions matter. A waiver pointing at a heading somebody renamed is
    dead text that reads as a considered exception. A waiver for a section that
    has since grown a command is a standing permission nobody re-examined —
    which is how a two-entry list becomes the way things are done here.
    """
    post_id, heading = key
    series, slug = post_id.split("/")
    post = CONTENT / series / slug / "index.md"
    assert post.exists(), f"waiver names a post that does not exist: {post_id}"
    body = _body(post)
    assert heading in actionable_headings(body), (
        f"waived heading {heading!r} is no longer an actionable heading in "
        f"{post_id} — delete the waiver"
    )
    assert heading in hollow_actionable_sections(body), (
        f"{post_id} :: {heading!r} now carries something to run, so the waiver "
        "is obsolete — delete it"
    )


def test_the_waiver_list_stays_small() -> None:
    """Two entries, one post. If this needs raising, the guard is being managed
    rather than met."""
    assert len(PROSE_ONLY_SECTIONS) <= 2, sorted(PROSE_ONLY_SECTIONS)
    assert all(reason.strip() for reason in PROSE_ONLY_SECTIONS.values())
