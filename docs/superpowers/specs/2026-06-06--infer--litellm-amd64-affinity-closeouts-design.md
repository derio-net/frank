# LiteLLM amd64 Affinity + Open-Issue Close-outs — Design Spec

**Date:** 2026-06-06
**Layer:** infer (primary), obs/orch (close-out only)
**Status:** Draft
**Issues:** [#478](https://github.com/derio-net/frank/issues/478), [#476](https://github.com/derio-net/frank/issues/476), [#474](https://github.com/derio-net/frank/issues/474)
**Branch:** `feat/issue-cleanup-474-476-478`

## Goal

Close three hand-opened GitHub issues in one pass:

1. **#478** — keep LiteLLM (gateway pods AND Prisma migrations Job) off the
   Raspberry Pi nodes, declaratively.
2. **#476** — execute the last trace-analyst close-out remainder that is repo
   work (`/update-readme`); fold the two cluster-side verifications into the
   post-merge Test Plan.
3. **#474** — no work: the hermes blog posts already shipped (commit
   `ce2fcd9e`, building `33-hermes-shell` + operating `28-hermes-shell` +
   series index + roadmap). Close with evidence at close-out.

## Key finding that reshapes #478

Issue #478 claims chart `litellm-helm 1.81.13` "supports NO
nodeSelector/affinity/tolerations" on the migrations Job. **Verified false for
affinity/tolerations** by pulling the pinned chart from
`docker.litellm.ai/berriai`:

- `templates/migrations-job.yaml:106` — `{{- with .Values.affinity }}`
- `templates/migrations-job.yaml:110` — `{{- with .Values.tolerations }}`
- `templates/deployment.yaml:226/230` — same top-level values

Only `nodeSelector` (and migrationJob-scoped scheduling values) are absent.
A single **top-level `affinity` block** therefore fixes both the main
Deployment placement (values.yaml TODO item 1) and the migrations Job (TODO
item 2 / #478) with the chart as-pinned. No Pi taint, no upstream PR, no
chart bump.

## Decisions (operator Q&A, 2026-06-06)

| Decision | Choice |
|---|---|
| #478 remediation | Top-level `affinity` requiring `kubernetes.io/arch=amd64` (the block the values.yaml TODO already drafted) |
| Resources requests/limits | **Deferred** — numbers unverifiable while the Metrics API is dead (#394); TODO stays with a note |
| #476 digest item 10 | **Closed** — operator confirms the 2026-06-06 08:00 digest arrived in Telegram |
| Test Plan | Full five-step post-merge plan (below) |

## Design

### 1. `apps/litellm/values.yaml` — affinity (#478)

Add at top level (consumed by both Deployment and migrations Job templates):

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/arch
          operator: In
          values: [amd64]
```

Rationale: arch (not hostname) is the documented intent — the Pis are ARM and
a broken upstream arm64 image layer was a prior failure mode (PR #220).
`amd64` still allows mini-1/2/3, gpu-1, pc-1.

Rewrite the values.yaml `TODO ON NEXT IMAGE BUMP` comment block:

- Item 1 (pod affinity): **shipped** (this change) except resources —
  resources remain TODO, blocked on #394 (no Metrics API; `kubectl top`
  dead). Alternative noted: verify numbers from VictoriaMetrics.
- Item 2 (migration Job pinning): **resolved** by the same top-level block;
  record the chart-template line numbers as evidence.

**Rollout interaction (known, accepted):** litellm is an Argo Rollouts canary
(`workloadRef` → chart Deployment) with two indefinite manual gates. The pod
template change triggers a gated canary; promotion is operator-driven
post-merge (Test Plan step 1). The migrations Job picks up the affinity on
the next ArgoCD sync (PreSync hook) with no gate.

### 2. README sync (#476)

Run `/update-readme` in the worktree: sync Technology Stack / Service Access /
Current Status to reflect ai-alert-helper 0.2.0 (Telegram analyst) and
anything else stale since the trace-analyst deploy.

### 3. Validation approach (TDD shape)

The affinity change is assertable offline — `helm template` against the
pinned chart with the repo's values file:

- **Red:** render currently emits NO `affinity` in either
  `Deployment/litellm` or `Job/litellm-migrations`.
- **Green:** after the values edit, both rendered manifests carry the
  `kubernetes.io/arch in [amd64]` nodeAffinity term.

The render check lives in a gitignored scratch script for the run (not CI) —
this is a one-shot structural assertion, not a regression suite.

### 4. Issue close-outs (manual phase / post-merge)

- **#474**: close citing commit `ce2fcd9e` + the four shipped artifacts.
- **#476**: close citing operator-confirmed digest arrival (item 10), the
  README PR, and the ArgoCD-cosmetic check result.
- **#478**: close citing the chart-template finding (correcting the issue's
  premise) + the merged affinity change + observed Job placement.

## Out of scope

- Resources requests/limits on litellm pods (blocked on #394 / VM-sourced
  verification — TODO comment retained).
- Cluster-wide Pi taint for heavy one-shot Jobs (bigger blast radius; would
  be its own brainstorm if a second app exhibits the same failure).
- Upstream `migrationJob.nodeSelector` PR (unnecessary — affinity suffices).
- The remaining #477 rework items (separate issue, separate plan).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-06-06-litellm-amd64-affinity-closeouts | `derio-net/frank` | `2026-06-06-litellm-amd64-affinity-closeouts` | — |

## Test Plan

> Post-merge — operator-driven. Agent runs cluster queries where it has
> access; operator promotes gates and confirms Telegram-side evidence.

1. **Canary rollout:** watch `kubectl argo rollouts get rollout litellm -n litellm`
   (or `kubectl get rollout`); evidence-gate the canary pod onto an amd64
   node (`kubectl get pod -n litellm -o wide`); operator promotes both
   manual gates; rollout reaches Healthy with all pods on amd64.
2. **Migrations Job placement:** on the sync that follows the merge, confirm
   the `litellm-migrations` Job pod scheduled on a non-Pi node
   (`kubectl get pod -n litellm -l job-name -o wide` or the Job's pod events).
3. **README:** confirm the `/update-readme` changes render correctly on main.
4. **ArgoCD cosmetic:** check ai-alert-helper Application health; if still
   stale `Degraded` (appTree cache gotcha), restart
   `argocd-application-controller` and confirm it clears.
5. **Close-outs:** close #474, #476, #478 with the evidence above.
