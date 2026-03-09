# Declarative Drift Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all declarative drift found in Phases 1–8, establish the manual-operations YAML format in plans and a central runbook, create the `/sync-runbook` skill, and update the phase workflow in CLAUDE.md.

**Architecture:** Four git-only template fixes (ArgoCD self-heals after push); one ConfigMap addition to make the Grafana datasource declarative; one new runbook file + retroactive manual-op blocks; one new project skill; one CLAUDE.md update.

**Tech Stack:** ArgoCD Application CRs, Helm values, Grafana provisioning ConfigMaps, Kubernetes YAML, Claude Code skill (Markdown).

---

## Task 1: Fix `longhorn` Application CR — remove ad-hoc finalizers

**Files:**
- Modify: `apps/root/templates/longhorn.yaml`

The cluster has two extra finalizers that were never in git:
- `pre-delete-finalizer.argocd.argoproj.io`
- `pre-delete-finalizer.argocd.argoproj.io/cleanup`

The standard App-of-Apps pattern uses only `resources-finalizer.argocd.argoproj.io`. These extras cause the root app to stay OutOfSync.

**Step 1: Verify the current template only has the one correct finalizer**

```bash
grep -A3 "finalizers" apps/root/templates/longhorn.yaml
```

Expected output:
```
  finalizers:
    - resources-finalizer.argocd.argoproj.io
```

If the extra finalizers are already absent (they're not in the git file, they're in the cluster), the file is already correct — no edit needed. The cluster will self-heal after we push Task 2+.

**Step 2: Confirm the file is correct as-is**

The template already only contains `resources-finalizer.argocd.argoproj.io`. The drift is purely in the cluster's live object. ArgoCD will remove the extra finalizers on next sync. No file change needed.

**Step 3: Commit a no-op comment to document the finding**

Add a comment to `apps/root/templates/longhorn.yaml` immediately above the finalizers block:

```yaml
  # Only resources-finalizer is valid here. pre-delete-finalizer variants
  # were added ad-hoc to the cluster and will be removed by ArgoCD on sync.
  finalizers:
    - resources-finalizer.argocd.argoproj.io
```

```bash
git add apps/root/templates/longhorn.yaml
git commit -m "fix(longhorn): document correct finalizer — ad-hoc extras will be pruned by ArgoCD"
```

---

## Task 2: Fix `longhorn-extras` Application CR — `ignoreDifferences` and `prune`

**Files:**
- Modify: `apps/root/templates/longhorn-extras.yaml`

**Problem:** The cluster's live Application has the `ignoreDifferences` entry with an explicit `group: ""` field and `prune: false`. The git template is already correct (it has both). Running `argocd app diff root` shows the diff is only the `group: ""` field.

**Step 1: Verify the current template**

```bash
grep -A8 "ignoreDifferences" apps/root/templates/longhorn-extras.yaml
```

Expected — current file:
```yaml
  ignoreDifferences:
    - group: ""
      kind: Secret
      name: longhorn-r2-secret
      namespace: longhorn-system
      jsonPointers:
        - /data
```

This is already correct. The OutOfSync is because the cluster's live object was patched with a slightly different schema. ArgoCD ServerSideApply will reconcile on next sync.

**Step 2: Verify `prune: false` is present**

```bash
grep "prune" apps/root/templates/longhorn-extras.yaml
```

Expected: `      prune: false`

**Step 3: If either is missing, add them now**

The `ignoreDifferences` block must be exactly:
```yaml
  ignoreDifferences:
    - group: ""
      kind: Secret
      name: longhorn-r2-secret
      namespace: longhorn-system
      jsonPointers:
        - /data
```

And `syncPolicy.automated` must include:
```yaml
    automated:
      prune: false
      selfHeal: true
```

**Step 4: Commit**

```bash
git add apps/root/templates/longhorn-extras.yaml
git commit -m "fix(longhorn-extras): ensure ignoreDifferences and prune match cluster state"
```

---

## Task 3: Fix `gpu-operator` Application CR — remove ad-hoc finalizers, add `prune: false`

**Files:**
- Modify: `apps/root/templates/gpu-operator.yaml`

**Problems:**
1. Cluster has `post-delete-finalizer.argocd.argoproj.io` and `post-delete-finalizer.argocd.argoproj.io/cleanup` — not in git template (correct, they should not be there)
2. `prune: false` is missing from `syncPolicy.automated` in git

**Step 1: Add `prune: false` to the gpu-operator template**

In `apps/root/templates/gpu-operator.yaml`, the `syncPolicy` block currently reads:
```yaml
  syncPolicy:
    automated:
      selfHeal: true
```

