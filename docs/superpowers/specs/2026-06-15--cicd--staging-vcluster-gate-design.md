# Staging-vCluster e2e Release Gate — Design

**Status:** Draft (revised 2026-09-14)
**Layer:** cicd (19 — CI/CD Platform; activates `tenant` (14) vCluster, uses `deploy`-style promotion)
**Date:** 2026-06-15
**Repos touched:** `frank` (this spec, vCluster + ArgoCD + Tekton gate), `runs-fr` (per-commit image build + smoke-test), possibly `agent-images`/`super-fr` later (future gated apps)

## Implementation Plans

| Plan | Repo | Status |
|------|------|--------|
| [2026-06-15-staging-vcluster-gate](../plans/2026-06-15-staging-vcluster-gate) | `derio-net/frank` | In progress |
| runs-fr sibling ([runs-fr#21](https://github.com/derio-net/runs-fr/pull/21), merged 2026-08-27) + dispatch-permission fix | `derio-net/runs-fr` | Fix pending |

## Revision 2026-09-14 — what changed and why

The design below dates from June. The branch was parked for the Omni rebuild and rebased onto
`main` 283 commits later. Re-checking it against current `main` and the live cluster found
three defects that would have failed at runtime, plus one missing target. The operator settled
the open decisions in one batched Q&A (journal:
`docs/superpowers/journals/specs/2026-06-15--cicd--staging-vcluster-gate.md`).

| Finding | Evidence | Resolution |
|---------|----------|------------|
| Registering the vCluster would crash the ArgoCD application-controller cluster-wide | Live ArgoCD is `v3.3.2`. argo-cd#26529 panics on any registered vCluster Pod with LimitRange-defaulted resources. The existing scoped `resource.exclusions` Pod entry lists only the cnc-staging URL (`docs/superpowers/debugging/2026-07-19-argocd-vcluster-cache-panic.md`) | Add `https://staging.vcluster-staging.svc:443` to that entry, still cluster-scoped, never global. Extend `scripts/tests/test_argocd_vcluster_pod_exclusion.py` to cover both URLs. The exclusion must be live (controller restarted) **before** registration |
| The runs-fr trigger never reaches Frank | Both `build.yml` runs on runs-fr `main` failed at `trigger-gate` with `Resource not accessible by integration (HTTP 403)`, because `GITHUB_TOKEN` carries only `contents: read`. Separately, a `repository_dispatch` reaches Frank only through a runs-fr webhook that subscribes to that event | runs-fr grants `contents: write` to the `trigger-gate` job (cross-repo PR). A runs-fr GitHub webhook for `repository_dispatch` with its own derio-net HMAC is declared in `apps/tekton/webhooks.yaml` and created by manual op |
| The listener trigger was deferred to a manual step | It predates the `webhooks.yaml` delivery-path tripwire (#707) and the array-freeze removal | Wire the trigger in git now, with CEL input validation, guarded by the tripwire suite |
| ArgoCD cannot fetch the runs-fr chart | runs-fr is a PRIVATE repo, and ArgoCD holds no repository credential for any `github.com/derio-net` repo (the only repository Secret is an in-cluster Gitea one). The chart is not published as OCI | An ESO-minted ArgoCD `repository` Secret for `https://github.com/derio-net/runs-fr.git`, built from the existing `github-app-derio` ClusterGenerator (the derio-fr-automation App covers every derio-net repo). Its PEM must exist in `argocd` (manual op) |
| The smoke image cannot be pulled | GHCR `runs-fr` is public, but `runs-fr-smoke` is private (an anonymous manifest fetch gets 403). A first push creates a package private | The operator makes `runs-fr-smoke` public (manual op), following Frank's public-package convention |
| The red path needs a notification | #797's `layer-25-pipeline-failing` fires only on 3 or more failures with zero successes in 24h, so a single red run on a pipeline with green runs never alerts | A per-run `finally` Telegram notify. #797 remains the chronic-failure backstop |
| The promote step has no target | Frank has no `apps/runs-fr`, and runs-fr was never deployed (`2026-06-14-stoa-frank-infra-design.md`) | **Promote records last-green**: it commits the blessed sha to `apps/staging-gate/runs-fr/promoted.yaml` (decision `d-promote-last-green`) |
| The declared `repository_dispatch` webhook cannot exist (P10 review Critical #1, 2026-09-20) | GitHub's webhook availability matrix (docs.github.com/en/webhooks/webhook-events-and-payloads) restricts `repository_dispatch` to **App** webhooks — a `derio-net/runs-fr` REPOSITORY webhook subscribing to it is impossible, not merely unwired. Live corroboration: `agentic-stoa/cnc-frd`'s hook carries `[pull_request, push]` although its `cnc-image-promotion` trigger filters `repository_dispatch`, and no such PipelineRun exists in the retained window — the same failure, already live and silent elsewhere | **No GitHub webhook is created.** runs-fr's own `build.yml` POSTs the signed payload straight to `https://webhooks.hop.derio.net/` (decision `d-delivery-gha-direct-post`, supersedes `d-dispatch-webhook`). The `github`/`cel` interceptors are unchanged — they validate purely by HMAC signature + `X-GitHub-Event` header value, never sender identity, so they cannot tell a direct POST from a real GitHub delivery. `webhooks.yaml` gains a first-class `scope: direct-post` declaration kind for this shape, plus two tripwire assertions that would have caught the original mistake (no `scope: repo`/`org` entry may claim a GitHub App-only event; every declaration's `events:` must cover its served trigger's real `eventTypes`) |

Operator decisions: keep the **dedicated `staging` vCluster** (`d-dedicated-vcluster`); trigger
via a **signed direct POST from runs-fr's own GHA workflow, no GitHub webhook**
(`d-delivery-gha-direct-post`, 2026-09-20, supersedes the original `d-dispatch-webhook` — a
`repository_dispatch` webhook on a repository scope cannot exist); the Test
Plan proves **green and red, driven by the agent after merge** (`d-test-plan`).

Defaults chosen without asking, each following an existing pattern in the repo:

- **Push credential.** The gate pushes over HTTPS with the `frank-gitops-push` App token, as
  `cnc-promotion` and `site-promotion` do. This removes the `staging-gate-ssh-creds` manual
  Secret.
- **vCluster access for Tekton.** The chart's `exportKubeConfig.additionalSecrets` writes a
  second kubeconfig (`vc-staging-gate`, server already rewritten to the in-cluster Service) into
  the vCluster's host namespace. A namespaced Role, restricted by `resourceNames` to that one
  Secret, lets the `staging-gate` ServiceAccount read it. This removes the
  `vcluster-staging-kubeconfig` manual Secret.
- **Destination by name.** `runs-fr-staging` and the AppProject address the vCluster as
  `name: staging`, matching `cnc-staging`.
- **Registration.** The ArgoCD `cluster` Secret stays out-of-band, following the cnc-staging
  precedent. It is generated from the live `vc-staging` Secret by a manual-op script rather than
  stored SOPS-encrypted in git, so the vCluster admin key never sits at rest in the repo.
- **Notification.** No alert rule watches failed PipelineRuns. A `finally` task sends a
  plain-text Telegram message (no `parse_mode`: the HTML-400 trap) through the existing C2 bot,
  using an ExternalSecret over `FRANK_C2_TELEGRAM_BOT_TOKEN` / `FRANK_C2_TELEGRAM_CHAT_ID`.

## Context

The runs-fr Phase-8 verification (2026-06-12) deployed the gateway into the `experiments`
vCluster by hand and **caught a real `runAsNonRoot`/non-numeric-USER bug that CI structurally
cannot**, because CI never runs the pod (runs-fr#19). That one-off proved a vCluster is a
high-fidelity, disposable staging target (real API server, real `pods/exec`, real RBAC), and it
surfaced what an automated gate needs. This design turns the one-off into a **reusable,
automated release gate**: every merge to an app's `main` is built, deployed into a staging
vCluster via GitOps, and exercised by an in-cluster end-to-end smoke-test. Only a green run is
**promoted**.

It realizes the two-tier verification the k8s-native-runs umbrella spec anticipated
(`docs/superpowers/specs/2026-06-07--agents--k8s-native-runs-design.md`): Tier-1 deterministic
CI, and Tier-2 real-cluster behavioral proof, here automated and made the gate for shipping.

The building blocks exist on Frank: **Tekton** with the `github-listener` EventListener (.223)
[`cicd`], the **vCluster** capability (`experiments` and `cnc-staging`, loft 0.32.1,
host-ArgoCD-managed) [`tenant`], and GHCR images that default to public. Since June, `main` has
also gained a registered vCluster destination (`cnc-staging`) and two GitOps promotion pipelines
(`cnc-promotion`, `site-promotion`). This design reuses their credential and registration
patterns.

## Goals

- Every merge to a gated app's `main` produces a per-commit image and runs an **automated
  end-to-end gate** in a real staging cluster.
- A failing gate **blocks promotion and notifies**. A passing gate **promotes** by a declarative
  git commit. For runs-fr the promotion writes the last-green record; bumping a prod app is the
  follow-up once one exists.
- The gate is **reusable**: any app opts in through a declarative contract and a smoke-test.
  runs-fr is first.
- Staging stays **fully declarative** (GitOps into the vCluster), and the smoke-test runs
  **in-cluster**.

## Non-goals (this spec)

- The runs-fr **production wiring** (a prod ArgoCD app, Authentik forward-auth, Ingress,
  homepage tile). It is the paired follow-up that will consume `promoted.yaml`.
- Pre-merge / per-PR gating. This is a **post-merge** gate.
- Onboarding apps beyond runs-fr.
- Browser/visual attach testing. The smoke-test works at the API and websocket level.
- Reconciling `webhooks.yaml` against the live forges (the tripwire's documented follow-up).

## Architecture

**End-to-end flow (per gated app; first proven on runs-fr):**

```
merge to main (app repo)
  → GHA: build ghcr.io/<app>:sha-<short> + <smokeImage>:sha-<short>
  → GHA: sign + POST a repository_dispatch-shaped payload {action: staging-gate,
         client_payload: {app, sha}} DIRECTLY to webhooks.hop.derio.net (no GitHub
         webhook -- repository_dispatch is App-only; see Component 1) → github-listener
  → trigger staging-gate-<app>: github interceptor (HMAC) → CEL (has() guards, repo,
         action, sha/app regex)
  → Tekton staging-gate Pipeline:
      0. resolve-contract: read apps/staging-gate/registry/<app>.yaml
      1. bump-staging: image.tag → sha-<short> in the staging values (commit + push to frank)
      2. await-sync: <app>-staging Application Synced + Healthy (in the staging vCluster)
      3. run-smoke: apply the app's smoke RBAC, run the smoke Job IN the vCluster, exit 0 = pass
      4a. GREEN → promote: write {sha, image, pipelineRun, promotedAt} to the promoted record
                  (commit + push to frank)
      4b. RED   → promote skipped; record untouched
      finally:
        notify: Telegram (plain text) when run-smoke did not succeed
        reset:  delete the smoke namespace in the vCluster
```

### Component 1 — Per-commit image (app repo, GHA)

An `on: push: branches: [main]` workflow builds `ghcr.io/<app>:sha-<short>` and the smoke image,
then delivers a `repository_dispatch`-shaped notification to Frank. For runs-fr this is
`build.yml` (runs-fr#21, plus the direct-POST follow-up below).

**Delivery mechanism (revised 2026-09-20, P10 review Critical #1):** GitHub's webhook
availability matrix restricts `repository_dispatch` to **App** webhooks — a repository webhook
cannot subscribe to it — so the `trigger-gate` job cannot reach Frank via the GitHub
`repository_dispatch` API + a repo webhook, the original June design. Instead `trigger-gate`
builds the exact webhook payload itself and **POSTs it directly** to
`https://webhooks.hop.derio.net/`:

```
POST https://webhooks.hop.derio.net/
X-GitHub-Event: repository_dispatch
X-Hub-Signature-256: sha256=<hex HMAC-SHA256 of the exact body, keyed by FRANK_STAGING_GATE_WEBHOOK_SECRET>
Content-Type: application/json

{"action":"staging-gate","client_payload":{"app":"runs-fr","sha":"<short-sha>"},"repository":{"full_name":"derio-net/runs-fr"}}
```

The `staging-gate-runs-fr` trigger's `github`/`cel` interceptors validate purely by HMAC
signature and the `X-GitHub-Event` header value — never sender identity — so they cannot tell
this from a real GitHub-originated delivery. This needs no special GHA permission: the job only
needs the shared secret (`FRANK_STAGING_GATE_WEBHOOK_SECRET`, mirrored from Infisical
`/derio-net/GITHUB_WEBHOOK_SECRET`) as a repo Actions secret and `curl`/`openssl` to sign the
request — `permissions: contents: write` (the June design's fix for the dispatch-API's 403) is
no longer needed, and runs-fr PR #42 that added it is obsolete.

### Component 2 — Staging vCluster + ArgoCD registration (frank)

- **A dedicated `staging` vCluster** (`apps/vclusters/staging/values.yaml`, plus
  `apps/root/templates/{ns-vcluster-staging,vcluster-staging}.yaml`). It is gate-owned and
  resettable, separate from `experiments` and `cnc-staging`.
- **`exportKubeConfig.additionalSecrets`** adds `vc-staging-gate` in `vcluster-staging` with
  `server: https://staging.vcluster-staging.svc:443`. This is the gate's own kubeconfig.
- **The argo-cd#26529 exclusion** in `apps/argocd/values.yaml` lists the staging URL next to the
  cnc-staging URL. It is scoped by `clusters` and never global.
- **Registration**: an ArgoCD `cluster` Secret named `cluster-staging` (`name: staging`, server
  `https://staging.vcluster-staging.svc:443`), created out-of-band by manual op **after** the
  exclusion is live.
- **`runs-fr-staging`**: an Application with `destination.name: staging` that deploys the
  runs-fr chart from the runs-fr repo with the frank-side staging values.

### Component 3 — The gate Pipeline and trigger (frank, Tekton)

- `apps/staging-gate/tekton/`: Pipeline, Tasks, TriggerBinding/TriggerTemplate, RBAC, the
  Telegram ExternalSecret.
- `apps/tekton/triggers/eventlistener-github.yaml` gains a `staging-gate-runs-fr` trigger. Its
  `github` interceptor validates the HMAC from `derio-net-github-webhook-secret` for
  `eventTypes: [repository_dispatch]`. Its CEL filter leads with `has()` guards on
  `body.client_payload`/`.app`/`.sha` (P10 review #5 — a malformed payload fails as a clean
  non-match instead of a CEL evaluation error), then requires
  `body.repository.full_name == 'derio-net/runs-fr'`, `body.action == 'staging-gate'`, and
  `client_payload.app` / `client_payload.sha` matching `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$` /
  `^[a-f0-9]{7,40}$` (a valid Kubernetes label value, not just `^[a-z0-9-]+$` — P10 review #11,
  deliberate) before either value reaches a task shell. Neither the trigger, the CEL filter's
  repo/action/shape logic, nor the ExternalSecret changed for the delivery-path revision below —
  only what sends the request changed.
- **`apps/tekton/webhooks.yaml` declares the delivery path as `scope: direct-post`, not a GitHub
  webhook** (revised 2026-09-20, P10 review Critical #1 — see the Revision table). This is a
  first-class declaration kind alongside `scope: repo`/`org`: it records that the sender (here,
  runs-fr's own GHA workflow) POSTs a signed request straight to the listener, with no forge
  webhook registered, so GitHub's per-scope event restriction does not apply to it. Two new
  tripwire assertions in `scripts/tests/test_webhook_delivery_paths.py` guard the class of bug:
  no `scope: repo`/`org` declaration may claim a GitHub App-only event (currently
  `repository_dispatch`), and every declaration's `events:` must cover its served triggers'
  actual interceptor `eventTypes`. The latter also surfaced a pre-existing, unrelated gap
  (`agentic-stoa/cnc-frd` ↔ `cnc-image-promotion`, apparently dead — see the plan journal), left
  as a documented exemption rather than silently fixed by this plan.
  `apps/tekton/manifests/` gains the `derio-net-github-webhook-secret` ExternalSecret, a per-org
  HMAC following the derio-homelab precedent, now shared with runs-fr's own
  `FRANK_STAGING_GATE_WEBHOOK_SECRET` Actions secret instead of a GitHub webhook config. Merging
  it leaves `tekton-extras` Degraded (ArgoCD's ExternalSecret health check) until the manual op
  seeds the Infisical value — expected, undocumented before this revision, now noted on both the
  ExternalSecret and the `webhooks.yaml` entry.
- **Git writes** clone and push over HTTPS with `frank-gitops-push`.
- **vCluster writes** (`run-smoke`, `reset`) fetch `vc-staging-gate` with the host
  ServiceAccount token, then operate with that kubeconfig.
- **Serialization**: `resolve-contract` waits while an older `staging-gate` PipelineRun for the
  same app is still running, so two runs never share staging.
- Repo Tekton gotchas apply: `computeResources`, `HOME=/tekton/home`, `fsGroup` on the pod
  template, and `when` accepting both `Succeeded` and `Completed`.

### Component 4 — The per-app gate contract (frank)

`apps/staging-gate/registry/<app>.yaml` declares `app`, `sourceRepo`, `image`, `chartRepo`,
`chartPath`, `stagingApp`, `stagingValuesPath`, `smokeImage`, `smokeNamespace`,
`smokeRbacUrl` (the app's smoke RBAC manifest, pinned to the gated sha at run time), and
`promotedRecordPath`. The June `prodApp`/`prodValuesPath`/`prodValuesKey` keys are replaced by
`promotedRecordPath`. A prod-app bump comes back as an optional key when a gated app has a prod
app. `scripts/staging-gate/validate-contract.py` enforces the shape, and a tripwire test runs it
in CI.

### Component 5 — The smoke-test contract

Each app ships an in-cluster smoke-test that exits `0` (pass) or non-zero (fail), run as a Job in
the staging vCluster. For runs-fr (`runs-fr/test/e2e/`), the Job runs as `serviceAccountName:
runs-fr-smoke` from `test/e2e/rbac.yaml`, self-provisions a tmux fixture pod, and asserts:
no-auth → 403, an authed list includes the probe, and ws attach echoes binary stdin with a text
resize.

## Walking-skeleton scope

```
runs-fr main merge → GHA sha images → signed direct POST (no GitHub webhook) → github-listener
→ staging-gate → bump runs-fr-staging → ArgoCD deploys into the staging vCluster
→ in-cluster smoke GREEN → promoted.yaml records the sha (or RED → Telegram, record untouched)
```

## Verification (the gate is itself a workflow)

"Done" requires a **real runs-fr `main` merge observed end to end**: GHA build, the dispatch
delivered, a `staging-gate-runs-fr-*` PipelineRun, the staging vCluster running the gated image,
smoke green, and a last-green commit on frank `main`. The **red path** must also be shown: a
deliberately broken smoke image fails `run-smoke`, `promote` is skipped, `promoted.yaml` is
untouched, and the Telegram notification arrives. ArgoCD `Synced`/`Healthy` is not evidence.
Assert on the commit, the record, and the PipelineRun.

## Risks & open considerations

- **Controller crash on registration.** This is mitigated by the scoped exclusion. Its runtime
  proof is the registration step itself: controller logs stay panic-free after a cold cache
  rebuild. The recovery is `kubectl delete secret cluster-staging -n argocd` plus deleting the
  controller pod. Drop the exclusion when ArgoCD reaches 3.5 or later.
- **Weak smoke means false confidence.** The red path is mandatory.
- **vCluster admin key handling.** Both the registration Secret and `vc-staging-gate` hold
  vCluster admin credentials. The Role is restricted by `resourceNames`, and nothing logs a
  kubeconfig.
- **Staging reset and concurrency.** Handled by per-app serialization plus `reset` in `finally`.
- **Unauthenticated or forged triggers.** Handled by HMAC plus a CEL repo/action/regex filter.
- **Pushes to `main` from automation.** Gate commits carry `[skip ci]` and touch only
  gate-owned files: the staging values' `image.tag` and the promoted record.
