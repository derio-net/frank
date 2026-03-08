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
- Edits an existing plan's manual-operation block (e.g. marking `status: done`)
- Adds a Phase 0 / bootstrap step directly to the runbook

## Process

1. **Scan** all `docs/plans/*.md` for fenced code blocks tagged `# manual-operation`
2. **Parse** each block as YAML — extract all fields
3. **Read** existing `docs/runbooks/manual-operations.yaml`
4. **Merge** — for each extracted entry:
   - If `id` already exists in runbook: update all fields EXCEPT `status` (preserve human-set status)
   - If `id` is new: append the entry with `status: pending`
5. **Sort** the final list by `phase` ascending, then `id` alphabetically within each phase
6. **Rewrite** `docs/runbooks/manual-operations.yaml` with the merged, sorted list (preserve the file header comment block)
7. **Report** summary: N new entries added, N updated, N total
8. **Commit**:
   ```bash
   git add docs/runbooks/manual-operations.yaml
   git commit -m "chore(runbooks): sync manual-operations from plan files"
   ```

## Rules

- NEVER change `status` of an existing entry — only new entries get `status: pending`
- If a block in a plan is malformed YAML, report the file and line number, skip the block, continue
- If `docs/runbooks/` does not exist, create it before writing
- Always populate the `plan:` field from the plan filename if the block omits it
- Do not touch any other files

## Manual-operation block format (in plans)

Each block in a plan file looks like this — fenced, with `# manual-operation` as the first line inside:

````markdown
```yaml
# manual-operation
id: phaseNN-short-name
phase: NN
app: <argocd-app-name>
plan: docs/plans/<filename>.md
when: "After Task N — <trigger description>"
why_manual: "<reason this cannot be automated>"
commands:
  - <exact command or UI instruction>
verify:
  - <command or instruction to confirm success>
status: pending
```
````

## Runbook file format

```yaml
# docs/runbooks/manual-operations.yaml
#
# [header comment block — preserve as-is]

operations:
  - id: phaseNN-short-name
    phase: NN
    app: <app>
    plan: <path or null>
    when: "<trigger>"
    why_manual: "<reason>"
    commands:
      - <command>
    verify:
      - <command>
    status: done | pending
```
