# Live-Mirror Sync Trigger Implementation Plan

> **For VK agents:** Use vk-execute to implement assigned phases.
> **For local execution:** Use subagent-driven-development or executing-plans.
> **For dispatch:** Use vk-dispatch to create Issues from this plan.

**Goal:** Replace the daily `0 6 * * *` Paperclip schedule on routine `2f4d361b` with a push-driven trigger: a merge to the `agentic-stoa/companies` gitea mirror's `main` fires a Tekton TaskRun that POSTs Paperclip's hmac_sha256 public-trigger endpoint (frank#444, Stoa-side STO-72/STO-75).

**Architecture:** A dedicated `live-mirror-sync` EventListener (cel interceptor: `X-Gitea-Event: push` + repo `agentic-stoa/companies` + ref `refs/heads/main`) in `tekton-pipelines` spawns a `fire-paperclip-webhook` TaskRun (python:3.12-alpine, stdlib-only HMAC signing — no runtime package installs, so Falco's EXE_UPPER_LAYER rule stays quiet). Manifests vendored from `agentic-stoa/companies@b61b374d stoa/ci/tekton/live-mirror-sync/` with frank-side adaptations documented in each file header. The existing daily schedule stays armed until the webhook path is observed end-to-end — no coverage gap.

**Tech Stack:** Tekton Triggers v1beta1 (cel interceptor), Tekton Task v1, gitea webhooks, Paperclip public routine triggers (HMAC-SHA256), ArgoCD (`tekton-extras` app, recursive `apps/tekton/`).

**Status:** In Progress

---

## Task 1: Vendor + adapt the Tekton manifests

- [x] **Step 1:** `apps/tekton/tasks/fire-paperclip-webhook.yaml` — Task, python stdlib signing, hardened securityContext, `HOME=/tekton/home`
- [x] **Step 2:** `apps/tekton/triggers/live-mirror-sync.yaml` — EventListener + TriggerBinding + TriggerTemplate, cel interceptor (github interceptor silently drops gitea webhooks — see frank-gotchas Tekton), nodeSelector pc-1
- [x] **Step 3:** Document divergences from the Stoa-canonical manifests in the file headers (namespace, interceptor, image, incoming-HMAC posture)

## Task 2: Install the Paperclip trigger secret (operator)

The HMAC value is rotated and delivered out-of-band by Stoa's CTO — it must never appear in git, issues, or chat (frank#444 §3a).

```yaml
# manual-operation
id: cicd-live-mirror-paperclip-secret
layer: cicd
app: tekton
plan: 2026-06-11--cicd--live-mirror-sync-trigger
when: "Before first webhook fire — TaskRuns fail env resolution until the secret exists"
why_manual: "Secret value is rotated Stoa-side and delivered out-of-band; bootstrap secrets are never ArgoCD-managed (repo principle)"
commands: |
  # fireUrl: cluster-internal Paperclip API base + the public trigger path.
  # Paperclip LB is 192.168.55.212:3100 (frank-infrastructure.md).
  kubectl -n tekton-pipelines create secret generic live-mirror-paperclip \
    --from-literal=fireUrl='http://192.168.55.212:3100/api/routine-triggers/public/31cbc6fb3c8ac34e3f25d677/fire' \
    --from-literal=webhookSecret='<VALUE DELIVERED OUT-OF-BAND — DO NOT PASTE ANYWHERE>'
verify: |
  kubectl -n tekton-pipelines get secret live-mirror-paperclip -o jsonpath='{.data.fireUrl}' | base64 -d
status: pending
```

- [ ] **Step 1:** Receive the rotated HMAC value from Stoa's CTO (coordinate on frank#444)
- [ ] **Step 2:** Create the secret per the manual-operation block
- [ ] **Step 3:** Run `/sync-runbook` (done in this PR for the block itself; re-run if the block changes)

## Task 3: Create the gitea webhook (operator)

```yaml
# manual-operation
id: cicd-live-mirror-gitea-webhook
layer: cicd
app: tekton
plan: 2026-06-11--cicd--live-mirror-sync-trigger
when: "After the EventListener is Synced/Healthy (el-live-mirror-sync Service exists)"
why_manual: "Gitea repo webhooks are instance state, not declarative; created via UI or API token"
commands: |
  # Gitea LB: 192.168.55.209:3000. Repo: the agentic-stoa/companies mirror.
  # UI: Settings -> Webhooks -> Add webhook -> Gitea
  #   Target URL: http://el-live-mirror-sync.tekton-pipelines.svc.cluster.local:8080
  #   Method: POST, Content type: application/json
  #   Trigger on: Push events, Branch filter: main
  # NOTE: webhook.ALLOWED_HOST_LIST must include *.svc.cluster.local
  # (frank-gotchas other-apps — already required by the existing gitea-listener).
  # A webhook secret MAY be set but is not validated cluster-side (cel
  # interceptor cannot HMAC; EventListener is ClusterIP-only — see the
  # divergence note in apps/tekton/triggers/live-mirror-sync.yaml).
verify: |
  # Gitea: webhook delivery log shows 202/200 from the EventListener.
  kubectl -n tekton-pipelines get svc el-live-mirror-sync
status: pending
```

- [ ] **Step 1:** Add the webhook on the gitea mirror repo per the block
- [ ] **Step 2:** Use gitea's "Test Delivery" — expect the cel filter to drop it (test payloads carry the real repo/ref, so a real merge is the true signal)

## Task 4: End-to-end verification + handback (operator)

- [ ] **Step 1:** Merge a test change to `agentic-stoa/companies` `main`; wait for the gitea mirror sync
- [ ] **Step 2:** Confirm `kubectl -n tekton-pipelines get taskrun | grep live-mirror-sync-` shows a run; logs end with `Paperclip responded HTTP 202` and `run=… issue=…`
- [ ] **Step 3:** Confirm the Paperclip run issue under routine `2f4d361b` carries the changed-file report
- [ ] **Step 4:** Report the 202/run-issue signal back on frank#444 (Stoa CTO then retires the `0 6 * * *` schedule)
- [ ] **Step 5:** Set this plan's `**Status:**` to `Deployed`

## Post-Deploy Checklist

Extension of the existing cicd layer, internal-only (no public domain, no homepage tile): skip exposure and blog posts per the fix/extension workflow. New gotchas, if any surface during verification, go to `agents/rules/frank-gotchas.md` + `docs/runbooks/frank-gotchas/tekton.md`.

- [x] Runbook sync (`/sync-runbook`) — included in this PR
- [ ] Plan status update on verification (Task 4, Step 5)
