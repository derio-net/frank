# Staging-vCluster e2e Release Gate — Design

**Status:** Draft
**Layer:** cicd (19 — CI/CD Platform; activates `tenant` (14) vCluster, uses `deploy`-style promotion)
**Date:** 2026-06-15
**Repos touched:** `frank` (this spec, vCluster + ArgoCD + Tekton gate), `runs-fr` (per-commit image build + smoke-test), possibly `agent-images`/`super-fr` later (future gated apps)

## Implementation Plans

| Plan | Repo | Status |
|------|------|--------|
| _TBD — fr-plan_ | `derio-net/frank` | Planned |

## Context

The runs-fr Phase-8 verification (2026-06-12) deployed the gateway into the `experiments`
vCluster by hand and **caught a real `runAsNonRoot`/non-numeric-USER bug that CI structurally
cannot** — CI never runs the pod (runs-fr#19). That one-off proved a vCluster is a
high-fidelity, disposable staging target (real API server, real `pods/exec`, real RBAC), and
surfaced exactly what an automated gate would need. This design turns that one-off into a
**reusable, automated release gate**: every merge to an app's `main` is built, deployed into a
staging vCluster via GitOps, exercised by an in-cluster end-to-end smoke-test, and — only if
green — **auto-promoted to Frank production**.

It is the concrete realization of the two-tier verification the k8s-native-runs umbrella spec
anticipated (`docs/superpowers/specs/2026-06-07--agents--k8s-native-runs-design.md`): Tier-1
deterministic CI, Tier-2 real-cluster behavioral proof — here automated and made the gate for
shipping.

All building blocks already exist on Frank: **Tekton** + a `github-listener` EventListener
(.223) [`cicd`], the **vCluster** capability (`experiments`, loft 0.32.1, host-ArgoCD-managed)
[`tenant`], **Argo Rollouts** [`deploy`], and GHCR images that default public (no pull
friction). The work is composition + wiring, plus Frank's **first ArgoCD external-cluster
registration**.

## Goals

- Every merge to a gated app's `main` produces a per-commit image and runs an **automated
  end-to-end gate** in a real staging cluster before anything ships.
- A failing gate **blocks promotion**; a passing gate **auto-promotes** the gated image to
  Frank production (full CD) by a declarative git bump.
- The gate is **reusable** — any app opts in via a declarative contract + a smoke-test; runs-fr
  is the first, agent-images/super-fr/future apps plug in later.
- Staging stays **fully declarative** (GitOps into the vCluster), honoring the declarative-only
  principle; the smoke-test runs **in-cluster** (no flaky laptop port-forwards).

## Non-goals (this spec)

- The runs-fr **production wiring** (its prod ArgoCD app + Authentik forward-auth + Ingress +
  homepage tile) — the **paired follow-up** the promote step targets. The gate skeleton proves
  "promote fires" against a configured prod ref without depending on that wiring being complete.
- Pre-merge / per-PR gating (this is a **post-merge** gate). A PR-check variant is a later option.
- Onboarding apps beyond runs-fr (agent-images, super-fr) — they ride the contract later.
- Browser/visual attach testing — the smoke-test is API+websocket level; visual attach stays a
  manual spot-check.

## Architecture

**End-to-end flow (per gated app; first proven on runs-fr):**

```
merge to main (app repo)
  → GHA: build ghcr.io/<app>:sha-<commit>  +  trigger Frank's Tekton github-listener (.223)
  → Tekton gate Pipeline (runs in-cluster, parameterized by <app>):
      1. bump <app>-staging image ref → sha-<commit>   (git commit to frank) → push
      2. wait: ArgoCD syncs <app>-staging INTO the staging vCluster, Synced + Healthy
      3. smoke: run <app>'s smoke-test Job IN the staging vCluster (against the app ClusterIP)
                exit 0 = pass
      4a. GREEN → promote: bump <app> PROD image ref → sha-<commit> (git commit to frank)
                  → ArgoCD ships prod
      4b. RED   → stop; notify (Telegram via the existing webhook contact / health-bridge);
                  prod untouched
      5. reset: drop the <app> staging namespace in the vCluster for the next run
```

### Component 1 — Per-commit image (app repo, GHA)

A new `on: push: branches: [main]` workflow builds and pushes `ghcr.io/<app>:sha-<short>`
(coexists with the existing `v*` release workflow — `v*` is for explicit human releases; the
gate consumes the `sha` tag). For runs-fr this is a small addition alongside `release.yml`.
The final pipeline step (GHA) calls the Tekton `github-listener` with `{repo, sha}`.

### Component 2 — Staging vCluster + ArgoCD multi-cluster registration (frank)

- **A dedicated `staging` vCluster** (`apps/vclusters/staging/values.yaml` +
  `apps/root/templates/{ns-vcluster-staging,vcluster-staging}.yaml`), mirroring the existing
  `experiments` Application (loft vcluster chart, template ⊕ instance values). Gate-owned and
  reset-able — separate from the `experiments` sandbox.
- **Frank's first ArgoCD external cluster.** A `cluster` Secret in `argocd` (labelled
  `argocd.argoproj.io/secret-type=cluster`) built from the vCluster's `vc-staging` kubeconfig,
  with the server rewritten from `https://localhost:8443` to the in-cluster
  `https://staging.vcluster-staging.svc:443`, and the embedded CA + client cert/key as the
  config. **SOPS-encrypted, applied out-of-band** (the documented bootstrap-secret exception —
  it carries the vCluster admin client key and must not be ArgoCD-managed).
