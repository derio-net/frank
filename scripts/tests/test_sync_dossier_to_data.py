"""Test blog/scripts/sync_dossier_to_data.py against real dossiers.

The sync script reads <dossier_dir>/<slug>/dossier.md and writes
<data_dir>/<slug>.yaml = {primary_sources: [...]}, which the papers §8
references-index reads as .Site.Data.papers.<slug>.primary_sources. Output
shape is pinned by the spec.

History worth keeping, because it is the reason this file was rewritten:
the script used to live at scripts/sync-dossier-to-data.py with a per-slug
CLI (`<slug> --output <path>`) and a module API of DATA_DIR / sync_all() /
check_drift(). The blog-craft extraction replaced all of it with a
config-driven `--config <.blog-craft.yaml> [--check]` and a single
sync(root, dossier_dir, data_dir, check) function. This test kept asserting
the old contract, so all five cases failed continuously from 2026-07-04 to
2026-07-26 — a stale CONTRACT, not merely a stale path. Nothing noticed
because no CI ran scripts/tests/; that gap is what the repo-tripwires
workflow closes.

Directories are read from .blog-craft.yaml rather than hardcoded, so this
tracks the config instead of drifting from it a second time.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "blog" / "scripts" / "sync_dossier_to_data.py"
CONFIG = REPO_ROOT / ".blog-craft.yaml"

# Fail specifically if either moves again, rather than letting every case below
# die on an opaque FileNotFoundError or ModuleNotFoundError.
assert SCRIPT.is_file(), f"sync script missing at {SCRIPT.relative_to(REPO_ROOT)} — it moved again"
assert CONFIG.is_file(), f"blog-craft config missing at {CONFIG.relative_to(REPO_ROOT)}"


def _cfg_dirs() -> tuple[str, str]:
    papers = ((yaml.safe_load(CONFIG.read_text()).get("content_types") or {})
              .get("papers") or {})
    return (papers.get("dossier_dir", "docs/papers-dossiers"),
            papers.get("data_dir", "blog/data/papers"))


DOSSIER_DIR, DATA_DIR = _cfg_dirs()


def _load_sync_module():
    """Import the script. blog/scripts must be on sys.path for dossier_parser,
    which the script imports as a sibling module."""
    from importlib.util import module_from_spec, spec_from_file_location
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec = spec_from_file_location("sync_dossier_to_data", SCRIPT)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(SCRIPT.parent))


def _dossier_slugs() -> list[str]:
    d = REPO_ROOT / DOSSIER_DIR
    return sorted(p.name for p in d.iterdir()
                  if p.is_dir() and (p / "dossier.md").is_file())


@pytest.fixture
def sandbox(tmp_path):
    """A fake repo root: real dossiers symlinked in, data dir free to be written.

    sync() joins its dir arguments onto root, so the clean way to keep repo
    state untouched is a temp root that points at the real dossiers rather than
    absolute-path gymnastics.
    """
    (tmp_path / DOSSIER_DIR).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / DOSSIER_DIR).symlink_to(REPO_ROOT / DOSSIER_DIR)
    return tmp_path


def test_sync_writes_spec_pinned_shape(sandbox):
    """Paper 09's data file carries the spec-pinned source shape."""
    mod, root = _load_sync_module(), sandbox
    problems = mod.sync(root, DOSSIER_DIR, DATA_DIR)
    assert problems == [], problems

    target = root / DATA_DIR / "09-secrets-bootstrap.yaml"
    assert target.is_file(), f"no data file written for paper 09 (got {list((root / DATA_DIR).glob('*'))})"
    data = yaml.safe_load(target.read_text())
    assert "primary_sources" in data
    sources = data["primary_sources"]
    assert len(sources) == 9
    s0 = sources[0]
    assert set(s0.keys()) >= {"title", "url", "type", "quoted_passages", "relevance"}
    assert s0["type"] in {"vendor-docs", "paper", "postmortem", "talk", "benchmark"}


def test_sync_is_idempotent(sandbox):
    """Re-running must produce byte-identical output, or --check false-alarms."""
    mod, root = _load_sync_module(), sandbox
    outs = []
    for _ in range(2):
        mod.sync(root, DOSSIER_DIR, DATA_DIR)
        outs.append((root / DATA_DIR / "09-secrets-bootstrap.yaml").read_text())
    assert outs[0] == outs[1], "repeat sync produced different output"


def test_sync_covers_every_dossier(sandbox):
    mod, root = _load_sync_module(), sandbox
    mod.sync(root, DOSSIER_DIR, DATA_DIR)
    generated = sorted(p.stem for p in (root / DATA_DIR).glob("*.yaml"))
    assert generated == _dossier_slugs(), (
        f"data files do not match dossiers\n  dossiers: {_dossier_slugs()}\n  generated: {generated}"
    )


def test_check_reports_clean_after_sync(sandbox):
    mod, root = _load_sync_module(), sandbox
    mod.sync(root, DOSSIER_DIR, DATA_DIR)
    assert mod.sync(root, DOSSIER_DIR, DATA_DIR, check=True) == []


def test_check_reports_the_tampered_file(sandbox):
    """--check must name the drifted file, not just exit non-zero."""
    mod, root = _load_sync_module(), sandbox
    mod.sync(root, DOSSIER_DIR, DATA_DIR)

    victim = next((root / DATA_DIR).glob("*.yaml"))
    victim.write_text("primary_sources: []\n")

    problems = mod.sync(root, DOSSIER_DIR, DATA_DIR, check=True)
    assert len(problems) == 1, problems
    assert victim.stem in problems[0], problems


def test_cli_check_contract_against_committed_state():
    """Exercise the REAL CLI, so an argument-contract change cannot pass unnoticed.

    This is the guard whose absence let the rewrite above go undetected: every
    other case here calls sync() directly, so all five kept passing the day the
    CLI changed shape. Also asserts the committed data files are in sync.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(CONFIG), "--check"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"committed dossier data is stale, or the CLI contract changed.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
