# Staging-vCluster e2e release gate — frank plan

Implements the frank half of the staging-vCluster release gate (spec:
`docs/superpowers/specs/2026-06-15--cicd--staging-vcluster-gate-design.md`). The runs-fr half
is runs-fr#21 (merged 2026-08-27), plus a one-job permission fix PR in `derio-net/runs-fr`.

## Shape after the 2026-09-14 revision

Phases 1–6 (June) authored and schema-validated the vCluster, the AppProject destination, the
`runs-fr-staging` Application, the contract and validator, the Tekton gate, and its App-of-Apps
registration. They stay complete.

Re-checking that work against current `main` and the live cluster found runtime defects that
schema validation could not see. Each is in the spec's revision table. Phases 7–10 fix them, and
the manual phase moves to 11:

| Phase | What it fixes |
|-------|---------------|
| 7 | The argo-cd#26529 exclusion covers the staging URL; destination by name; ArgoCD can read the private runs-fr chart |
| 8 | Contract v2: promote records last-green; git goes over HTTPS with `frank-gitops-push` (no SSH Secret) |
| 9 | Tekton reaches the vCluster through a chart-exported kubeconfig (no manual Secret); the smoke Job runs with the app's RBAC fetched at the gated sha; per-app serialization; Telegram notify on red |
| 10 | The `staging-gate-runs-fr` trigger on `github-listener`, its HMAC ExternalSecret, and the `webhooks.yaml` declaration |
| 11 (manual) | Registration after the exclusion is live, the delivery-path and forge wiring, then the green and red Test Plan |

## Tests

The tripwire suite (`uv run --group dev pytest scripts/tests -q`) is the test runner for every
new phase, and CI runs it (`repo-tripwires.yml`). New assertions live in
`scripts/tests/test_staging_gate_manifests.py` and `test_staging_gate_contract.py`, and extend
`test_argocd_vcluster_pod_exclusion.py`. Tests that render charts shell out to `helm template`
and fail closed. Baseline before phase 7: 776 passed, 1 xfailed.

The June phases used a fetched `.bin/` toolchain because the `dev` devcontainer had no helm.
This run uses host-worktree isolation, where helm, kubeconform and uv are on PATH.
`scripts/staging-gate/ensure-tools.sh` remains for devcontainer runs.

## Agentic vs runtime split

Phases 7–10 author manifests and prove structure. They never touch the live cluster. Runtime
proof belongs to phase 11 and the post-merge Test Plan. Nothing agentic depends on phase 11.

## Dependencies

1 and 4 are roots. 2 → [1]; 3 → [1,2]; 5 → [4]; 6 → [1,3,4,5]; 7 → [6]; 8 → [6]; 9 → [8];
10 → [8,9]; 11 (manual) → [7,8,9,10].

## Cross-repo note

`runs-fr-staging` sources the runs-fr chart from the runs-fr repo read-only. The only runs-fr
change in this round is the `trigger-gate` job's `contents: write`, in its own PR, merged only
after the webhook exists.
