## Manual Operations

Some steps cannot be declarative (SOPS secrets, UI-only config). Every such step must be:

1. Documented in the relevant plan as a fenced YAML block tagged `# manual-operation`
2. Synced to `docs/runbooks/manual-operations.yaml` via `/sync-runbook`

### Block format

Use fenced YAML with `# manual-operation` as first line. Required fields: `id`, `layer`, `app`, `plan`, `when`, `why_manual`, `commands`, `verify`, `status`. See `/sync-runbook` skill for the canonical schema.

### Central runbook

`docs/runbooks/manual-operations.yaml` — single source of truth for all manual ops across all layers. Run `/sync-runbook` to update it from plan files.
