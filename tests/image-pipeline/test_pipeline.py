"""Tests for the modular image-prompt pipeline.

Covers:
  - Pure functions in scripts/generate-all-images.py
    (_key_to_series, _key_to_torso_default, _resolve_reference_guidance,
    _sha256_short, load_pool_refs)
  - YAML structural integrity (no dead series-banner block, required
    top-level keys present)
  - Per-image-entry validity (torso_variant in range, mood is a string,
    every `references:` path exists)

Run:
    uv run --with pytest --with pyyaml --with google-genai --with pillow \\
      python -m pytest tests/image-pipeline/ -v

google-genai / pillow are imported at module load of the script under test,
so they're required even though the tests never touch the model.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate-all-images.py"
YAML_PATH = REPO_ROOT / "blog" / "prompt_for_images.yaml"


@pytest.fixture(scope="session")
def script():
    """Load scripts/generate-all-images.py as a module (hyphen in filename
    prevents normal `import`, so we go through importlib)."""
    spec = importlib.util.spec_from_file_location("gen_images", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_images"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def cfg():
    """Parsed prompt_for_images.yaml."""
    with open(YAML_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def entries(cfg):
    return cfg["images"]


@pytest.fixture(scope="session")
def torso_variants(cfg):
    """Normalised torso_variants — list form regardless of input shape."""
    raw = cfg.get("torso_variants", {}) or {}
    return {k: ([v] if isinstance(v, str) else list(v or [])) for k, v in raw.items()}


@pytest.fixture(scope="session")
def moods(cfg):
    return cfg.get("moods", {}) or {}


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


class TestKeyToSeries:
    def test_paper_prefix(self, script):
        assert script._key_to_series("paper-04-cover") == "papers"
        assert script._key_to_series("paper-00-cover") == "papers"

    def test_building_prefix(self, script):
        assert script._key_to_series("building-09-secrets") == "building"

    def test_ops_prefix(self, script):
        assert script._key_to_series("ops-02-storage-backups") == "operating"

    def test_unknown_prefix_returns_none(self, script):
        assert script._key_to_series("banner-thin") is None
        assert script._key_to_series("favicon") is None

    def test_operating_prefix_not_recognised(self, script):
        # `operating-` is NOT a supported prefix — `ops-` is the firm
        # convention. If this changes, _key_to_torso_default must change
        # too (they share the prefix table).
        assert script._key_to_series("operating-foo") is None


class TestKeyToTorsoDefault:
    def test_explicit_series_wins(self, script):
        assert script._key_to_torso_default("paper-04-cover", "building") == "building"

    def test_falls_back_to_key_prefix(self, script):
        assert script._key_to_torso_default("paper-04-cover", None) == "papers"
        assert script._key_to_torso_default("ops-02-foo", None) == "operating"
        assert script._key_to_torso_default("building-99-foo", None) == "building"

    def test_unknown_key_returns_generic(self, script):
        assert script._key_to_torso_default("banner-thin", None) == "generic"
        assert script._key_to_torso_default("favicon", None) == "generic"

    def test_invalid_series_falls_through(self, script):
        # An unknown series value still falls through to the key-prefix path.
        assert script._key_to_torso_default("paper-04-cover", "unknown") == "papers"

    def test_consistent_with_key_to_series(self, script):
        # Homogenisation guarantee: both functions recognise the SAME prefixes.
        for k in ("paper-x", "building-x", "ops-x", "banner-x", "favicon"):
            series = script._key_to_series(k)
            torso = script._key_to_torso_default(k, None)
            if series is None:
                assert torso == "generic", f"{k}: series=None but torso={torso}"
            else:
                assert torso == series, f"{k}: series={series} but torso={torso}"


class TestResolveReferenceGuidance:
    def test_string_form(self, script):
        assert script._resolve_reference_guidance("hello") == "hello"

    def test_dict_form_with_base(self, script):
        assert script._resolve_reference_guidance({"base": "abc"}) == "abc"

    def test_dict_form_missing_base(self, script):
        # Empty dict → empty string. No crash.
        assert script._resolve_reference_guidance({}) == ""

    def test_dict_form_ignores_extra_keys(self, script):
        # The legacy `series.<name>.banner` block is silently ignored.
        raw = {"base": "x", "series": {"papers": {"banner": "irrelevant.png"}}}
        assert script._resolve_reference_guidance(raw) == "x"


class TestSha256Short:
    def test_default_length(self, script):
        assert len(script._sha256_short(b"hello")) == 12

    def test_stable(self, script):
        assert script._sha256_short(b"x") == script._sha256_short(b"x")

    def test_custom_length(self, script):
        assert len(script._sha256_short(b"x", n=16)) == 16

    def test_collision_resistance_short_circuit(self, script):
        # Sanity: trivially different inputs produce different shortnames.
        assert script._sha256_short(b"a") != script._sha256_short(b"b")


class TestLoadPoolRefs:
    def test_returns_empty_when_disabled(self, script):
        refs = script.load_pool_refs("paper-04-cover", 0, 0, random.Random(0))
        assert refs == []

    def test_respects_series_partition(self, script):
        # Whatever it returns must be in the right pool subdir.
        refs = script.load_pool_refs(
            "paper-04-cover", n_generic=1, n_series=2, rng=random.Random(0)
        )
        for r in refs:
            assert ".reference-pool/generic" in str(r) or ".reference-pool/papers" in str(r)

    def test_unknown_key_falls_back_to_generic_only(self, script):
        # An unknown-prefix key gets generic refs but no series refs.
        refs = script.load_pool_refs(
            "banner-thin", n_generic=1, n_series=2, rng=random.Random(0)
        )
        for r in refs:
            assert ".reference-pool/generic" in str(r)

    def test_does_not_crash_on_missing_pool(self, script, tmp_path, monkeypatch):
        # If POOL_DIR points at a non-existent path, load returns empty
        # without raising.
        monkeypatch.setattr(script, "POOL_DIR", tmp_path / "missing-pool")
        refs = script.load_pool_refs("paper-04-cover", 1, 2, random.Random(0))
        assert refs == []


# ---------------------------------------------------------------------------
# YAML structural integrity
# ---------------------------------------------------------------------------


class TestYamlStructure:
    def test_required_top_level_keys(self, cfg):
        for k in (
            "base_character",
            "base_atmosphere",
            "reference_guidance",
            "torso_variants",
            "moods",
            "images",
        ):
            assert k in cfg, f"missing top-level key: {k}"

    def test_no_dead_series_banner_block(self, cfg):
        """The auto-attached series banner wiring was removed. References
        are now picked explicitly per image entry. Re-introducing the
        wiring would silently break that contract."""
        assert "series" not in cfg["reference_guidance"], (
            "reference_guidance.series wiring should be gone; "
            "refs are now picked explicitly per entry"
        )

    def test_torso_variants_complete(self, torso_variants):
        for k in ("generic", "papers", "building", "operating"):
            assert k in torso_variants, f"missing torso bucket: {k}"
            assert len(torso_variants[k]) >= 1, f"torso bucket '{k}' is empty"

    def test_images_is_a_list(self, entries):
        assert isinstance(entries, list)
        assert len(entries) > 0


# ---------------------------------------------------------------------------
# Per-entry validity
# ---------------------------------------------------------------------------


class TestEntries:
    def test_every_entry_has_required_fields(self, entries):
        for e in entries:
            for f in ("key", "output", "prompt"):
                assert f in e, f"entry {e.get('key', '<?>')}: missing required field '{f}'"

    def test_no_duplicate_keys(self, entries):
        keys = [e["key"] for e in entries]
        dupes = {k for k in keys if keys.count(k) > 1}
        assert not dupes, f"duplicate keys: {sorted(dupes)}"

    def test_every_torso_variant_in_range(self, entries, torso_variants, script):
        """If an entry sets torso_variant as an int, it must be a valid
        index into the relevant torso_variants list."""
        for e in entries:
            tv = e.get("torso_variant")
            if tv is None or not isinstance(tv, int):
                continue
            torso_key = e.get("torso") or script._key_to_torso_default(
                e["key"], e.get("series")
            )
            opts = torso_variants.get(torso_key, [])
            assert 0 <= tv < len(opts), (
                f"{e['key']}: torso_variant={tv} out of range "
                f"for torso '{torso_key}' ({len(opts)} options)"
            )

    def test_every_mood_is_string(self, entries):
        for e in entries:
            if "mood" in e:
                assert isinstance(e["mood"], str), (
                    f"{e['key']}: mood must be a string (preset key or "
                    f"free-form), got {type(e['mood']).__name__}"
                )

    def test_every_reference_path_exists(self, entries):
        """Explicit `references:` paths are the contract. A broken path
        means the script silently drops the ref (with a WARN), producing
        worse output."""
        missing = []
        for e in entries:
            for r in e.get("references", []) or []:
                p = REPO_ROOT / r
                if not p.exists():
                    missing.append(f"{e['key']}: {r}")
        assert not missing, "broken references:\n  " + "\n  ".join(missing)

    def test_no_legacy_base_style_fallback_left(self, cfg):
        """The legacy `base_style` top-level key is gone — `base_character`
        is the only path. If someone re-adds `base_style`, the test fails
        so we have an opportunity to discuss it instead of silently
        accumulating two parallel keys."""
        assert "base_style" not in cfg, (
            "`base_style` is a removed legacy key; use `base_character`"
        )
