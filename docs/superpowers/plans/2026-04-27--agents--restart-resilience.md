# Agent Pod Restart Resilience — Implementation Plan (frank side)

**Spec:** `docs/superpowers/specs/2026-04-27--agents--restart-resilience-design.md`
**Status:** Not Started

**Type:** Fix/extension of the `agents` layer (extends [`2026-04-15--agents--agent-images-and-vk-local-sidecar`](../archived-plans/2026-04-15--agents--agent-images-and-vk-local-sidecar.md) and [`2026-03-30--agents--secure-agent-pod`](../archived-plans/2026-03-30--agents--secure-agent-pod.md)). Per `repo-workflows.md`: same layer code, update existing layer's blog posts (no new posts).

**Goal:** The cluster-side and verification work to make the secure-agent-pod (and the planned fleet of sibling agent pods) survive container restarts gracefully. Specifically: deploy ArgoCD Notifications → Telegram for bump alerts; cut the running pod over to the new s6-based image; drop the redundant `lifecycle.preStop` hook in favor of s6's `cont-finish.d`; verify end-to-end resilience; document.

**Why now:** Two real failures on 2026-04-26/27 (in-pod agent SIGHUP'd supercronic → kali container died; image bump 4.5h later silently recreated the pod) made the cost of the current design concrete. PR #127 shipped operator-side mitigation (wezterm Cmd+Shift+{1,2} re-spawn); this plan addresses the underlying disruption from the cluster side.

**Cross-repo coordination:**
- This plan covers Phases 1-5 (cluster-side + cutover + verification + docs)
- The [agent-images-side plan](https://github.com/derio-net/agent-images/blob/main/docs/superpowers/plans/2026-04-27--agents--restart-resilience.md) covers Phases 1-4 there (image work). Those four phases must complete and produce new GHCR image SHAs before Phase 2 of this plan (the cutover) can run
- This plan's Phase 1 (ArgoCD Notifications) can land in parallel with the agent-images plan — no cross-repo dep
- The bumper workflow auto-fires PRs in this repo when agent-images merges. Hold those bumps until all four agent-images phases have landed; then this plan's Phase 2 picks up the merge

---

## Phase 1: Deploy ArgoCD Notifications + Telegram template [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/132 -->
**Depends on:** —

<!-- Tracking: Independent of agent-images work; can land in parallel. Must exist before Phase 3's annotations have anything to subscribe to. -->

Cluster-side wiring for the bump alert. Two new ArgoCD Applications + ESO secret.

### Task 1: Enable notifications in argocd Helm values

- [x] **Step 1: Edit `apps/argocd/values.yaml`**

```yaml
notifications:
  enabled: true
```

Verify the chart version supports this; current frank argocd is on argo-cd Helm chart 5.x or 6.x — both support the notifications subchart.

### Task 2: Create `apps/argocd-notifications/manifests/configmap.yaml`

> **Deviation (executed):** The argo-cd Helm chart already owns
> `argocd-notifications-cm` (created by the `argocd` Application). Having a
> second ArgoCD app try to manage that same ConfigMap causes ownership /
> tracking-id conflicts. Instead, the Telegram service, triggers, and templates
> were moved into `apps/argocd/values.yaml` under `notifications.notifiers /
> .triggers / .templates`, which the chart merges into the existing CM. The
> `argocd-notifications` Application still exists, but only manages the
> ExternalSecret (Task 3).

- [x] **Step 1: Telegram service + triggers + templates**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-notifications-cm
  namespace: argocd
data:
  service.telegram: |
    token: $telegram-token

  trigger.on-sync-running: |
    - description: Application is rolling out
      send: [agent-pod-rolling]
      when: app.status.operationState.phase in ['Running']

  trigger.on-sync-succeeded: |
    - description: Application sync completed
      send: [agent-pod-ready]
      when: app.status.operationState.phase in ['Succeeded']

  template.agent-pod-rolling: |
    message: |
      🔄 *{{.app.metadata.name}}* is rolling out
      From: `{{.app.status.sync.revision | substr 0 7}}`
      To:   `{{.app.spec.source.targetRevision | substr 0 7}}`
      Pods will recreate in ~30s. mosh sessions will need re-spawn (Cmd+Shift+2).
    telegram:
      chatIds:
        - $telegram-chat-id

  template.agent-pod-ready: |
    message: |
      ✅ *{{.app.metadata.name}}* synced — `{{.app.status.sync.revision | substr 0 7}}`
    telegram:
      chatIds:
        - $telegram-chat-id
```

### Task 3: Create `apps/argocd-notifications/manifests/externalsecret.yaml`

> **Deviation (executed):** Real frank ClusterSecretStore is named `infisical`
> (not `infisical-clustersecretstore`) and the in-cluster ESO API version is
> `external-secrets.io/v1` (not `v1beta1`). Used the values that match the
> existing `apps/grafana-alerting/manifests/externalsecret.yaml`. Also set
> `notifications.secret.create: false` in `apps/argocd/values.yaml` so the
> chart's empty placeholder Secret does not race ESO for ownership of
> `argocd-notifications-secret`.

- [x] **Step 1: Pull Telegram credentials from Infisical via ESO**

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: argocd-notifications-secret
  namespace: argocd
spec:
  refreshInterval: 1m
  secretStoreRef:
    name: infisical-clustersecretstore
    kind: ClusterSecretStore
  target:
    name: argocd-notifications-secret
    creationPolicy: Owner
  data:
    - secretKey: telegram-token
      remoteRef:
        key: FRANK_C2_TELEGRAM_BOT_TOKEN
    - secretKey: telegram-chat-id
      remoteRef:
        key: FRANK_C2_TELEGRAM_CHAT_ID
```

### Task 4: Add Application CR to `apps/root/templates/argocd-notifications.yaml`

- [x] **Step 1: Wire it into the App-of-Apps**

Single source pointing at `apps/argocd-notifications/manifests/`, ServerSideApply, prune false, selfHeal true. Match the pattern in existing root templates.

### Task 5: Push, sync, verify controller starts

- [x] **Step 1: Push the branch + open PR + merge**

- [x] **Step 2: Sync and verify**

```bash
argocd app sync argocd-notifications --port-forward --port-forward-namespace argocd
kubectl -n argocd get pods -l app.kubernetes.io/name=argocd-notifications-controller
```

Expected: controller pod runs.

- [x] **Step 3: Verify the secret resolves**

```bash
kubectl -n argocd get secret argocd-notifications-secret -o jsonpath='{.data}' \
  | python3 -c "import json,sys,base64; d=json.load(sys.stdin); [print(f'{k}: {len(base64.b64decode(v))} bytes') for k,v in d.items()]"
```

Expected: `telegram-token: <some bytes>`, `telegram-chat-id: <some bytes>`.

### Task 6: Test with a benign trigger

- [x] **Step 1: Annotate any test app temporarily, force a sync, observe Telegram**

```bash
kubectl -n argocd annotate app homepage \
    notifications.argoproj.io/subscribe.on-sync-running.telegram="" --overwrite
argocd app sync homepage --port-forward --port-forward-namespace argocd
```

Expected: Telegram message arrives. Remove the annotation:

```bash
kubectl -n argocd annotate app homepage \
    notifications.argoproj.io/subscribe.on-sync-running.telegram- --overwrite
```

> **Deviation (executed):** `on-sync-running` never fired for homepage because the sync
> completed in 0s (no pods to recreate). Tested `on-sync-succeeded` instead — trigger
> DID fire and called the Telegram Bot API. Result: `Bad Request: chat not found`.
>
> **Root cause (2026-04-29):** The notifications-engine native Telegram service
> (`github.com/OvyFlash/telegram-bot-api`) routes recipients by sign: negative IDs go
> to `NewMessage(chatID)` (group chats), positive IDs go to
> `NewMessageToChannel("@"+recipient)` (channel/username lookup). The chat ID
> `2034763022` is a positive integer — a private user chat, not a channel or group —
> so the engine produces `NewMessageToChannel("@2034763022")` which the Bot API
> rejects with "chat not found". The `chatIds` field in templates is entirely ignored
> by the service; `dest.Recipient` comes from the annotation value.
>
> **Fix:** Switched from `service.telegram` to `service.webhook.telegram` in
> `apps/argocd/values.yaml`. The webhook service calls the Bot API directly via HTTP
> with `chat_id: {{.context.telegramChatId}}` (hardcoded `2034763022` in
> `notifications.context` — not sensitive). Confirmed: direct `curl` to
> `https://api.telegram.org/bot.../sendMessage?chat_id=2034763022&text=...` delivers
> successfully to `@DerioUnbound` (type: private). Templates now use `webhook:
> telegram: method: POST body: <JSON>` format.
>
> **Phase 3 annotation format update:** The subscription annotations must use
> `subscribe.on-sync-running.webhook=telegram` (not `.telegram=""`) to match the
> renamed service. See Phase 3 Task 2 for the corrected annotation keys.
>
> **Infrastructure verdict: notification pipeline is wired and functional end-to-end
> (with webhook service).** Annotations removed after test.

---

## Phase 2: Image bump cutover [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/133 -->
**Depends on:** —

<!-- Tracking: Independent of Phase 1 in the dep graph (notifications are tested with a benign app in Phase 1 Task 6, not via this cutover). Operationally, do Phase 1 first so the controller exists when Phase 3's subscriptions land. -->

**External prerequisite (cross-repo):** The agent-images-side plan's Phases 1-4 must have merged on `derio-net/agent-images:main`, and the resulting bumper PR must exist in this repo. If you haven't completed those, switch to the agent-images plan now.

The disruptive moment. Pod restarts onto the new s6-based image. Operator must manually re-spawn mosh and verify behavior.

### Task 1: Confirm Phases 1-4 are merged in agent-images

- [ ] **Step 1: Check agent-images main has all four PRs**

```bash
cd ~/Docs/projects/DERIO_NET/agent-images
git log --oneline -10 origin/main | grep -E "agent-init.d|agent-shell-base|migrate to agent-shell-base|vk-local.*wrapper"
```

Expected: 4 commits.

> **Status (2026-04-29):** BLOCKED. `derio-net/agent-images` main is at `efc07ee`
> (fix: disable errexit in bashrc source). Only Phase 1 (`/opt/agent-init.d/`
> scripts, merged via PR #20) is on main. Phases 2-4 remain open:
> - Phase 2 (agent-shell-base): issue #17, not yet started
> - Phase 3 (kali migration to agent-shell-base): issue #18, not yet started
> - Phase 4 (vk-local wrapper): issue #19, PR #25 open but blocked by Phase 2
>
> Do NOT merge any frank bump PRs until agent-images Phases 2-4 land.
> The current open bump PR in frank (#146, `efc07ee`) carries only bug fixes,
> not the s6-based image — close it or hold it until the s6 bump supersedes it.

### Task 2: Merge the accumulated bumper PR in frank

- [ ] **Step 1: Identify the bump PR**

```bash
gh pr list --repo derio-net/frank --label vk-ready --search "bump agent-images"
```

There may be multiple if Phases 1-4 each fired the bumper. The latest one supersedes earlier ones; close the older ones.

- [ ] **Step 2: Merge the latest bump PR**

```bash
gh pr merge <PR_NUMBER> --repo derio-net/frank --squash
```

### Task 3: Observe the rollout

- [ ] **Step 1: Watch ArgoCD sync + pod recreation**

```bash
argocd app get secure-agent-pod --port-forward --port-forward-namespace argocd
kubectl -n secure-agent-pod get pods -w
```

Expected: old pod terminates, new pod creates with the new image SHAs (kali + vk-local). Recreate strategy means ~30s of downtime.

Note: this first cutover happens *without* the agent-pod-specific Telegram alert because Phase 3's subscription annotations haven't been added yet. Phase 1 Task 6's test left no permanent subscription.

### Task 4: Re-spawn mosh + verify pod-side state

- [ ] **Step 1: Cmd+Shift+2 in WezTerm**

A fresh mosh session attaches to a fresh tmux server. tmux-continuum auto-restore fires; on first cutover there's no prior layout to restore.

- [ ] **Step 2: Verify s6 + services**

```bash
ssh claude@192.168.55.215 'ps -ef | head -20'
# PID 1 should be /init (s6); s6-rc supervisors visible.

ssh claude@192.168.55.215 's6-svstat /run/service/sshd /run/service/supercronic'
# Expected: both up

ssh claude@192.168.55.215 'tmux -V; mosh-server --version | head -1'
# Expected: tmux 3.6, mosh-server 1.4.x

ssh claude@192.168.55.215 'ls /usr/local/share/tmux-plugins/'
# Expected: tmux-resurrect/, tmux-continuum/

ssh claude@192.168.55.215 'cat ~/.tmux.conf | tail -5'
# Should contain `source-file /etc/agent/tmux-resurrect.conf`.
# IF MISSING: existing PR #127-deposited ~/.tmux.conf overrode /etc/skel.
# Append the line manually once: echo 'source-file /etc/agent/tmux-resurrect.conf' >> ~/.tmux.conf
# Then `tmux source ~/.tmux.conf` to load the plugins in the running server.
```

### Task 5: Smoke test in-pod resilience

- [ ] **Step 1: Kill supercronic, observe respawn**

```bash
ssh claude@192.168.55.215 'pkill supercronic'
sleep 3
ssh claude@192.168.55.215 'pgrep -af supercronic'
# Expected: supercronic running with low elapsed time
```

mosh+tmux session uninterrupted (no container restart).

- [ ] **Step 2: Confirm no historical regressions**

Open a tmux session, split panes, attach `claude` REPL, type a message, observe everything works as before.

---

## Phase 3: Drop preStop, add notification annotations [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/134 -->
**Depends on:** Phase 1, Phase 2

<!-- Tracking: Manifest changes that complete the resilience picture. Fans in on Phase 1 (controller must exist) and Phase 2 (pod must already be on the new image so cont-finish.d takes over the shutdown role). -->

### Task 1: Remove `lifecycle.preStop` from deployment.yaml

- [x] **Step 1: Edit `apps/secure-agent-pod/manifests/deployment.yaml`**

Delete the entire `lifecycle:` block from the kali container spec. cont-finish.d/01-shutdown now handles the same shutdown.sh call, with the bonus that cont-finish.d/02-tmux-save runs after.

### Task 2: Add notification subscription annotations to the Application CR

- [x] **Step 1: Edit `apps/root/templates/secure-agent-pod.yaml`**

Add to the Application CR's `metadata.annotations`:

```yaml
notifications.argoproj.io/subscribe.on-sync-running.webhook: telegram
notifications.argoproj.io/subscribe.on-sync-succeeded.webhook: telegram
```

> **Note:** The service was renamed from `telegram` to `webhook.telegram` (see Task 6
> deviation above). The annotation key suffix must match the service name component
> after `service.webhook.` → so the annotation uses `.webhook` with value `telegram`
> (the named webhook endpoint).



### Task 3: Open PR + merge

- [x] **Step 1: Open PR `feat(agents): drop preStop, subscribe to ArgoCD bump alerts`**

- [ ] **Step 2: Merge after CI green**

ArgoCD syncs the Application change. Telegram fires (`on-sync-running` then `on-sync-succeeded`) — this is the **second cutover**, the first one with the heads-up. Pod recreates because the deployment.yaml change applies.

### Task 4: Re-spawn mosh + verify Telegram fired

- [ ] **Step 1: Cmd+Shift+2**

- [ ] **Step 2: Confirm Telegram alert arrived for this sync**

If alert is missing, check `argocd-notifications-controller` logs for delivery errors. Typical issues: bot token misconfigured (rare), chat ID typo, template parse error.

---

## Phase 4: End-to-end verification [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/135 -->
**Depends on:** Phase 3

<!-- Tracking: Exercise the full restart resilience story before declaring success. -->

### Task 1: Layout persistence across an image bump

- [ ] **Step 1: Set up a test layout**

In the frank workspace:
- Split tmux into 4 panes
- Each pane has a different cwd: `~/repos/agent-images`, `~/repos/frank`, `/tmp`, `~/.willikins-agent`
- One pane runs `vim /tmp/test.txt` with some unsaved content

- [ ] **Step 2: Wait 6 minutes**

Continuum auto-saves every 5 min; 6 min ensures at least one save fired.

- [ ] **Step 3: Trigger a pod restart**

```bash
kubectl -n secure-agent-pod delete pod -l app=secure-agent-pod
```

Telegram alert fires.

- [ ] **Step 4: Re-spawn mosh, observe restoration**

Cmd+Shift+2. After mosh handshakes and tmux server starts, tmux-continuum auto-restore fires. **Expected:** 4 panes back, cwds correct. **Lost:** vim's unsaved content (process is gone).

### Task 2: Crashloop bail

- [ ] **Step 1: Break supercronic and observe bail-out**

```bash
ssh claude@192.168.55.215
mv /usr/local/bin/supercronic /usr/local/bin/supercronic.broken   # or via kubectl exec
for i in 1 2 3 4 5 6; do pkill -KILL supercronic 2>/dev/null; sleep 0.5; done
sleep 10
s6-svstat /run/service/supercronic   # down
s6-svstat /run/service/sshd          # still up
```

- [ ] **Step 2: Restore supercronic and recover**

```bash
mv /usr/local/bin/supercronic.broken /usr/local/bin/supercronic
s6-svc -u /run/service/supercronic
sleep 2
s6-svstat /run/service/supercronic   # up
```

mosh+tmux session uninterrupted throughout.

### Task 3: Independent service deaths

- [ ] **Step 1: Kill sshd, observe readinessProbe failure + recovery**

```bash
ssh claude@192.168.55.215 'pkill sshd'
# SSH session drops. readinessProbe trips within ~30s.
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod
# Expected: READY 1/2 briefly
# s6 respawns sshd within 1-2s.
ssh claude@192.168.55.215 's6-svstat /run/service/sshd'   # up
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod
# Expected: READY 2/2 again after probe cycle
```

### Task 4: Bump alert end-to-end

- [ ] **Step 1: Trigger a sync (real or simulated)**

```bash
kubectl -n argocd annotate app secure-agent-pod \
    test-trigger="$(date)" --overwrite
```

- [ ] **Step 2: Confirm Telegram alert content matches the template**

App name, from-revision, to-revision, the "mosh sessions will need re-spawn" line. If anything is off, edit `apps/argocd-notifications/manifests/configmap.yaml` and re-sync.

### Task 5: Document learned gotchas

- [ ] **Step 1: For any quirk encountered (s6 non-root edge cases, tmux save timing, ESO refresh latency), append to `.claude/rules/frank-gotchas.md`**

Even small edge-case findings belong here so the next operator has the context.

---

## Phase 5: Post-deploy documentation [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/136 -->
**Depends on:** Phase 4

<!-- Tracking: Update existing layer docs (operating + building posts), README, gotchas. Per fix/extension rules, no new blog posts. -->

### Task 1: Update operating post

- [ ] **Step 1: Add an "Architecture: s6-overlay" section to `blog/content/docs/operating/14-secure-agent-pod/index.md`**

Cover: PID 1 is `/init`; cont-init.d/services.d/cont-finish.d roles; how to inspect with `s6-svstat /run/service/<name>`; how to restart a service (`s6-svc -t /run/service/<name>` then it auto-respawns); the bail policy.

- [ ] **Step 2: Update the "Persistent shells with mosh + tmux" section**

Add a paragraph about tmux-continuum auto-restore: "After a mosh re-spawn (Cmd+Shift+2), the new tmux server attaches to your saved layout — pane structure and cwds restored from the last save (≤5 min before the restart). Running processes are not restored; re-launch them yourself."

- [ ] **Step 3: Update the "What 'Healthy' Looks Like" process list**

Replace the `wait -n`-era process list with the s6-aware view: PID 1 = `/init`, services seen via `s6-svstat`, plus the supercronic-spawned children (claude session-manager, vk-bridge.py).

### Task 2: Update building post

- [ ] **Step 1: Update the "Architecture" section in `blog/content/docs/building/21-secure-agent-pod/index.md`**

Reflect the three-tier base lineage: agent-base → agent-shell-base → secure-agent-kali. Note that s6-overlay supervises sshd + supercronic independently, that crashloop bail-out is configured, and that kali keeps `claude`/`/home/claude` via build-arg parameterization (with a forward-link to "the rename plan").

- [ ] **Step 2: Update the "Process Supervision" section**

Replace the `wait -n` description with the s6-overlay model. Explain why this matters (the 23:27 SIGHUP incident). Link to the spec.

### Task 3: Update README

- [ ] **Step 1: Update Technology Stack row for Secure Agent Pod**

Mention s6-overlay-supervised + tmux-continuum-restored in the description.

- [ ] **Step 2: Add ArgoCD Notifications row to Technology Stack**

```markdown
| ArgoCD Notifications | Native ArgoCD subsystem | Telegram alerts on agent-pod sync events (image bumps, manual rollouts) — operator gets ~30s heads-up before mosh sessions die |
```

### Task 4: Update gotchas

- [ ] **Step 1: Add to `.claude/rules/frank-gotchas.md`**

```markdown
- **s6-overlay v3 in non-root mode requires `S6_KEEP_ENV=1` and `S6_VERBOSITY=2`** — without these, services don't inherit the container env. The `with-contenv` wrapper around cont-init.d / services.d scripts is also required for them to see `$AGENT_HOME`.
- **agent-shell-base parameterizes user via `AGENT_USER` / `AGENT_HOME` build args** (defaults `agent`/`/home/agent`). secure-agent-kali overrides to `claude`/`/home/claude` to preserve PV-resident state. New shell-driven children inherit defaults.
- **tmux-continuum auto-restore only fires when tmux server starts fresh** — `tmux source ~/.tmux.conf` in a running server reloads plugins but does not trigger restore. Auto-restore = fresh server start.
- **/etc/skel/.tmux.conf only seeds on first boot of a fresh PV** — existing PVs (like secure-agent-kali's) keep their existing ~/.tmux.conf. To pick up the resurrect/continuum line, append `source-file /etc/agent/tmux-resurrect.conf` manually once.
- **s6 crashloop bail (5 deaths in 60s) leaves the service down without a Telegram alert** — sshd-down is visible via K8s readinessProbe (pod removed from LB); supercronic-down is only visible in `s6-svstat`. Future enhancement: alert on bail.
```

### Task 5: Set plan status

- [ ] **Step 1: Edit `**Status:**` to `Deployed` in this file AND the agent-images-side plan**

Both plans flip to `Deployed` once the cluster-side verification passes. The agent-images plan's status reflects "images built and merged"; the frank plan's status reflects "pod is running on the new images with verified resilience."

### Task 6: Sync runbook

- [ ] **Step 1: Run `/sync-runbook`**

This plan has no `# manual-operation` blocks (all steps documented inline; no SOPS/UI-only operations). Expected: zero diff.

---

## Out of scope (deliberately)

Per spec — repeated here for plan-level clarity:

- secure-agent-kali rename to `agent`/`/home/agent` — separate plan, scheduled when convenient
- Tmux usage inside vk-local — VK-side decision
- Per-pod egress profiles for new shell pods — per-pod plans
- Generalized `spawn_agent_workspace(name)` in wezterm.lua — when second shell pod arrives
- Telegram alerts on s6 crashloop bail-out — bolt-on if real ops show value
- Service dependencies (s6-rc) for credential-mount-ready ordering — when it's needed
- CRIU process checkpointing — not viable
