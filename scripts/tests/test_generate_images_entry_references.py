"""Guard that an image entry's `references:` anchors actually reach the model.

REGRESSION HISTORY — this is why the test exists. frank's original
`scripts/generate-all-images.py` passed the entry's `references:` images to the
model after the master character sheet:

    contents = [full_prompt, reference_image]
    contents.extend(explicit_images)   # from the entry's `references:` field

The P7 blog-craft cutover (42916bf9, #600) replaced it with
`blog/scripts/generate-images.py`, whose `_gen_bytes` appended ONLY the master
reference. The `references:` field silently became decorative on all 84 entries.

It went unnoticed because the cutover proved "image-compose parity" on the
composed PROMPT TEXT (smoke-image-compose) — the one thing that had not
regressed. Nothing asserted which IMAGES were sent. Covers then drifted off the
declared clothing/torso variant, because only the text layer carried it.

So these guards pin the payload, not the prose:
  - entry references resolve relative to the repo root (where .blog-craft.yaml
    and .reference-pool/ live), matching every entry's `output:` convention;
  - a missing anchor is SKIPPED, not fatal (a stale path must not block a cover);
  - ORDER is load-bearing: the master character sheet stays FIRST, because the
    composed `reference_guidance` prose tells the model the first image is
    canonical for the face and later ones are clothing/pose anchors only.

LOCAL guards (frank does not run scripts/tests/ in CI). Pure — no network, no
API key, no PIL decode.
"""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "blog/scripts/generate-images.py"


def _mod():
    """Import the hyphenated script by path (not importable as a module name)."""
    spec = importlib.util.spec_from_file_location("generate_images", GEN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_entry_references_resolve_against_repo_root(tmp_path):
    m = _mod()
    (tmp_path / ".reference-pool/building/subjects").mkdir(parents=True)
    a = tmp_path / ".reference-pool/building/subjects/a.png"
    a.write_bytes(b"x")
    entry = {"references": [".reference-pool/building/subjects/a.png"]}
    assert m.entry_reference_paths(entry, tmp_path) == [a]


def test_missing_reference_is_skipped_not_fatal(tmp_path):
    """A stale path in one entry must not block generating its cover."""
    m = _mod()
    (tmp_path / "refs").mkdir()
    good = tmp_path / "refs/good.png"
    good.write_bytes(b"x")
    entry = {"references": ["refs/missing.png", "refs/good.png"]}
    assert m.entry_reference_paths(entry, tmp_path) == [good]


def test_declared_order_is_preserved(tmp_path):
    m = _mod()
    (tmp_path / "refs").mkdir()
    for n in ("one", "two", "three"):
        (tmp_path / f"refs/{n}.png").write_bytes(b"x")
    entry = {"references": ["refs/two.png", "refs/one.png", "refs/three.png"]}
    got = [p.name for p in m.entry_reference_paths(entry, tmp_path)]
    assert got == ["two.png", "one.png", "three.png"]


def test_absent_or_empty_references_yields_nothing(tmp_path):
    m = _mod()
    assert m.entry_reference_paths({}, tmp_path) == []
    assert m.entry_reference_paths({"references": []}, tmp_path) == []
    assert m.entry_reference_paths({"references": None}, tmp_path) == []


def test_gen_bytes_takes_root_so_entry_refs_can_resolve():
    """The regression was structural: _gen_bytes had no way to resolve the
    entry's repo-root-relative reference paths, so it could not pass them."""
    import inspect
    m = _mod()
    params = list(inspect.signature(m._gen_bytes).parameters)
    assert "entry" in params and "root" in params, params


def test_master_reference_stays_first_in_the_payload():
    """ORDER guard: reference_guidance declares the FIRST image canonical for the
    face; entry anchors must be appended AFTER it, never before."""
    import inspect
    m = _mod()
    src = inspect.getsource(m._gen_bytes)
    master_at = src.index("contents.append(Image.open(ref))")
    entry_at = src.index("entry_reference_paths(entry, root)")
    assert master_at < entry_at, "entry references must be appended after the master sheet"