- Per gated app, an **`<app>-staging` ArgoCD Application** whose `destination.server` is the
  registered staging cluster, deploying the app's chart with a staging values file whose
  `image.tag` is the ref Tekton bumps.

### Component 3 — The gate Pipeline (frank, Tekton)

A Tekton `Pipeline` + `EventListener`/`TriggerBinding`/`TriggerTemplate` wired to the existing
`github-listener`, parameterized by `<app>` (resolved from the gate contract, Component 4).
Tasks, in order: **bump-staging** (git) → **await-sync** (ArgoCD app Synced+Healthy in the
vCluster) → **smoke** (the app's smoke-test Job in the vCluster) → **promote** (git bump prod,
on success) → **reset** (drop staging ns). Heed the repo's Tekton gotchas: `computeResources`
(not `resources`); accept `$(tasks.status)` of `Completed`; `fsGroup` on workspace pod
template; `HOME=/tekton/home`. Runs are **serialized per app** (one gate at a time) and reset
staging between runs.

### Component 4 — The per-app gate contract (frank)

A declarative entry per gated app (e.g. `apps/staging-gate/registry/<app>.yaml`) declaring:
`source repo`, `image repo`, `chart + staging-values path`, `smoke-test ref` (image/Job),
`prod app + values path to bump`. The Pipeline reads this; **onboarding an app = add an entry +
ship a smoke-test**. This is the reusability seam future apps (agent-images run-pod
provisioning, super-fr k8s runner) plug into.

### Component 5 — The smoke-test contract

Each app ships an **in-cluster** smoke-test that exits `0` (pass) / non-zero (fail), run as a
Job in the staging vCluster against the deployed app. For **runs-fr**: a small
`python + websockets` image running the one-off's three checks — no-auth → 403, authed list
returns the probe, ws attach (text resize + binary stdin → tmux echo) — plus the fixture
tmux probe-pod (`alpine` + `tmux new-session -d -s <id>` + `fr.run/*` labels). Lives in
`runs-fr/test/e2e/` so it versions with the app.

## Walking-skeleton scope (first plan)

Build Components 1–5 **for runs-fr**, proven end-to-end:

```
runs-fr main merge → GHA sha image → Tekton trigger → bump runs-fr-staging → ArgoCD deploys
into the staging vCluster → in-cluster smoke (403 / list / ws-attach) GREEN → promote step
commits the gated sha to the runs-fr PROD image ref
```

- The runs-fr **prod app** (Authentik/Ingress/homepage) is the **paired follow-up**; the
  skeleton's promote step bumps the configured prod image-ref/values (a stub prod app or the
  values file the follow-up will consume) — proving the *gate + promote mechanism* without
  depending on prod wiring.
- The **gate contract** (Component 4) is built real (runs-fr is one entry), establishing the
  reusable shape even though only runs-fr is onboarded.

## Verification (the gate is itself a workflow)

Per the "test workflows before declaring Deployed" principle, "done" requires a **real runs-fr
`main` merge observed flowing end-to-end** — GHA build → Tekton gate → staging vCluster shows
the gated image → smoke green → a promote commit appears — not merely ArgoCD Synced/Healthy.
Also verify the **red path**: a deliberately-broken image must fail the smoke and leave the
prod ref untouched (a notification fires).

## Risks & open considerations

- **First ArgoCD external cluster** — multi-cluster registration is new on Frank; the SOPS
  `cluster` Secret + server-URL rewrite is fiddly and a single source of "staging won't sync"
  failures. Document the registration as a `# manual-operation`.
- **Full CD blast radius** — every green merge auto-ships to prod. The smoke-test IS the safety;
  its coverage must be meaningful (the runAsUser class of bug, auth gating, the core attach
  path). Weak smoke = shipping bugs. The red-path test is mandatory.
- **vCluster admin key handling** — the registration Secret carries the vCluster admin client
  key; keep it SOPS-only, never ArgoCD-managed, never logged.
- **Staging reset / concurrency** — gate runs must serialize per app and fully reset staging
  between runs, or a stale deploy taints a verdict.
- **Promotion provenance** — the gated `sha` becomes the prod tag; the promote commit is the
  audit record of what shipped and why (which gate run blessed it).
- **GHA→Tekton trigger contract** — the github-listener must extract `{repo, sha}` from the GHA
  call (a TriggerBinding); a malformed/unauthenticated trigger must be rejected (the listener is
  cluster-internal; keep it so, or authenticate the call).