Change it to:
```yaml
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

**Step 2: Verify no extra finalizers are in the git file**

```bash
grep -A5 "finalizers" apps/root/templates/gpu-operator.yaml
```

Expected: only `resources-finalizer.argocd.argoproj.io`. The cluster-side extras will be removed by ArgoCD on sync.

**Step 3: Commit**

```bash
git add apps/root/templates/gpu-operator.yaml
git commit -m "fix(gpu-operator): add prune: false to syncPolicy — ad-hoc post-delete finalizers will be pruned by ArgoCD"
```

---

## Task 4: Make Grafana VictoriaLogs datasource declarative

**Files:**
- Create: `apps/victoria-metrics/manifests/grafana-victorialogs-ds.yaml`
- Modify: `apps/root/templates/victoria-metrics.yaml`
- Modify: `apps/victoria-metrics/values.yaml`

The VictoriaLogs datasource currently exists only in Grafana's PVC (added via API). We move it to a provisioning ConfigMap mounted into Grafana.

**Step 1: Create the provisioning ConfigMap**

```yaml
# apps/victoria-metrics/manifests/grafana-victorialogs-ds.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-victorialogs-datasource
  namespace: monitoring
  labels:
    grafana_datasource: "1"
data:
  victorialogs-datasource.yaml: |
    apiVersion: 1
    datasources:
      - name: VictoriaLogs
        type: victoriametrics-logs-datasource
        access: proxy
        url: http://victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local:9428
        isDefault: false
        version: 1
        editable: false
```

**Step 2: Mount the ConfigMap into Grafana via values**

In `apps/victoria-metrics/values.yaml`, add the following under the `grafana:` key (after the `plugins:` list):

```yaml
  extraConfigmapMounts:
    - name: victorialogs-datasource
      mountPath: /etc/grafana/provisioning/datasources/victorialogs.yaml
      subPath: victorialogs-datasource.yaml
      configMap: grafana-victorialogs-datasource
      readOnly: true
```

Also update the comment block that previously noted the workaround:

```yaml
  # VictoriaLogs datasource is provisioned declaratively via grafana-victorialogs-ds ConfigMap.
  # extraConfigmapMounts mounts it into /etc/grafana/provisioning/datasources/.
```

Remove the old NOTE/TODO/Workaround comment lines entirely.

**Step 3: Add the ConfigMap to the victoria-metrics ArgoCD app**

The `victoria-metrics` ArgoCD Application currently only has the Helm chart source. The ConfigMap needs to be applied separately. Add a second source pointing to the manifests directory:

In `apps/root/templates/victoria-metrics.yaml`, add a third source entry:

```yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      path: apps/victoria-metrics/manifests
```

The full `sources:` block becomes:
```yaml
  sources:
    - repoURL: https://victoriametrics.github.io/helm-charts/
      chart: victoria-metrics-k8s-stack
      targetRevision: "0.72.4"
      helm:
        releaseName: victoria-metrics
        valueFiles:
          - $values/apps/victoria-metrics/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      path: apps/victoria-metrics/manifests
```

**Step 4: Commit**

```bash
git add apps/victoria-metrics/manifests/grafana-victorialogs-ds.yaml \
        apps/victoria-metrics/values.yaml \
        apps/root/templates/victoria-metrics.yaml
git commit -m "fix(monitoring): make VictoriaLogs Grafana datasource declarative via provisioning ConfigMap"
```

**Step 5: Push and verify ArgoCD picks up the new ConfigMap**

```bash
git push
argocd app sync victoria-metrics --port-forward --port-forward-namespace argocd
kubectl get configmap grafana-victorialogs-datasource -n monitoring
```

Expected: ConfigMap exists in `monitoring` namespace.

**Step 6: Delete the live API-added datasource and verify provisioning takes over**

The manually-added datasource (id: 3) must be removed from Grafana so the provisioned one takes effect. This is a one-time migration step — see Task 5 (manual operation).

---

## Task 5: Document the Grafana datasource migration as a manual operation

This task adds the `# manual-operation` YAML block to this plan and to the Phase 7 observability plan, then populates the central runbook.

**Step 1: Add manual-operation block to this plan**

Append the following fenced block at the end of this file (before the Task 6 heading):

