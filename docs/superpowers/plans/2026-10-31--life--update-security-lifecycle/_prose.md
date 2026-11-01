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

```yaml
# manual-operation
id: life-main-ruleset
layer: life
app: cluster-update-fr
plan: 2026-10-31--life--update-security-lifecycle
when: "[POST-MERGE] after the three GitHub Apps exist and the console posts cluster-update/approved"
why_manual: "GitHub rulesets are forge state with no IaC in this repo; without it the session App (contents:write) could push or merge to main directly"
commands:
  - "gh api -X POST repos/derio-net/frank/rulesets with target=branch, include refs/heads/main, rules: pull_request, required_status_checks [{context: cluster-update/approved, integration_id: <console App id>}], non_fast_forward, deletion; bypass_actors = the operator and the console App only"
verify:
  - "with a session-App installation token: git push to main is refused, and a PR merge attempt is refused"
  - "the console merges a verified PR (it posts cluster-update/approved on the head SHA first)"
status: pending
```

```yaml
# manual-operation
id: life-console-pins
layer: life
app: cluster-update-fr
plan: 2026-10-31--life--update-security-lifecycle
when: "[PRE-MERGE of frank] after agent-images publishes the session image and cluster-update-fr publishes v0.1.0"
why_manual: "the image digests exist only after the sibling repos release; the manifests carry placeholders until then"
commands:
  - "apps/cluster-update-fr/manifests/deployment.yaml: replace ghcr.io/derio-net/cluster-update-fr:v0.1.0 with the @sha256 digest from the release notes; delete that entry from scripts/tests/fixtures/life/pin-exceptions.yaml"
  - "same file: replace ghcr.io/derio-net/upgrade-session:PENDING-PHASE-7 (omni-status sidecar) with the published tag or digest; set SESSION_IMAGE in files/console.env to the SAME value; delete the PENDING-PHASE-7 entry from pin-exceptions.yaml"
  - "regenerate: scripts/life_policy.py --emit-facts; scripts/render_all_images.py"
verify:
  - "kubectl -n cluster-update-fr get pod -l app.kubernetes.io/name=cluster-update-fr -o jsonpath='{..imageID}' names the digests (imageID, not ArgoCD Synced)"
status: pending
```

```yaml
# manual-operation
id: life-console-trust
layer: life
app: cluster-update-fr
plan: 2026-10-31--life--update-security-lifecycle
when: "[PRE-MERGE of frank] after the three GitHub Apps exist"
why_manual: "the bot logins are known only once the Apps are created; empty means the console trusts nothing"
commands:
  - "files/console.env: RENOVATE_BOT_LOGIN=<renovate-app>[bot], CONSOLE_BOT_LOGIN=<console-app>[bot], SESSION_BOT_LOGIN=<session-app>[bot]; leave STATUS_CREATOR_LOGINS empty (unused with ci_source: github-checks)"
verify:
  - "the console's Needs-action page lists a Renovate PR as trusted and an untrusted PR read-only"
status: pending
```

```yaml
# manual-operation
id: life-console-secrets
layer: life
app: cluster-update-fr
plan: 2026-10-31--life--update-security-lifecycle
when: "[POST-MERGE] after the app exists; every Secret is optional so the pod runs without them"
why_manual: "credentials cannot live in git; SOPS-applied out of band into the console namespace"
commands:
  - "Secret frank-updater-tailscale, key authkey (the same reusable ephemeral tag:frank-updater key hop-scan uses), namespace cluster-update-fr"
  - "Secret hop-readonly-kubeconfig, key config, namespace cluster-update-fr. Its cluster entry MUST carry `proxy-url: socks5://localhost:1055` (the tailscale sidecar's SOCKS5, TS_SOCKS5_SERVER) so only the Hop client uses the tunnel; hop-scan instead uses HTTPS_PROXY"
  - "Secrets cluster-update-session-omni (key key), cluster-update-session-talos (talosconfig), cluster-update-session-hop-talos (talosconfig), cluster-update-session-hop-kube (config), cluster-update-omni-reader (omniconfig, a Reader-role Omni service account), all in cluster-update-fr"
  - "PEM Secrets github-app-cluster-update-console-key and github-app-cluster-update-session-key (key `key`) in cluster-update-fr; Infisical keys FRANK_UPDATER_TELEGRAM_BOT_TOKEN, _CHAT_ID, _SECURITY_THREAD_ID, FRANK_UPDATER_GITEA_TOKEN"
verify:
  - "Telegram test alarm reaches derio.net #security; the inventory shows Hop versions and Omni's version; kubectl -n cluster-update-fr logs deploy/cluster-update-fr -c omni-status shows no omnictl failure"
status: pending
```

```yaml
# manual-operation
id: life-admission-dry-run
layer: life
app: cluster-update-fr
plan: 2026-10-31--life--update-security-lifecycle
when: "[POST-MERGE] once the admission policies are applied; also covers environments without a CEL engine"
why_manual: "the policies were evaluated offline with cel-python only; the API server's CEL is the authority"
commands:
  - "as the console SA (kubectl --as=system:serviceaccount:cluster-update-fr:cluster-update-fr) kubectl apply --dry-run=server -n upgrade-sessions -f <pod>: a pod with a foreign image, another ServiceAccount, a hostPath, privileged, hop-os with a token, an ephemeral container; and a service-account-token Secret, a Secret with the service-account.name annotation, a Secret not named us-*"
verify:
  - "every hostile object is refused with the policy's message; a pod shaped like the console's own is admitted"
status: pending
```

```yaml
# manual-operation
id: life-console-mirror
layer: life
app: cluster-update-fr
plan: 2026-10-31--life--update-security-lifecycle
when: "[POST-MERGE, LAST] trigger-first: the allowlists, mirror-reconcile and webhooks.yaml entries are already live"
why_manual: "forge state has no IaC here; creating the hook before the listeners accept the repo loses every event in the gap"
commands:
  - "create the Gitea mirror derio-net/cluster-update-fr; ensure the derio-fr-automation App installation includes the repo"
  - "THEN create the GitHub repo webhook (push, pull_request) to https://webhooks.hop.derio.net/ with the derio-net secret"
verify:
  - "a push to the repo creates a derio-net-main-sync PipelineRun and a gitea-actions/* status appears on the head"
status: pending
```

## Deployment deviations

None yet.
