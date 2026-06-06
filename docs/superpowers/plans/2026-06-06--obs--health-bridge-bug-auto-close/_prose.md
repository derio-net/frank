# Health Bridge — Auto-Close Healed Bug Issues

**Spec:** `docs/superpowers/specs/2026-06-06--obs--health-bridge-bug-auto-close-design.md`
**Status:** In Progress

## What this is

Closes the loop the original Layer 23 design left open: health-bridge files
`[Bug] <alertname> is dead — …` issues on dead transitions but never touches
them when the alert resolves. Transient incidents (frank-ops #38, #39, #40)
leave permanently-open bugs the operator closes by hand. This plan makes the
resolved webhook close them automatically, with a heal comment carrying
resolution time and outage duration.

En route it fixes a latent collision: `HasOpenBug` matches by title prefix
only, so layers sharing Grafana's synthetic `DatasourceError` alertname
suppress each other's bug creation — and a naive close-by-alertname would
close the wrong layer's bug. Both paths now disambiguate via the
`**Feature Issue:**` ref embedded in every bug body (newline-terminated, so
`#2` never matches `#24`).

## Shape of the work

Two repos, two PRs, one plan (precedent: the original
`2026-04-04--obs--health-bridge-service` plan lived in frank while the Go
code lives in `derio-net/health-bridge`):

| Phase | Repo | Working copy | Deliverable |
|-------|------|--------------|-------------|
| 1 (agentic) | derio-net/health-bridge | `~/Docs/projects/DERIO_NET/health-bridge`, branch `feat/auto-close-healed-bugs` | code PR (TDD, httptest-mock pattern) |
| 2 (agentic) | derio-net/frank | isolation worktree, branch `feat/ops-issue-auto-close` | image bump + doc updates (this PR carries spec + plan) |
| 3 (manual) | derio-net/health-bridge | — | merge PR, tag `v0.3.0`, GHCR build |
| 4 (manual) | cluster + frank-ops | — | smoke fire/heal, stale #38/#39 cleanup |

**Merge order matters operationally, not structurally:** the frank PR can be
authored and merged any time (the bump references tag `v0.3.0` by name), but
ArgoCD can only pull the image after Phase 3 pushes the tag. Recommended
order: merge health-bridge PR → tag → merge frank PR → ArgoCD syncs →
Phase 4 smoke.

## Design decisions (operator Q&A 2026-06-06, full detail in spec)

- **Webhook-close only.** No Grafana-state reconciler, no new credentials.
  Evidence: every recent incident's resolved webhook reached the bridge
  (tracker `healthy` comments at +3 to +45 min). Revisit only if a stale bug
  recurs.
- **New issue per incident.** Flapping alerts file fresh bugs each time;
  auto-close keeps the open count at zero between incidents.
- **Close is not gated** by the per-tracker `lastState` dedup nor by
  severity — it keys purely on `alert.Status == "resolved"` and is
  idempotent (no open bugs ⇒ no-op).

## Post-deploy checklist

This is a **fix/extension** of deployed Layer 23 — per plan-config
`skip_when`, no new blog posts and no README delta; the existing
building/operating posts are updated in Phase 2. `/sync-runbook` after the
plan lands (three `# manual-operation` blocks in Phases 3–4).