````markdown
```yaml
# manual-operation
id: phase07-grafana-victorialogs-migration
phase: 7
app: victoria-metrics
plan: docs/plans/2026-03-08-declarative-drift-remediation-plan.md
when: "After Task 4 Step 5 — after ArgoCD has synced the new provisioning ConfigMap"
why_manual: "The live API-added datasource (id:3) must be deleted via Grafana UI before the provisioned one activates; Grafana does not auto-replace API datasources with provisioned ones of the same name"
commands:
  - "Open Grafana at http://192.168.55.203"
  - "Navigate to Connections → Data sources"
  - "Find 'VictoriaLogs' (the API-added one, editable)"
  - "Click Delete datasource"
  - "Restart Grafana pod to force provisioning reload: kubectl -n monitoring rollout restart deployment victoria-metrics-grafana"
verify:
  - "kubectl -n monitoring logs -l app.kubernetes.io/name=grafana | grep -i victorialogs"
  - "Open Grafana → Connections → Data sources — VictoriaLogs should appear as provisioned (non-editable)"
  - "Click Test on VictoriaLogs — expect green success"
status: done
notes: "Grafana automatically adopted the API-added datasource on pod restart — no manual UI deletion needed. readOnly=True confirmed via API."
```
````

**Step 2: Retroactively add manual-operation block to Phase 8 plan**

Append this block to `docs/plans/2026-03-08-phase08-backup-impl.md`:

````markdown
```yaml
# manual-operation
id: phase08-r2-sops-secret
phase: 8
app: longhorn
plan: docs/plans/2026-03-08-phase08-backup-impl.md
when: "After Task 2 — after SOPS-encrypting the R2 secret"
why_manual: "SOPS metadata (.sops key) in Secret YAML is rejected by ArgoCD ServerSideApply schema validation; encrypted secrets must live outside ArgoCD-managed paths and be applied out-of-band"
commands:
  - sops --decrypt secrets/longhorn/r2-secret.yaml | kubectl apply -f -
verify:
  - kubectl get secret longhorn-r2-secret -n longhorn-system
status: done
```
````

**Step 3: Commit**

```bash
git add docs/plans/2026-03-08-declarative-drift-remediation-plan.md \
        docs/plans/2026-03-08-phase08-backup-impl.md
git commit -m "docs(plans): add manual-operation YAML blocks to drift remediation and phase 8 plans"
```

---

## Task 6: Create `docs/runbooks/manual-operations.yaml`

**Files:**
- Create: `docs/runbooks/manual-operations.yaml`

**Step 1: Create the runbooks directory and the YAML file**

```yaml
# docs/runbooks/manual-operations.yaml
#
# Central registry of all manual operations required across phases.
# Each entry corresponds to a # manual-operation block in a plan file.
# Maintained by the /sync-runbook skill — run it after editing any plan
# that adds or changes manual operations.
#
# Fields:
#   id          — unique identifier, format: phaseNN-short-name
#   phase       — phase number (0 = bootstrap, before ArgoCD)
#   app         — ArgoCD app name or "bootstrap"
#   plan        — relative path to the plan file, or null
#   when        — trigger: what must be done first
#   why_manual  — reason this cannot be declarative
#   commands    — exact steps to execute
#   verify      — how to confirm success
#   status      — pending | done

operations:
  - id: phase00-argocd-bootstrap
    phase: 0
    app: bootstrap
    plan: null
    when: "Initial cluster setup — before any ArgoCD apps exist"
    why_manual: "ArgoCD must be installed before it can manage itself; chicken-and-egg bootstrap"
    commands:
      - helm repo add argo https://argoproj.github.io/argo-helm
      - helm repo update
      - helm install argocd argo/argo-cd -n argocd --create-namespace --version 9.4.6
      - kubectl apply -f apps/root/ -n argocd
    verify:
      - kubectl get pods -n argocd
      - argocd app list --port-forward --port-forward-namespace argocd
    status: done

  - id: phase08-r2-sops-secret
    phase: 8
    app: longhorn
    plan: docs/plans/2026-03-08-phase08-backup-impl.md
    when: "After Task 2 — after SOPS-encrypting the R2 secret"
    why_manual: "SOPS metadata (.sops key) in Secret YAML is rejected by ArgoCD ServerSideApply schema validation; encrypted secrets must live outside ArgoCD-managed paths and be applied out-of-band"
    commands:
      - sops --decrypt secrets/longhorn/r2-secret.yaml | kubectl apply -f -
    verify:
      - kubectl get secret longhorn-r2-secret -n longhorn-system
    status: done

  - id: phase07-grafana-victorialogs-migration
    phase: 7
    app: victoria-metrics
    plan: docs/plans/2026-03-08-declarative-drift-remediation-plan.md
    when: "After drift remediation Task 4 Step 5 — after ArgoCD has synced the new provisioning ConfigMap"
    why_manual: "The live API-added datasource must be deleted via Grafana UI before the provisioned one activates; Grafana does not auto-replace API datasources with provisioned ones of the same name"
    commands:
      - "Open Grafana at http://192.168.55.203"
      - "Navigate to Connections → Data sources"
      - "Find 'VictoriaLogs' (the API-added one, editable) and click Delete datasource"
      - kubectl -n monitoring rollout restart deployment victoria-metrics-grafana
    verify:
      - kubectl -n monitoring logs -l app.kubernetes.io/name=grafana | grep -i victorialogs
      - "Open Grafana → Connections → Data sources — VictoriaLogs should appear as provisioned (non-editable)"
      - "Click Test on VictoriaLogs — expect green success"
    status: pending
```

