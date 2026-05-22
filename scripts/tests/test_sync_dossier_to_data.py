"""Test scripts/sync-dossier-to-data.py against real dossiers.

The sync script reads docs/papers-dossiers/<slug>/dossier.md
and writes blog/data/papers/<slug>.yaml. Output shape is
pinned by the spec.
"""
from pathlib import Path
import subprocess
import sys

import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "sync-dossier-to-data.py"
DATA_DIR = REPO_ROOT / "blog" / "data" / "papers"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_sync_single_slug_writes_data_file(tmp_path, monkeypatch):
    # Sync Paper 09 into a temp data dir to avoid clobbering main repo state during tests
    target = tmp_path / "09-secrets-bootstrap.yaml"
    proc = run("09-secrets-bootstrap", "--output", str(target))
    assert proc.returncode == 0, proc.stderr
    data = yaml.safe_load(target.read_text())
    assert "primary_sources" in data
    sources = data["primary_sources"]
    assert len(sources) == 9
    # Spec-pinned shape per source
    s0 = sources[0]
    assert set(s0.keys()) >= {"title", "url", "type", "quoted_passages", "relevance"}
    assert s0["type"] in {"vendor-docs", "paper", "postmortem", "talk", "benchmark"}


def test_sync_emits_idempotent_yaml(tmp_path):
    t1 = tmp_path / "a.yaml"
    t2 = tmp_path / "b.yaml"
    run("09-secrets-bootstrap", "--output", str(t1))
    run("09-secrets-bootstrap", "--output", str(t2))
    assert t1.read_text() == t2.read_text(), "repeat sync produced different output"


def _load_sync_module():
    """Load scripts/sync-dossier-to-data.py via importlib (hyphenated filename)."""
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location(
        "sync_dossier_to_data",
        REPO_ROOT / "scripts" / "sync-dossier-to-data.py",
    )
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sync_all_covers_every_dossier(tmp_path, monkeypatch):
    mod = _load_sync_module()
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    # Count dossiers
    dossier_count = len([
        d for d in (REPO_ROOT / "docs" / "papers-dossiers").iterdir()
        if d.is_dir() and (d / "dossier.md").exists()
    ])
    # Invoke programmatically (subprocess won't see the monkeypatch)
    mod.sync_all()
    generated = list(tmp_path.glob("*.yaml"))
    assert len(generated) == dossier_count, (
        f"expected {dossier_count} data files, generated {len(generated)}"
    )


def test_check_clean_exits_zero(tmp_path, monkeypatch):
    """After --all, --check must pass."""
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location(
        "sync_dossier_to_data",
        REPO_ROOT / "scripts" / "sync-dossier-to-data.py",
    )
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    mod.sync_all()
    rc, diff = mod.check_drift()
    assert rc == 0, f"expected clean, got diff:\n{diff}"


def test_check_dirty_exits_nonzero_with_diff(tmp_path, monkeypatch):
    """Tamper with one data file, expect rc=1 + a unified diff."""
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location(
        "sync_dossier_to_data",
        REPO_ROOT / "scripts" / "sync-dossier-to-data.py",
    )
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    mod.sync_all()
    # Corrupt one file
    victim = next(tmp_path.glob("*.yaml"))
    victim.write_text("primary_sources: []\n")
    rc, diff = mod.check_drift()
    assert rc == 1
    assert victim.name in diff or victim.stem in diff
