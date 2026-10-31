# Update & Security Lifecycle — Design

**Date:** 2026-10-31
**Layer:** `life` (new layer 22, "Update Lifecycle" — see *Builder's calls*)
**Clusters:** Frank (Omni-managed) and Hop (standalone talosctl), plus the
off-cluster Omni instance
**Supersedes:** `2026-03-25--repo--safe-update-automation-design.md` (never
started; its phase issues #387–#392 were closed as "dispatched in error")
**Verification gate:** `devops` holds the close-out

---

## Intent

The operator found out by *looking at Omni* that Frank runs Talos 1.12.6 and
Kubernetes 1.35.3 while upstream is at 1.14.5 / 1.37.2. Nothing told them. Hop
is further behind (Kubernetes 1.34.1), and Omni itself (v1.5 vs v1.13.1) is
tracked by nothing at all. Today there is no Renovate, no version file, no
vulnerability scanning, and 11 of 67 container images run `:latest` or no tag.

The goal is that the clusters **tell the operator** what is out of date or
vulnerable, **offer the right way to update each thing**, and **prove** every
update actually works — with the operator authorising by clicking, batching as
the preferred mode, and security issues raised immediately.

The operator's standing pain shapes the "prove it works" requirement: ArgoCD
has repeatedly reported Synced/Healthy while a change never applied or an
error hid behind OutOfSync for weeks (see `agents/rules/frank-gotchas.md`,
ArgoCD section). An update is not done when it merges, and not done when a pod
starts — it is done when the service answers correctly.

This is delivered as a **working system**, not infrastructure for one: on day
one every dependency is classified, and real updates have flowed through every
path.

## Goals

- One place listing every dependency of both clusters and the services on each,
  with running vs. latest version and vulnerabilities.
- A daily report and immediate security alarms in a **dedicated** Telegram chat.
- Approval by clicking, batching preferred, with different paths (auto-merge,
  batch-approve, session, operator runbook) depending on what is being updated.
- Every update verified end to end, with a defined way back.

## Non-goals

- Automatic remediation of vulnerabilities without a policy that allows it
  (security items alarm and jump the queue; they do not self-merge unless their
  path is auto-merge anyway).
- Posture/compliance scanning (Kubescape, CIS benchmarks).
- Hosts outside the clusters other than Omni (Pi-holes, Proxmox, the MacBook).
- Replacing Grafana, ArgoCD, or the existing alert bot.

## Anti-goals — it fails, even if it technically works, if:

1. Telegram repeats alarms — the dedicated chat becomes noise to be muted.
2. A failed update, killed pod or abandoned session leaves the system or the
   console in a messy, unexplained state.
3. An update that must be rolled back has no revert or restore path.
4. Credentials leak into logs, transcripts, PR bodies, Telegram or the console.
5. Canary / blue-green deployments (Argo Rollouts) are unsupported or left
   stuck at a pause.

## Constraints

- **Declarative-only** (`agents/rules/repo-principles.md`): every version the
  clusters run is declared in git. Bootstrap secrets are the only manual
  exception, applied via SOPS and recorded as `# manual-operation` blocks.
- **Omni owns Frank's Talos and Kubernetes versions.** No in-cluster upgrade
  controller may compete with it on Frank.
- **Hop is a single node** (CX23, 4 GB RAM): every Talos/Kubernetes step is
  public-edge downtime (blog, Headscale) and must be operator-approved; heavy
  in-cluster scanners do not fit there.
- **Talos ↔ Kubernetes support window** and **one Kubernetes minor at a time**:
  OS upgrades are ordered sequences, not independent bumps.
- **GitHub Actions minutes are exhausted** (`CI_AUTHORITY=gitea`, see gotchas);
  scheduled jobs run on Frank, not on GitHub-hosted runners.
- `prune: false` everywhere, `ServerSideApply=true`, and the other ArgoCD
  conventions in `agents/rules/frank-argocd.md`.

## Requirements

R1. The system keeps an inventory of every dependency of Frank, Hop and the off-cluster Omni instance — Talos, Kubernetes, Omni, every Helm chart and every container image, grouped by cluster and by service — showing for each its declared version (git), running version (live), latest available version and the gap.
R2. Every container image and chart is pinned to an exact version; no workload runs `:latest` or an untagged image.
R3. Frank's Talos and Kubernetes versions, Hop's Talos and Kubernetes versions, and the Omni version are declared in git, and the inventory flags any difference between declared and running.
R4. Renovate, self-hosted on Frank, detects available updates for every dependency type in R1, including Talos, Kubernetes and Omni.
R5. Every dependency is assigned exactly one update path — `auto-merge`, `batch-approve`, `session`, or `operator-runbook` — in a policy file in git, and CI fails if a dependency has no path.
R6. Auto-merge items show in the console with the time they will merge; the operator can hold one or merge it now; every auto-merge is recorded in History.
R7. Routine updates are collected into a suggested batch that the operator can edit and approve with one click, producing one PR.
R8. Every image running on either cluster is scanned for known vulnerabilities, with severity and whether a fixed version exists.
R9. Security items bypass batching: they are listed first and visually prominent, and each can be acted on alone immediately through its own path — "Approve now" for auto-merge and batch-approve items, a queue-jumping "Start session" for session items.
R10. A dedicated Telegram chat (not the existing alert chat) receives an immediate alarm when a vulnerability at or above the alarm threshold is found in a running component, and repeats it only when that item's state changes (fix released, severity raised, still unresolved past its deadline).
R11. The same chat receives one daily report summarising what needs action, with a link to the console; on days with nothing new it is a single short line.
R12. A Grafana dashboard shows versions-behind and vulnerability counts over time per cluster, and the alarm and report state is visible there.
R13. A web console at `updates.cluster.derio.net`, behind Authentik, opens on a "Needs action" page grouped as Security, Suggested batch, Auto-merge countdowns and Guided upgrades, with Inventory and History tabs.
R14. The console never changes a cluster itself: its buttons act only on the forges (merge or approve PRs, tick Renovate approvals, open issues, re-forward CI statuses, re-run CI jobs) or start an upgrade session.
R15. History records every update — manual, batched, automatic or session — with who or what approved it, the PR, the rollout result and the verification result.
R16. An update counts as done only when it is verified: for workloads, ArgoCD has applied its merge commit (checked against `operationState`, not the Synced status) and the service's smoke test passes; for OS steps, every node runs the declared version, nodes are healthy and the cluster's smoke tests pass. Until then it is shown as "rolled out, unverified", and a failing check shows it as failed.
R17. Every application on both clusters has a smoke test declared in git that exercises the real service, and CI fails if one is missing.
R18. Applications using Argo Rollouts show their rollout phase in the console, a paused or aborted rollout appears under Needs action, and updates to them run as upgrade sessions in which the promote or abort decision is made, guided by the brief.
R19. Every update path states how it is undone before it is approved: a one-click revert PR for chart and image bumps, a Longhorn snapshot taken inside the session before a stateful upgrade with restore steps, reverting the declared Talos version (through Omni on Frank, `talosctl rollback` on Hop), and an explicit one-way warning for Kubernetes minors.
R20. "Start session" launches a disposable pod for that upgrade alone, built on a derio-net/agent-images base, with credentials scoped to that upgrade injected; the operator attaches from the console in the browser and logs the agent in interactively.
R21. An upgrade session may act on the clusters (`omnictl`, `talosctl`, `kubectl`) only with credentials scoped to its upgrade type, runs non-root with all capabilities dropped in its own namespace, and can reach only the endpoints that upgrade needs.
R22. A session starts with a brief — the target, its place in the upgrade sequence, release notes, migration count, the rollback path and the relevant gotchas — and ends only after the R16 verification passes; for OS steps the new version is declared in git before it is applied.
R23. A session pod and its credentials are deleted when the operator ends it or after an idle timeout that never fires while an upgrade step is running, and its outcome and transcript (scrubbed) are kept in History.
R24. The OS tracks for Frank and Hop are shown as ordered sequences respecting the Talos–Kubernetes support window, each step approved separately; Omni is shown with its running and latest version and a link to its operator-run upgrade runbook.
R25. No credential appears in logs, session transcripts, PR bodies, Telegram messages or the console, and CI fails on a token-shaped string in any of them.
R26. A failed update, killed pod or abandoned session ends in a named state shown in the console ("failed at step X, rolled back", "needs you"), with its leftover pods, branches and volumes removed.
R27. At handover every dependency is classified, and at least one real update has completed through each of auto-merge, batch, security approval and agent session, plus one OS step on each cluster. Upgrading Omni itself is not part of handover.
R28. An update held for missing or failed CI shows why (status lost, never ran, or ran and failed) and offers the matching recovery from the console; a retry that fails again marks the update failed rather than retrying forever.
R29. Starting a session is safe to repeat: a second "Start session" for the same upgrade attaches to the running session instead of creating another, and two sessions that would change the same cluster's OS, or the same application, cannot run at once.

## Design

Four parts, built in this order. Each is useful by itself. One spec; the plans
may span several repos (see *Repos*).

```
              ┌────────────── git (frank repo) ──────────────┐
              │ versions/*.yaml · update-policy.yaml ·       │
              │ smoke/*.yaml · apps/** · omni env template   │
              └──────▲─────────────▲──────────────▲──────────┘
        PRs/merges   │             │ reads        │ records new version
 ┌──────────┐   ┌────┴─────┐  ┌────┴─────────┐  ┌─┴──────────────────┐
 │ Renovate │──▶│ GitHub   │◀─│ Update       │─▶│ Upgrade session pod│
 │ CronJob  │   │ PRs +    │  │ console      │  │ (disposable, runs- │
 └──────────┘   │ dashboard│  │ (Authentik)  │  │ fr attach)         │
                └────┬─────┘  └──▲───┬───────┘  └─────────┬──────────┘
          ArgoCD sync│           │   │ verify / alarm     │ omnictl/talosctl
                ┌────▼──────┐    │   ▼                    ▼
                │ Frank/Hop │────┘ Telegram (dedicated) + Grafana
                │ + Trivy   │  live versions, vulns, rollout state
                └───────────┘
```

### Part 1 — Detection, alarm, verification foundation

**Version declarations (R2, R3).** Every running version gets a declared home
in git:

- Images and charts: pin the 11 `:latest`/untagged images; charts are already
  pinned through `targetRevision`.
- **Frank OS:** add a **versions-only** declaration (e.g. `versions/frank.yaml`)
  for the Talos and Kubernetes versions — none exists today; they live only in
  Omni's database. It is NOT an Omni cluster template: a template sync owns
  every ConfigPatch on the cluster (`patches/phase*`: Longhorn disks, GPU,
  Cilium) and could drop or rewrite node config. A session applies a version
  step by changing only the cluster's version fields in Omni, then the
  inventory compares declared vs. running. Migrating Frank to a full Omni
  cluster template is a **non-goal** of this design.
- **Hop OS:** declare Talos and Kubernetes in `versions/hop.yaml`. Hop's
  combined machine-config patch is **not** in git (it carries secrets, and
  `clusters/hop/talosconfig/` is gitignored), so the versions file stands
  alone: version steps use `talosctl upgrade --image …` and
  `talosctl upgrade-k8s --to …`, which change versions without re-applying the
  patch. Bringing Hop's patch into git (SOPS) is out of scope.
- **Omni:** pin the version in the existing `omni/omni/omni.env.template`
  (`OMNI_IMG_TAG=${OMNI_VERSION}`, consumed by `compose.yaml`) by giving
  `OMNI_VERSION` a committed value; the Renovate custom manager points there.

**Renovate (R4, R5, R6, R7).** Self-hosted, as a CronJob on Frank, using a
**new scoped GitHub App** (repo contents, PRs, issues on `derio-net/frank` only)
minted through ESO like the existing agent tokens. Managers: `argocd`,
`helm-values`, `kubernetes`, `kustomize`, plus regex/custom managers for the
Talos, Kubernetes and Omni declarations (GitHub releases data source). The
Dependency Dashboard issue stays enabled as a fallback UI; the console is the
primary one.

The **update policy** (`update-policy.yaml` or Renovate `packageRules`,
builder's choice of representation) assigns each dependency a path. Defaults,
to be reviewed by the operator during the plan:

| Path | Default for |
|---|---|
| `auto-merge` | patch bumps of stateless apps with a smoke test |
| `batch-approve` | minor bumps of stateless apps |
| `session` | any update of a stateful app (needs a pre-merge Longhorn snapshot: databases, Longhorn, Authentik, Gitea, Paperclip); any update of an Argo Rollouts app; majors; Argo CD, Cilium minors; Talos and Kubernetes steps |
| `operator-runbook` | Omni (run by the operator from their laptop; console tracks only) |

**The console is the only merger.** Renovate opens PRs with
`automerge: false`; for `auto-merge` items the console merges once the
countdown (from Renovate's `minimumReleaseAge` and the policy's merge window)
has elapsed **and** CI has passed. `main` has no required checks
(`frank-gotchas.md`, Tekton), so letting Renovate merge on its own would
bypass the CI hold in R28. Requiring the bridged checks in branch protection
was rejected because a dropped status would then also block the operator's
manual merges. Same countdown, hold and merge-now as R6; the console just
owns the click. Batches use Renovate grouping; the console edits a batch
by changing approvals before the batch PR is generated.

**Vulnerability scanning (R8).** Trivy Operator on **Frank**, scanning
workloads; its metrics go to VictoriaMetrics. Per-vulnerability-id metrics
stay **off** (summary counts per image and severity only): an oversized scrape
is dropped whole and silently (`promscrape.maxScrapeSize`, Grafana gotchas).
The plan measures the scrape size before enabling it; per-CVE detail is read by
the console from the VulnerabilityReport objects, not from metrics. **Hop is scanned centrally from
Frank** (Hop's 4 GB node cannot host the operator): a Frank job lists Hop's
running images through a read-only Hop kubeconfig and scans them with Trivy
in client/server mode. **Reaching Hop:** nothing on Frank is on the tailnet
today (the only Tailscale client is on Hop). Pods that need Hop — the scan job,
the console, Hop sessions — carry a userspace Tailscale sidecar joined with a
tagged, ephemeral pre-auth key (bootstrap secret, SOPS); a Headscale ACL lets
that tag reach only Hop's kube and Talos APIs. Both feed the same store the console reads.

**Telegram destination (operator's decision).** A new Telegram **group named
`derio.net`** with Topics enabled, holding a **`#security` topic**. A new bot,
**Frank Updater** (`@frank_updater_bot`), separate from `@agent_zero_cc_bot`,
is a member and posts there by `message_thread_id`. The group is meant to grow:
the operator will invite other bots later, so the bot must post only to its own
topic. Creating the group, the topic and the bot needs the operator's Telegram
account, so it is a manual operation:

```yaml
# manual-operation
id: life-telegram-derio-net-group
layer: life
app: cluster-update-fr
plan: <filled by fr-plan>
when: "[PRE-MERGE] before the alarm/report phase merges"
why_manual: "BotFather and group creation need the operator's Telegram account"
commands:
  - "BotFather: /newbot -> name 'Frank Updater', username 'frank_updater_bot'; copy the token"
  - "Telegram: create group 'derio.net'; Settings -> Topics: on; create topic 'security'"
  - "Add @frank_updater_bot to the group"
  - "Read chat id (negative, -100...) and the topic's message_thread_id (getUpdates after posting in the topic)"
  - "Store in Infisical: FRANK_UPDATER_TELEGRAM_BOT_TOKEN, FRANK_UPDATER_TELEGRAM_CHAT_ID, FRANK_UPDATER_TELEGRAM_SECURITY_THREAD_ID"
verify: "a test message sent with the stored values appears in derio.net -> #security, and nowhere else"
status: pending
```

Supergroup chat ids are negative; use the webhook-style send (the
`service.telegram` positive-id gotcha does not apply to a direct Bot API call,
but keep the id as a string).

**Alarm and report (R10, R11, R12).** The `#security` topic above. The console
backend owns alarm state (one record per vulnerability × component) so
re-alarm happens only on a state change; Grafana alert rules exist for the
dashboard and as a dead-man's switch on the scanner and the report job, not as
the alarm source (Grafana re-fires on its own schedule, which violates
anti-goal 1). Respect the Telegram `parse_mode` gotcha (pin it explicitly).
Grafana dashboard: versions-behind and vulnerability counts per cluster over
time, last report sent, last scan. The console exports this state as
Prometheus metrics (open alarms by state, last report timestamp, last scan
timestamp, updates by state), scraped into VictoriaMetrics.

**Smoke tests (R16, R17).** One declaration per application in git
(`smoke/<app>.yaml` or a field in a shared file — builder's call), defaulting to
an HTTP check of the real endpoint, upgraded to a functional check where it
matters (LiteLLM chat call, ComfyUI `/object_info`, OVMS
`/v2/models/<name>/ready`, Grafana provisioning loaded). A verifier runs them
after every rollout. "Applied" means `status.operationState.operation.sync.revision`
equals the merge SHA and the live artifact reflects the change; `Synced` alone
never counts (gotchas: stale-revision for 15 days).

**CI guards (R5, R17, R25).** Offline tests in `scripts/tests/`: every
dependency classified, every app has a smoke test, no `:latest`, Renovate
config validates, no token-shaped strings in rendered outputs and fixtures.

### Part 2 — The update console

A small web app (new repo, see *Repos*) deployed on Frank at
`updates.cluster.derio.net`, behind Traefik + Authentik forward-auth
(`expose-service` skill), with a homepage tile.

**Pages (R13).**
- **Needs action** (landing): 🔴 Security (each with "Approve now", or a
  queue-jumping "Start session" for session-path apps), 📦
  Suggested batch (editable, "Approve batch"), ⏱ Auto-merge countdowns
  ("Hold" / "Merge now"), 🧭 Guided upgrades (OS tracks as ordered sequences,
  Omni, majors — "Plan step" / "Start session"), plus paused/aborted Rollouts.
- **Inventory**: cluster → service → dependency, declared/running/latest/gap,
  vulnerabilities, assigned path.
- **History**: every update with approver (operator / auto / session), PR,
  rollout, verification, rollback taken.

**Reading Hop.** The console reaches Hop's API over the tailnet with a
read-only kubeconfig (bootstrap secret) that may read pods, ArgoCD
Applications and Rollouts. Hop smoke tests for public services check the
public endpoint; mesh-only services are checked over the tailnet.

**CI signal across forges (R28).** Merges happen on GitHub; required-check
statuses arrive from Gitea through the status bridge, which can drop events. If
an auto-merge or batch PR has no conclusive CI status within a timeout, or its
CI failed, the item becomes `held — CI` under Needs action; it never merges
without a passing signal and never stalls silently.

The console **diagnoses** a held item before offering a fix, because the three
causes in `docs/runbooks/frank-gotchas/tekton.md` need different remedies:

| Diagnosis | Evidence the console checks | "Retry CI" does |
|---|---|---|
| Ran, status lost | Gitea has a terminal status for the head SHA; GitHub does not | re-forward the status to GitHub (the `ci_status_backfill.py` logic, posted with the console's GitHub App token) |
| Never ran | no Gitea run for the head SHA; check `mergeable` first | if conflicting: ask Renovate to rebase (checkbox); else redeliver the GitHub push webhook (GitHub API), which re-drives the mirror sync without any cluster write |
| Ran and failed | Gitea run concluded `failure` | re-run the failed jobs through the Gitea API |

The diagnosis and the action taken are shown on the item and kept in History.
Re-running a genuine failure does not hide it: after **one** retry that fails
again, the item is marked `failed — CI` and needs the operator. Auto-merge
items get that one retry automatically for the *ran-and-failed* case only;
everything else waits for the button. These are forge actions (GitHub, Gitea),
not cluster writes, so R14 still holds. The builder verifies that the running
Gitea version exposes a job re-run API; if not, the fallback is to re-request
the run through Renovate (rebase checkbox), **never** an empty commit — path
filters make an empty commit trigger nothing (tekton gotcha).

**Acting (R14).** Buttons act on the forges only — on GitHub: merge a PR,
tick a Renovate approval, open a revert PR, open an issue, post a re-forwarded
status, redeliver a webhook; on Gitea: re-run CI jobs — or start an upgrade
session (Part 3). Credentials: a GitHub App token able to merge PRs and write
statuses on `derio-net/frank`, and a Gitea token limited to Actions on the
mirrored repo. Access is restricted to the operator's Authentik group.

**OS steps (R16, R22).** Git leads the cluster: the session first opens and
merges the PR changing `versions/<cluster>.yaml`, then applies the step, then
verifies. Between merge and verification the inventory shows the item as
`declared, applying` — a known, displayed gap, never a silent one.

**Verification and state (R15, R16, R26). The console tracks each update
through `pending → approved → merged → applied → verified` (or `failed`,
`rolled-back`, `held`, `abandoned`), and reconciles leftovers (stale branches,
orphan session pods, unfinished snapshots) into a named state.

**Rollouts (R18).** For Argo Rollouts apps the console reads `.status.phase` and
pause conditions (read-only) and lists paused/aborted rollouts under Needs
action with a "Start session" button. Promote/abort happens **only inside an
upgrade session**, guided by the brief (the status-subresource patch already
used in this repo). The console makes **no cluster writes at all** (R14 holds
without exception).

**Rollback (R19).** Each item shows its rollback path before approval. Stateful
updates run as sessions: the session takes a Longhorn snapshot of the app's
volumes *before* merging the PR, and the brief carries the restore steps.
Kubernetes minors show a one-way warning.

### Part 3 — Disposable upgrade sessions

**Pod (R20, R21, R23).** "Start session" creates, in a dedicated namespace
(e.g. `upgrade-sessions`), a pod labelled `fr.run/id=<upgrade-id>` from an image
built in agent-images (base: `infra-shell`, which already pins `talosctl` to the
cluster version; add `omnictl` and the agent CLIs). Talos allows only ±1
minor of client skew and infra-shell's kubectl is unpinned, so `talosctl` and
`kubectl` are pinned **per upgrade step** to the step's target (selected at
session start), and the session image itself is a Renovate-tracked
dependency. Hardening: non-root,
`capabilities.drop: [ALL]`, read-only root FS with writable `emptyDir` home, no
service-account token unless the upgrade needs one, a CiliumNetworkPolicy
allowing egress only to that upgrade's endpoints (Omni, Talos API, GitHub,
model providers, the target services for smoke checks).

**Credentials by upgrade type.**

| Upgrade | Injected |
|---|---|
| chart/image major | GitHub App token; read-only kube SA for rollout checks |
| stateful app | + kube SA allowed to create Longhorn snapshots for that app's volumes |
| Rollouts app | + kube SA allowed to patch that app's Rollout status (promote/abort) |
| Frank Talos/K8s step | + Omni service-account key (role scoped as narrowly as Omni allows), Omni-issued talosconfig |
| Hop Talos/K8s step | + Hop talosconfig and kubeconfig |

No session ever receives access to the Omni host.

Bootstrap secrets (Hop talosconfig, Omni SA key) are SOPS-encrypted and applied
out-of-band as `# manual-operation` blocks.

**Attach.** The console embeds or links **runs-fr** (currently only in staging
on Frank — promote a production instance scoped to the session namespace,
behind the same Authentik set-and-overwrite header contract). The operator logs
the agent in interactively (Anthropic, OpenAI, or other); the login lives only
in the pod's `emptyDir` and dies with it.

**Brief and finish (R22).** The session starts with a generated brief file and
an agent instruction file (`CLAUDE.md`/`AGENTS.md` — gotchas: `SKILL.md` is
loaded by nothing). It ends by opening the PR that records the new version and
running the R16 verification; the console then checks the running version
independently.

**Starting twice (R29).** A session's identity is the upgrade id, never a
random suffix (`$(uid)` is random, not unique — tekton gotcha): the pod name and
its Secrets derive deterministically from it, so a second "Start session" finds
the existing pod (create-if-absent) and attaches to it. On top of that, a
**lock per target** — one per cluster OS, one per application — refuses a
second session that would change the same thing, naming the session that holds
it. The button is disabled while a start is in flight, but the server-side
check is the guarantee, not the button.

**Lifecycle.** Idle timeout and a maximum lifetime (builder's numbers; suggest
2 h idle / 8 h max). The idle clock runs only from a safe point: while a step is
in progress (a Talos rollout, an upgrade-k8s, a snapshot, a canary analysis) it
is paused, and the maximum lifetime warns the operator instead of killing a
running step. On end, the pod and its Secrets are deleted (the session has no
PVC — only `emptyDir`); the scrubbed transcript and outcome go to History.

### Part 4 — OS tracks

- **Frank:** Talos 1.12.6 → 1.13.x → K8s 1.36 → Talos 1.14.x → K8s 1.37 (exact
  path computed from the support matrix at run time), applied by changing only
  the cluster's version fields in Omni, inside a session. Known traps go in the brief:
  Longhorn last-replica drains, etcd extraArgs only on reboot, Omni silent
  wedge, the Omni rollback race scripts.
- **Hop:** same sequence via `talosctl`, each step announced as edge downtime.
  `tuppr` is noted as a possible later replacement for Hop only.
- **Omni:** the console shows running vs. latest (v1.5 vs. v1.13.1 today) and
  links an **operator runbook** (`docs/runbooks/`) that the operator runs from
  a terminal on their laptop, backup first. The actual Omni upgrade is out of
  scope here and tracked as derio-net/willikins#528. The console
  reads Omni's version with a read-only (Reader-role) Omni service account.
- **Rollback:** on Frank, revert the declared Talos version and apply it through Omni (Omni reconciles toward its cluster spec, so a per-node `talosctl rollback` would be undone); on Hop, `talosctl rollback`. Kubernetes is one-way.

## Repos

| Repo | Gets |
|---|---|
| `derio-net/frank` | Renovate, Trivy, policy, smoke tests, versions, Omni runbook, Grafana, apps for console/runs-fr/sessions, manual ops, blog posts |
| new `derio-net/cluster-update-fr` | the console |
| `derio-net/agent-images` | the upgrade-session image |
| `derio-net/runs-fr` | only if the attach contract needs changes |

## Verification

strategy: live
gate: devops

Pre-merge: offline CI tests in `scripts/tests/` (classification, smoke
coverage, pinning, Renovate config, token scrub) and the console's own unit
tests plus a run in the staging vCluster (`staging-gate`, `runs-fr-staging`).
Post-merge (`live`): each requirement is accepted only after it is observed on
the real clusters — a real auto-merge verified, a real alarm received in the
new chat, a real session upgraded something and was cleaned up, one OS step per
cluster. The operator (`devops`) holds the close-out because several steps are
theirs alone (creating the Telegram chat, SOPS bootstrap secrets, OS steps).

## Operator decisions (from the builder check)

- **Omni host:** never reached from the cluster. Omni upgrades are an operator
  runbook run from the laptop; the console only tracks and links it.
- **Cluster writes:** the console makes none. Longhorn snapshots and Rollouts
  promote/abort happen inside upgrade sessions, guided by the brief — so
  stateful and Rollouts-backed apps take the session path.
- **Omni at handover:** not upgraded in this project; shown with status only.
  Follow-up: derio-net/willikins#528 starts it once this ships.

## Builder's calls

These were decided by the designer, not the operator; check them:

- New layer `life` (#22, "Update Lifecycle") rather than folding into `auto`.
- Console is written in Go like `runs-fr` and `health-bridge` (the repo name,
  `derio-net/cluster-update-fr`, is the operator's).
- Both the security alarms and the daily report post to the `#security` topic;
  a separate topic for the daily report can be added later.
- Renovate runs as a CronJob on Frank with a new scoped GitHub App.
- Hop is scanned from Frank rather than running Trivy Operator on Hop.
- Alarm state lives in the console backend; Grafana alerts are dead-man's
  switches, not the alarm source.
- Policy defaults in the Part 1 table.
- Session timeouts 2 h idle / 8 h max.
- Frank versions are declared versions-only, not as an Omni cluster template.
- Hop is read over the tailnet with a read-only kubeconfig.
- A missing CI status holds an item visibly rather than merging or stalling.
- The console, not Renovate, performs every merge (spec review s3).
- Frank reaches Hop through a userspace Tailscale sidecar with a tagged,
  ephemeral pre-auth key and a Headscale ACL limited to Hop's APIs (s8).

## Left to the builder

Console storage, framework and UI library; the policy file's format; smoke-test
format; Renovate schedule specifics; the alarm threshold (suggest Critical and
High with a fixed version); the daily report time; exact NetworkPolicy rules.