**Step 2: Commit**

```bash
git add docs/runbooks/manual-operations.yaml
git commit -m "feat(runbooks): add central manual-operations registry with phase 0, 7, 8 entries"
```

---

## Task 7: Create the `/sync-runbook` skill

**Files:**
- Create: `.claude/skills/sync-runbook.md`

**Step 1: Create the skill file**

```markdown
---
name: sync-runbook
description: >
  Sync the central manual-operations runbook from all plan files.
  Use after writing or editing any plan that contains manual-operation
  YAML blocks. Scans docs/plans/*.md, extracts blocks tagged
  "# manual-operation", merges into docs/runbooks/manual-operations.yaml
  (deduplicates by id, preserves status of existing entries), then commits.
---

# Sync Runbook Skill

## When to use

Invoke `/sync-runbook` after any session that:
- Writes a new implementation plan containing `# manual-operation` blocks
- Edits an existing plan's manual-operation block (e.g. marking status: done)
- Adds a Phase 0 / bootstrap step directly to the runbook

## Process

1. **Scan** all `docs/plans/*.md` for fenced code blocks tagged `# manual-operation`
2. **Parse** each block as YAML — extract all fields
3. **Read** existing `docs/runbooks/manual-operations.yaml`
4. **Merge** — for each extracted entry:
   - If `id` already exists in runbook: update all fields EXCEPT `status` (preserve human-set status)
   - If `id` is new: append the entry
5. **Sort** the final list by `phase` ascending, then `id` alphabetically within each phase
6. **Rewrite** `docs/runbooks/manual-operations.yaml` with the merged, sorted list (preserve the file header comment)
7. **Report** summary: N new entries added, N updated, N total
8. **Commit**:
   ```bash
   git add docs/runbooks/manual-operations.yaml
   git commit -m "chore(runbooks): sync manual-operations from plan files"
   ```

## Rules

- NEVER change `status` of an existing entry — only new entries get `status: pending`
- If a block in a plan is malformed YAML, report the file and line, skip the block, continue
- If `docs/runbooks/` does not exist, create it before writing
- Always add the `plan:` field from the plan filename if the block omits it
- Do not touch any other files

## Manual-operation block format (in plans)

Each block in a plan file looks like:

\`\`\`yaml
# manual-operation
id: phaseNN-short-name
phase: NN
app: <argocd-app-name>
plan: docs/plans/<filename>.md
when: "After Task N — <trigger>"
why_manual: "<reason>"
commands:
  - <command or instruction>
verify:
  - <command or instruction>
status: pending
\`\`\`

## Runbook file format

\`\`\`yaml
# docs/runbooks/manual-operations.yaml
# [header comment block]

operations:
  - id: ...
    phase: ...
    app: ...
    plan: ...
    when: ...
    why_manual: ...
    commands:
      - ...
    verify:
      - ...
    status: ...
\`\`\`
```

**Step 2: Commit**

```bash
git add .claude/skills/sync-runbook.md
git commit -m "feat(skills): add sync-runbook skill for maintaining manual-operations runbook"
```

---

## Task 8: Update CLAUDE.md — add `/sync-runbook` to phase workflow and document the manual-op format

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add `/sync-runbook` to the Standard Phase Workflow section**

Find the workflow section:
```markdown
## Standard Phase Workflow

Every phase follows this sequence:

1. **Brainstorm** — `/brainstorming` (Superpowers plugin) to explore requirements, refine scope, and design the approach via Socratic dialogue
2. **Deploy** — Implement the ArgoCD app (values, Application CR, manifests)
3. **Blog** — Write a Hugo blog post documenting the phase
4. **Review** — Verify deployment health and blog accuracy
```

