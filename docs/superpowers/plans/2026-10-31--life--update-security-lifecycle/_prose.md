# Update & Security Lifecycle — frank plan

**Spec:** `docs/superpowers/specs/2026-10-31--life--update-security-lifecycle-design.md`
**Status:** Not Started
**Layer:** `life` (22)

## What this plan builds (frank's share)

The frank repo owns everything declarative: version declarations, Renovate,
the update policy, smoke declarations, Trivy, the Hop tailnet route, the
Grafana view, the console's and runs-fr's deployment, the upgrade-session
namespace/policies/briefs, the OS-track data and the runbooks.

Two sibling plans, run by their own agents in their own workspaces:

| Repo | Plan | Delivers |
|---|---|---|
| `derio-net/cluster-update-fr` (public) | console | the app: inventory, Needs action / Inventory / History, merge engine, CI diagnosis, alarm state + Telegram, session launcher with locks, metrics |
| `derio-net/agent-images` | upgrade-session image | `infra-shell`-based image with omnictl, per-step talosctl/kubectl selection, agent CLIs |

**Cross-repo merge order** (phase 7): agent-images → cluster-update-fr
(v0.1.0, GHCR public) → this PR. `depends_on` is within-plan only, so the order
is enforced by the operator at merge time, not by fr.

## Why the manual phase is last

Nothing agentic needs the secrets: every phase writes manifests and offline
tests. Secrets matter only when apps go live, which is post-merge. Every new
app therefore tolerates a missing Secret (`optional: true`, the crowdsec-canary
pattern) and phase 7 bootstraps them, merges in order, and drives the live
handover (R27).

## Conventions for executors

- Tests: `/Users/derio/Docs/projects/DERIO_NET/frank/.venv/bin/pytest <files> -q`
  from the worktree. Never create `.venv` in the worktree (not gitignored).
  Exclude the hugo-driving blog tests (they wedge; see memory/CI).
- Every new Application: `ServerSideApply=true`, `prune: false` (unless a
  configMapGenerator needs `prune: true` — then per-resource `Prune=false` on
  stateful objects), `selfHeal: true`, `ignoreDifferences` on Secret `/data`.
- Never apply anything to a cluster from an agentic phase. Read-only `kubectl`
  / `omnictl get` for measurements only.

## Deployment deviations

None yet.
