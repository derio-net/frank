# n8n agent-session migration (frank — Plan C)

**Status:** Planned
**Spec:** `docs/superpowers/specs/2026-06-15--obs--agentic-alert-helper-design.md` (Part C)
**Layer:** obs

## Why

n8n-01 currently bolts the persistent-agent driver on via two ConfigMaps
(`agent-session-driver`, `agent-session-bootstrap`) mounted at `/opt/stoa-bin` + `/opt/stoa-bootstrap`
with a `lifecycle.postStart` bootstrap. Plan A bakes that `agent-session` interface into the
`multi-agent-shell` image. This migrates n8n onto the baked version — proving the extraction against
its **original** client and removing the duplicate. Split from the alert-agent plan deliberately:
n8n is a **live content-factory prod path**, so it gets its own review/rollback blast radius.

## Depends on (cross-repo)

Consumes the `multi-agent-shell` image tag from **Plan A**. `fr` `depends_on` is within-plan only,
so this gate is prose: don't bump n8n's image before Plan A's tag exists. Until then n8n stays on its
current pinned SHA with its ConfigMap driver — there is no broken window.

## What changes (beyond "drop two ConfigMaps")

The container spec changes too: remove the `/opt/stoa-bin` + `/opt/stoa-bootstrap` `volumeMounts` +
`volumes` AND the `lifecycle.postStart` hook (a postStart pointing at a deleted ConfigMap, or a
dangling mount, crashloops the sidecar). `AGENT_SIDECAR_URL=http://localhost:8765` is unchanged
(the driver's default port); set `AGENT_SESSION_SERVE=1` so the baked s6 longrun serves.

## Phase map

1. **Migrate the sidecar (TDD)** — rewrite `test_n8n_agent_sidecar.py` to assert the post-migration
   wiring (new image, `AGENT_SESSION_SERVE=1`, no `/opt/stoa-*` mounts, no postStart, ConfigMaps
   gone) RED; apply the deployment edits + delete the ConfigMaps GREEN.
2. **Post-Deploy verification** — content-factory's session drives a turn end-to-end through the
   baked driver after the swap (operator-driven; the remaining gate before Deployed).
