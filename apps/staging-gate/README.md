# staging-gate

The automated release gate (spec:
`docs/superpowers/specs/2026-06-15--cicd--staging-vcluster-gate-design.md`). Each gated app's
merge to `main` is built (GHA, per-commit image), deployed into the **`staging` vCluster** via
ArgoCD, exercised by an **in-cluster e2e smoke-test**, and — only if green — **auto-promoted**
to Frank production by a declarative image-ref bump.

## Layout

```
apps/staging-gate/
  registry/<app>.yaml   # per-app CONTRACT (data; validated, NOT applied to the cluster)
  <app>/staging-values.yaml  # per-app staging Helm values (image.tag is gate-owned)
  <app>/promoted.yaml   # per-app last-green RECORD (data, gate-owned, never hand-edited)
  tekton/               # the gate Pipeline + Tasks + triggers (THIS is what ArgoCD applies)
  README.md
```

The App-of-Apps Application for staging-gate points ONLY at `tekton/` — `registry/` and the
per-app values are data consumed by the pipeline / the `<app>-staging` ArgoCD app, not Kubernetes
objects.

## Onboarding an app

1. Add `registry/<app>.yaml` (schema below) + `<app>/staging-values.yaml` +
   `<app>/promoted.yaml` (gate-owned, `sha`/`image`/`pipelineRun`/`promotedAt` all `null`).
2. Add an `<app>-staging` ArgoCD Application (`apps/root/templates/<app>-staging.yaml`) deploying
   the chart into the staging vCluster, pinned to `<app>/staging-values.yaml`.
3. Ship an in-cluster smoke-test image (`smokeImage`) that exits 0 (pass) / non-zero (fail), plus
   an RBAC manifest reachable at `smokeRbacUrl`.
4. Add the per-commit image build + the gate trigger (GHA `repository_dispatch` action
   `staging-gate`) in the app repo.

Validate: `uv run --with pyyaml python scripts/staging-gate/validate-contract.py`.

## Contract schema (`registry/<app>.yaml`)

| key | meaning |
|-----|---------|
| `app` | short name (PipelineRun param + labels) |
| `sourceRepo` | `owner/repo` whose `main` merges trigger the gate |
| `image` | GHCR image repository (gate appends `:sha-<commit>`) |
| `chartRepo` | git URL of the Helm chart |
| `chartPath` | chart path within `chartRepo` |
| `stagingApp` | ArgoCD Application name for staging |
| `stagingValuesPath` | frank path to the staging values file (gate bumps `image.tag` here) |
| `smokeImage` | in-cluster smoke-test image (exit 0 = pass) |
| `smokeNamespace` | namespace in the staging vCluster to run the smoke Job |
| `smokeRbacUrl` | URL of the app's smoke RBAC manifest; contains the literal `{sha}`, substituted by run-smoke |
| `promotedRecordPath` | frank path to the gate-owned last-green record (`promote` writes it) |

The validator checks the contract's SHAPE, not the existence of the referenced remote targets
(`smokeRbacUrl`'s repo content, `chartRepo`) — but `stagingValuesPath` and `promotedRecordPath`
are checked for real (`scripts/tests/test_staging_gate_contract.py`), since both live in this
repo and a typo there is silent until a gate run.

**Retired (2026-09-14):** `prodApp`, `prodValuesPath`, `prodValuesKey`. runs-fr has no prod app
yet, so promote records the last-green sha at `promotedRecordPath` instead of bumping a
not-yet-existing prod values file; a contract still carrying the retired keys is rejected with a
pointer to the spec's Revision table. A prod-app bump returns as an optional key once a gated app
has one.

### `promoted.yaml` (`<app>/promoted.yaml`)

Gate-owned, never hand-edited. `promote` overwrites it in place after a green `run-smoke`:

| key | meaning |
|-----|---------|
| `sha` | the gated commit sha |
| `image` | the full image ref that passed (`<image>:sha-<sha>`) |
| `pipelineRun` | the `staging-gate` PipelineRun name that promoted it |
| `promotedAt` | UTC timestamp of when the `record` step ran (not the promote commit) |
