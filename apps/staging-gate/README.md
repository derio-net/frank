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
  tekton/               # the gate Pipeline + Tasks + triggers (THIS is what ArgoCD applies)
  README.md
```

The App-of-Apps Application for staging-gate points ONLY at `tekton/` — `registry/` and the
per-app values are data consumed by the pipeline / the `<app>-staging` ArgoCD app, not Kubernetes
objects.

## Onboarding an app

1. Add `registry/<app>.yaml` (schema below) + `<app>/staging-values.yaml`.
2. Add an `<app>-staging` ArgoCD Application (`apps/root/templates/<app>-staging.yaml`) deploying
   the chart into the staging vCluster, pinned to `<app>/staging-values.yaml`.
3. Ship an in-cluster smoke-test image (`smokeImage`) that exits 0 (pass) / non-zero (fail).
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
| `prodApp` | ArgoCD Application name for prod (promote target) |
| `prodValuesPath` | frank path to the prod values file |
| `prodValuesKey` | dotted key in `prodValuesPath` to bump on promote (e.g. `image.tag`) |

The validator checks the contract's SHAPE, not the existence of the referenced targets — a
`prodApp` may be a paired follow-up that doesn't exist yet.
