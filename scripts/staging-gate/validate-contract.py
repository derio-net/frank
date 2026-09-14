#!/usr/bin/env python3
"""Validate per-app staging-gate contracts.

Each app that rides the staging-gate declares a contract at
apps/staging-gate/registry/<app>.yaml. The Tekton gate Pipeline reads it to learn
what to build/deploy/smoke/promote. This validator enforces the contract SHAPE
(required keys + basic types) — not the existence of the referenced targets (the
prod app may be a paired follow-up).

Run via the exec-bridge:
  fr isolation exec --branch feat/staging-vcluster-gate -- \
    bash -lc 'uv run --quiet --with pyyaml python scripts/staging-gate/validate-contract.py'

Exit 0 = all contracts valid; non-zero = a problem (including "no contracts found").
"""
from __future__ import annotations

import glob
import sys

import yaml

REQUIRED: dict[str, type] = {
    "app": str,            # short name, used for labels + the PipelineRun param
    "sourceRepo": str,     # owner/repo whose merges trigger the gate
    "image": str,          # ghcr image repository (gate appends :sha-<commit>)
    "chartRepo": str,      # git URL of the Helm chart
    "chartPath": str,      # path to the chart within chartRepo
    "stagingApp": str,     # ArgoCD Application name for staging
    "stagingValuesPath": str,  # frank path to the staging values file (image.tag bumped here)
    "smokeImage": str,     # in-cluster smoke-test image (exit 0 = pass)
    "smokeNamespace": str,  # namespace in the staging vCluster to run the smoke Job
    "smokeRbacUrl": str,   # the app's smoke RBAC manifest, containing the literal {sha}
    "promotedRecordPath": str,  # frank path to the gate-owned last-green record
}

# Retired by the 2026-09-14 spec revision: runs-fr has no prod app yet, so promote
# now records the last-green sha at `promotedRecordPath` instead of bumping a
# not-yet-existing prod values file. See the Revision table in
# docs/superpowers/specs/2026-06-15--cicd--staging-vcluster-gate-design.md.
RETIRED: dict[str, str] = {
    "prodApp": "replaced by 'promotedRecordPath' (spec revision 2026-09-14)",
    "prodValuesPath": "replaced by 'promotedRecordPath' (spec revision 2026-09-14)",
    "prodValuesKey": "replaced by 'promotedRecordPath' (spec revision 2026-09-14)",
}

REGISTRY_GLOB = "apps/staging-gate/registry/*.yaml"


def validate_one(path: str) -> list[str]:
    errs: list[str] = []
    try:
        doc = yaml.safe_load(open(path)) or {}
    except yaml.YAMLError as e:  # noqa: PERF203
        return [f"{path}: YAML parse error: {e}"]
    if not isinstance(doc, dict):
        return [f"{path}: top-level must be a mapping"]
    for key, typ in REQUIRED.items():
        if key not in doc:
            errs.append(f"{path}: missing required key '{key}'")
        elif not isinstance(doc[key], typ) or (typ is str and not doc[key].strip()):
            errs.append(f"{path}: key '{key}' must be a non-empty {typ.__name__}")
    for key, reason in RETIRED.items():
        if key in doc:
            errs.append(
                f"{path}: key '{key}' is retired and must be removed — {reason}. "
                "See docs/superpowers/specs/2026-06-15--cicd--staging-vcluster-gate-design.md "
                "(Revision 2026-09-14 table)."
            )
    # P8 review (p8-m5-sha-placeholder-cli): run-smoke substitutes {sha} into
    # smokeRbacUrl. Enforced here (not only in the pytest fixture) so the CLI
    # itself catches an onboarder's typo before a gate run does.
    smoke_rbac_url = doc.get("smokeRbacUrl")
    if isinstance(smoke_rbac_url, str) and "{sha}" not in smoke_rbac_url:
        errs.append(
            f"{path}: key 'smokeRbacUrl' must contain the literal placeholder '{{sha}}': "
            f"{smoke_rbac_url!r}"
        )
    return errs


def main() -> int:
    paths = sorted(glob.glob(REGISTRY_GLOB))
    if not paths:
        print(f"FAIL: no contracts found at {REGISTRY_GLOB}", file=sys.stderr)
        return 1
    all_errs: list[str] = []
    for p in paths:
        all_errs += validate_one(p)
    if all_errs:
        for e in all_errs:
            print(e, file=sys.stderr)
        print(f"FAIL: {len(all_errs)} problem(s) across {len(paths)} contract(s)", file=sys.stderr)
        return 1
    print(f"PASS: {len(paths)} contract(s) valid: {', '.join(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
