# Declarative Drift Remediation — Design

**Date:** 2026-03-08
**Scope:** Audit and remediate ad-hoc cluster changes across Phases 1–8; establish a canonical format for documenting permanent manual operations.

---

## Problem Statement

Eight phases of homelab work have accumulated two categories of drift from the declarative-only principle:

1. **Declarative drift** — resources exist on the cluster that are not reproducible from code in this repo (or git templates diverge from what's actually in the cluster).
2. **Undocumented manual operations** — steps that are legitimately manual (SOPS secrets, UI-only config) were performed without a canonical record, making disaster recovery and blog-writing harder.

---

## Findings

### Declarative Drift (must be fixed in code)

| Item | Location | Issue |
|------|----------|-------|
| Grafana VictoriaLogs datasource | Grafana PVC (live only) | Added via Grafana API; not in any manifest. Lost if PVC deleted. |
| `longhorn` Application CR | cluster vs `apps/root/templates/longhorn.yaml` | Cluster has extra finalizers: `pre-delete-finalizer.argocd.argoproj.io` and `pre-delete-finalizer.argocd.argoproj.io/cleanup` |
| `longhorn-extras` Application CR | cluster vs `apps/root/templates/longhorn-extras.yaml` | `ignoreDifferences` missing `group: ""` field; `prune: false` absent |
| `gpu-operator` Application CR | cluster vs `apps/root/templates/gpu-operator.yaml` | Cluster has extra finalizers: `post-delete-finalizer.*`; `prune: false` absent |

All four cause the `root` ArgoCD app to remain permanently OutOfSync.

### Legitimate Manual Exceptions (document, do not fix)

| Item | Reason | Status |
|------|--------|--------|
| R2 SOPS secret (`secrets/longhorn/r2-secret.yaml`) | SOPS metadata rejected by ArgoCD ServerSideApply schema | Applied via `sops --decrypt \| kubectl apply`; documented as exception in CLAUDE.md |
| ArgoCD initial Helm install | ArgoCD must exist before it can manage itself | Bootstrap; no plan file |

---

## Solution

### Part 1 — Declarative Retrofits

Four git-only fixes. ArgoCD self-heals after push; no manual cluster intervention needed.

**1. Grafana VictoriaLogs datasource**
Add a Grafana provisioning ConfigMap (`apps/victoria-metrics/manifests/grafana-victorialogs-ds.yaml`) and mount it via `grafana.extraConfigmapMounts` in `apps/victoria-metrics/values.yaml`. The existing live datasource (added via API) must be deleted from Grafana UI before the provisioned one takes effect — this is a one-time migration step documented as a manual operation.

**2. `longhorn` App CR**
Remove the two `pre-delete-finalizer.*` entries from `apps/root/templates/longhorn.yaml`. These were added ad-hoc and are not part of the standard App-of-Apps pattern.

**3. `longhorn-extras` App CR**
Fix `ignoreDifferences` to include the required `group: ""` field. Add `prune: false` to `syncPolicy.automated`.

**4. `gpu-operator` App CR**
Remove the two `post-delete-finalizer.*` entries. Add `prune: false` to `syncPolicy.automated`.

---

### Part 2 — Manual Operations Format

#### In Implementation Plans

Every plan that includes steps that cannot be declarative embeds one YAML block per step, fenced and tagged `# manual-operation`:

````markdown
```yaml
# manual-operation
id: <phase-app-short-name>       # unique across all plans
phase: <NN>
app: <app-name>
plan: docs/plans/<filename>.md
when: "After Task N — <trigger description>"
why_manual: "<reason this cannot be automated>"
commands:
  - <exact shell command>
verify:
  - <command to confirm success>
status: pending   # or: done
```
````

#### Central Runbook

`docs/runbooks/manual-operations.yaml` — single YAML file, sorted by phase:

```yaml
operations:
  - id: <phase-app-short-name>
    phase: <NN>
    app: <app-name>
    plan: <path or null>
    when: "<trigger>"
    why_manual: "<reason>"
    commands:
      - <command>
    verify:
      - <command>
    status: done | pending
```

Maintained by the `/sync-runbook` skill (see Part 3).

Retroactively populated with:
- Phase 0: ArgoCD bootstrap (no plan file)
- Phase 7: Grafana datasource migration (one-time)
- Phase 8: R2 SOPS secret

---

### Part 3 — `/sync-runbook` Skill

A Claude skill at `~/.claude/plugins/skills/sync-runbook.md` that:

1. Globs all `docs/plans/*.md` files
2. Extracts fenced YAML blocks tagged `# manual-operation`
3. Merges with any existing entries in `docs/runbooks/manual-operations.yaml` (deduplicates by `id`, preserves `status`)
4. Rewrites the runbook file sorted by phase, then by id
5. Reports a summary: new entries added, existing entries updated, total

Invoked as `/sync-runbook` after writing or editing any plan that contains manual operations.

---

### Part 4 — CLAUDE.md Workflow Update

The Standard Phase Workflow gains a `/sync-runbook` step:

```
1. Brainstorm
2. Deploy
3. Blog
4. /sync-runbook   ← new: after any plan with manual ops
5. Review
```

---

## Out of Scope

- Phases 1–6: no manual operations found beyond bootstrap (verified via git log and cluster audit)
- NAS backup target: disabled due to upstream Longhorn bug, properly stubbed in code — no action needed
- ValidatingWebhookConfiguration caBundle diff in victoria-metrics: certificate rotation managed by the operator — not ad-hoc