Replace with:
```markdown
## Standard Phase Workflow

Every phase follows this sequence:

1. **Brainstorm** — `/brainstorming` (Superpowers plugin) to explore requirements, refine scope, and design the approach via Socratic dialogue
2. **Deploy** — Implement the ArgoCD app (values, Application CR, manifests)
3. **Blog** — Write a Hugo blog post documenting the phase
4. **Sync runbook** — Run `/sync-runbook` if the phase plan contains any `# manual-operation` blocks
5. **Review** — Verify deployment health and blog accuracy
```

**Step 2: Add a Manual Operations section to CLAUDE.md**

Add the following new section after the `## Gotchas` section:

```markdown
## Manual Operations

Some steps cannot be declarative (SOPS secrets, UI-only config). Every such step must be:

1. Documented in the relevant plan as a fenced YAML block tagged `# manual-operation`
2. Synced to `docs/runbooks/manual-operations.yaml` via `/sync-runbook`

### Block format (in plans)

\`\`\`yaml
# manual-operation
id: phaseNN-short-name        # unique across all plans
phase: NN
app: <argocd-app-name>
plan: docs/plans/<filename>.md
when: "After Task N — <trigger description>"
why_manual: "<reason this cannot be automated>"
commands:
  - <exact command or UI instruction>
verify:
  - <command or instruction to confirm success>
status: pending               # update to: done after execution
\`\`\`

### Central runbook

`docs/runbooks/manual-operations.yaml` — single source of truth for all manual ops across all phases. Run `/sync-runbook` to update it from plan files.
```

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude-md): add sync-runbook to phase workflow and document manual-operations format"
```

---

## Task 9: Push and verify root app syncs clean

**Step 1: Push all commits**

```bash
git push
```

**Step 2: Sync root app and check status**

```bash
argocd app sync root --port-forward --port-forward-namespace argocd
argocd app list --port-forward --port-forward-namespace argocd
```

Expected: `root` shows `Synced` / `Healthy`. The previously OutOfSync apps (`longhorn`, `longhorn-extras`, `victoria-metrics`) should now show `Synced`.

**Step 3: Verify longhorn Application CR finalizers were cleaned up**

```bash
kubectl get application longhorn -n argocd -o jsonpath='{.metadata.finalizers}' | python3 -m json.tool
```

Expected: only `["resources-finalizer.argocd.argoproj.io"]` — no `pre-delete-finalizer` entries.

**Step 4: Verify gpu-operator Application CR**

```bash
kubectl get application gpu-operator -n argocd -o jsonpath='{.metadata.finalizers}'
kubectl get application gpu-operator -n argocd -o jsonpath='{.spec.syncPolicy}'
```

Expected: only `resources-finalizer.argocd.argoproj.io` in finalizers; `prune: false` in syncPolicy.

**Step 5: Verify Grafana provisioning ConfigMap exists**

```bash
kubectl get configmap grafana-victorialogs-datasource -n monitoring
```

Expected: ConfigMap exists.

**Step 6: Execute the Grafana datasource migration manual operation**

Follow the manual operation `phase07-grafana-victorialogs-migration` in `docs/runbooks/manual-operations.yaml`:
- Delete the API-added VictoriaLogs datasource in Grafana UI
- Restart the Grafana pod
- Verify the provisioned datasource appears and tests green

After completing: update `status: done` in both the plan block and the runbook entry.

**Step 7: Sync the runbook**

```bash
# invoke /sync-runbook skill
```

**Step 8: Final commit if runbook status was updated**

```bash
git add docs/runbooks/manual-operations.yaml docs/plans/2026-03-08-declarative-drift-remediation-plan.md
git commit -m "chore(runbooks): mark Grafana datasource migration as done"
git push
```

---

## Manual Operations

```yaml
# manual-operation
id: phase07-grafana-victorialogs-migration
phase: 7
app: victoria-metrics
plan: docs/plans/2026-03-08-declarative-drift-remediation-plan.md
when: "After Task 4 Step 5 — after ArgoCD has synced the new provisioning ConfigMap"
why_manual: "The live API-added datasource must be deleted via Grafana UI before the provisioned one activates; Grafana does not auto-replace API datasources with provisioned ones of the same name"
commands:
  - "Open Grafana at http://192.168.55.203"
  - "Navigate to Connections → Data sources"
  - "Find 'VictoriaLogs' (the API-added one, editable) and click Delete datasource"
  - kubectl -n monitoring rollout restart deployment victoria-metrics-grafana
verify:
  - kubectl -n monitoring logs -l app.kubernetes.io/name=grafana | grep -i victorialogs
  - "Open Grafana → Connections → Data sources — VictoriaLogs should appear as provisioned (non-editable)"
  - "Click Test on VictoriaLogs — expect green success"
status: done
notes: "Grafana automatically adopted the API-added datasource on pod restart — no manual UI deletion needed. readOnly=True confirmed via API."
```
