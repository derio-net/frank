"""Contract schema v2 tripwire (plan 2026-06-15-staging-vcluster-gate, phase 8).

The June contract shape (`prodApp`/`prodValuesPath`/`prodValuesKey`) is retired by
the 2026-09-14 spec revision: `docs/superpowers/specs/2026-06-15--cicd--staging-
vcluster-gate-design.md`. Promote now records the last-green sha at
`promotedRecordPath` instead of bumping a not-yet-existing prod app. This guards:

  (a) `scripts/staging-gate/validate-contract.py` exits 0 against the live registry;
  (b) the validator REJECTS a contract still carrying the retired prod* keys, and
      REQUIRES `promotedRecordPath` + `smokeRbacUrl`, exercised via tmp-dir fixtures
      fed straight to the importable `validate_one`, not the live registry;
  (c) every live registry entry's `stagingValuesPath` and `promotedRecordPath`
      resolve to real files in the repo, and `smokeRbacUrl` still carries the
      literal `{sha}` placeholder phase 9's run-smoke task substitutes.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO / "scripts/staging-gate/validate-contract.py"
REGISTRY_GLOB = "apps/staging-gate/registry/*.yaml"

RETIRED_KEYS = ("prodApp", "prodValuesPath", "prodValuesKey")


def _load_validator():
    spec = importlib.util.spec_from_file_location("staging_gate_validate_contract", VALIDATOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


validate_contract = _load_validator()


def _valid_v2_contract() -> dict:
    return {
        "app": "runs-fr",
        "sourceRepo": "derio-net/runs-fr",
        "image": "ghcr.io/derio-net/runs-fr",
        "chartRepo": "https://github.com/derio-net/runs-fr.git",
        "chartPath": "charts/runs-fr",
        "stagingApp": "runs-fr-staging",
        "stagingValuesPath": "apps/staging-gate/runs-fr/staging-values.yaml",
        "smokeImage": "ghcr.io/derio-net/runs-fr-smoke",
        "smokeNamespace": "runs-fr",
        "smokeRbacUrl": (
            "https://api.github.com/repos/derio-net/runs-fr/contents/test/e2e/rbac.yaml?ref={sha}"
        ),
        "promotedRecordPath": "apps/staging-gate/runs-fr/promoted.yaml",
    }


def _write(tmp_path: Path, doc: dict) -> str:
    p = tmp_path / "contract.yaml"
    p.write_text(yaml.safe_dump(doc))
    return str(p)


def test_validator_passes_on_the_live_registry():
    out = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert out.returncode == 0, f"stdout:\n{out.stdout}\nstderr:\n{out.stderr}"


def test_validate_one_accepts_a_valid_v2_contract(tmp_path):
    assert validate_contract.validate_one(_write(tmp_path, _valid_v2_contract())) == []


def test_validate_one_rejects_the_retired_prod_keys(tmp_path):
    doc = _valid_v2_contract()
    doc.update(
        {
            "prodApp": "runs-fr",
            "prodValuesPath": "apps/runs-fr/values.yaml",
            "prodValuesKey": "image.tag",
        }
    )
    errs = validate_contract.validate_one(_write(tmp_path, doc))
    assert errs, "expected the retired prod* keys to be rejected"
    joined = "\n".join(errs)
    for key in RETIRED_KEYS:
        assert key in joined, f"expected {key!r} named in the error output: {joined}"
    assert "2026-09-14" in joined, (
        f"expected the spec revision date to point at the design doc: {joined}"
    )


@pytest.mark.parametrize("missing_key", ["promotedRecordPath", "smokeRbacUrl"])
def test_validate_one_requires_the_v2_keys(tmp_path, missing_key):
    doc = _valid_v2_contract()
    del doc[missing_key]
    errs = validate_contract.validate_one(_write(tmp_path, doc))
    assert any(missing_key in e for e in errs), f"expected a {missing_key!r} error, got: {errs}"


def test_validate_one_rejects_a_smoke_rbac_url_missing_the_sha_placeholder(tmp_path):
    """P8 review (p8-m5-sha-placeholder-cli): the {sha} check previously lived
    only in test_registry_entries_reference_real_paths_and_the_sha_placeholder
    (pytest, against the live registry) — an onboarder running the CLI validator
    directly got no warning. Move the check into validate_one itself."""
    doc = _valid_v2_contract()
    doc["smokeRbacUrl"] = "https://api.github.com/repos/derio-net/runs-fr/contents/test/e2e/rbac.yaml"
    errs = validate_contract.validate_one(_write(tmp_path, doc))
    assert any("smokeRbacUrl" in e and "{sha}" in e for e in errs), (
        f"expected a smokeRbacUrl/{{sha}} error, got: {errs}"
    )


def _registry_docs() -> dict:
    return {p: yaml.safe_load(p.read_text()) for p in sorted(REPO.glob(REGISTRY_GLOB))}


def test_registry_entries_reference_real_paths_and_the_sha_placeholder():
    docs = _registry_docs()
    assert docs, f"no registry contracts found at {REGISTRY_GLOB}"
    for path, doc in docs.items():
        staging_values = REPO / doc["stagingValuesPath"]
        assert staging_values.is_file(), (
            f"{path}: stagingValuesPath does not exist: {staging_values}"
        )
        promoted = REPO / doc["promotedRecordPath"]
        assert promoted.is_file(), (
            f"{path}: promotedRecordPath does not exist: {promoted}"
        )
        assert "{sha}" in doc["smokeRbacUrl"], (
            f"{path}: smokeRbacUrl must carry the literal placeholder {{sha}}: "
            f"{doc['smokeRbacUrl']}"
        )
