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

## Manual operations (phase 7, run in this order)

Headscale 0.25.1 source check (hscontrol/policy/acls.go): `expandUsersFromGroup` returns the group's
member strings unvalidated and `filterNodesByUser` simply matches nothing for an unknown user, so a
policy that names the not-yet-existing user `tag-admin` LOADS without error. The user must still exist
before step 2, because `preauthkeys create --user` needs it; the restart goes last so the ACL grant is
effective only once the key, the tag and the hop-1 node exist. Read from source, not run live.

```yaml
# manual-operation
id: life-hop-headscale-user
layer: life
app: headscale
plan: 2026-10-31--life--update-security-lifecycle
when: "[POST-MERGE, step 1 of 4] before minting the frank-updater key"
why_manual: "Headscale users are runtime state, not declarative"
commands:
  - "kubectl -n headscale-system exec deploy/headscale -- headscale users create tag-admin"
verify:
  - "kubectl -n headscale-system exec deploy/headscale -- headscale users list shows tag-admin"
status: pending
```

```yaml
# manual-operation
id: life-hop-headscale-key
layer: life
app: hop-scan
plan: 2026-10-31--life--update-security-lifecycle
when: "[POST-MERGE, step 2 of 4] after life-hop-headscale-user"
why_manual: "A secret minted at runtime; SOPS-applied, never in git"
commands:
  - "kubectl -n headscale-system exec deploy/headscale -- headscale preauthkeys create --user tag-admin --reusable --ephemeral --tags tag:frank-updater --expiration 720h"
  - "apply the key as Secret frank-updater-tailscale (key authkey) in namespace hop-scan via SOPS; rotate before it expires"
verify:
  - "headscale preauthkeys list --user tag-admin shows a reusable, ephemeral key with tag:frank-updater"
status: pending
```

```yaml
# manual-operation
id: life-hop-headscale-tag-hop1
layer: life
app: headscale
plan: 2026-10-31--life--update-security-lifecycle
when: "[POST-MERGE, step 3 of 4] after life-hop-headscale-key"
why_manual: "Node tags are runtime Headscale state"
commands:
  - "kubectl -n headscale-system exec deploy/headscale -- headscale nodes list   # note hop-1's id"
  - "kubectl -n headscale-system exec deploy/headscale -- headscale nodes tag -i <hop-1-id> -t tag:hop-node"
verify:
  - "headscale nodes list shows tag:hop-node on hop-1"
status: pending
```

```yaml
# manual-operation
id: life-hop-headscale-apply
layer: life
app: headscale
plan: 2026-10-31--life--update-security-lifecycle
when: "[POST-MERGE, step 4 of 4] LAST, after the ACL ConfigMap has synced and steps 1-3 are done"
why_manual: "headscale-config never rolls the pod (it is mounted by headplane too); restart by hand, gated on live ConfigMap content"
commands:
  - "until kubectl -n headscale-system get cm headscale-config -o jsonpath='{.data.acl\\.yaml}' | grep -q tag-admin; do sleep 10; done"
  - "kubectl -n headscale-system rollout restart deploy/headscale"
verify:
  - "kubectl -n headscale-system rollout status deploy/headscale; the hop-scan job's heartbeat reports healthy=true"
status: pending
```

## Deployment deviations

None yet.
