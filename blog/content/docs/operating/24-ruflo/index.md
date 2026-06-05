---
title: "Operating on Ruflo"
date: 2026-05-03
draft: false
tags: ["operations", "ruflo", "claude-flow", "ruvocal", "ai-agents", "agent-shell-base", "ssh", "mosh", "litellm"]
summary: "Day-to-day commands for managing Ruflo — connecting via SSH/Mosh, curating the inventory ConfigMap, reading the install log, bumping images, backups, and a worked example of running claude-flow against the running ruvocal."
weight: 25
---

This is the operational companion to [Ruflo — A Swarm Orchestrator Next to Paperclip]({{< relref "/docs/building/29-ruflo" >}}). That post explains the architecture and the rationale. This one covers the day-to-day: connecting, installing tools, bumping images, reading logs, recovering from breakage, and a worked swarm-run cookbook.

## What "Healthy" Looks Like

Ruflo is healthy when:

- The `ruflo` Deployment is `2/2 Running` in the `ruflo-system` namespace (both `ruflo` and `ruflo-shell` containers Ready).
- The web UI loads at `https://ruflo.cluster.derio.net` after Authentik SSO.
- SSH to `agent@192.168.55.222` succeeds.
- All four ExternalSecrets (`ruflo-llm`, `ruflo-resend`, `ruflo-shell-alerts`, plus any optional add-ons) show `SecretSynced=True`.
- The three PVCs are `Bound` (`ruflo-data` 5Gi, `ruflo-shell-home` 10Gi, `ruflo-workspace` 20Gi).
- The `ruflo-db` Bitnami postgresql StatefulSet is `1/1 Running` (parked but green — see the building post for the RVF deviation).

```bash
kubectl get pods,pvc,externalsecret,svc -n ruflo-system
```

Expected: one `ruflo-…` Deployment pod (2/2), one `ruflo-db-postgresql-0` StatefulSet pod (2/2), three Bound PVCs, four synced ExternalSecrets, two Services (ClusterIP for ruvocal, LoadBalancer at `192.168.55.222` for SSH+Mosh).

## Connecting

### Web UI

Open `https://ruflo.cluster.derio.net`. Authentik forward-auth handles the SSO redirect. After login you land on ruvocal's chat surface. The session cookie is shared with every other Authentik-fronted service on the cluster, so you sign in once.

### SSH

Add to `~/.ssh/config`:

```ssh-config
Host ruflo
  HostName 192.168.55.222
  User agent
  Port 22
```

Then:

```bash
ssh ruflo
```

### Mosh

Mosh works over a UDP port range allocated on the Service (`60016–60031`). You can wrap it in a shell function or just call it directly:

```bash
mosh --ssh="ssh -i ~/.ssh/<your-key>" \
     --server="mosh-server new -p 60016:60031" \
     agent@192.168.55.222
```

Sixteen ports is plenty of headroom; `MOSH_SERVER_NETWORK_TMOUT` reaps stuck sessions so the range doesn't bleed.

### Authorised-Keys Bootstrap

Authorised keys live in a SOPS-encrypted Secret `ruflo-shell-ssh-keys` (under `secrets/ruflo/`). The pod boots whether the Secret exists or not — sshd just rejects key-based logins until the bootstrap is applied. To rotate or seed keys:

```bash
# Edit secrets/ruflo/ruflo-shell-ssh-keys.yaml (SOPS will round-trip the encryption)
sops secrets/ruflo/ruflo-shell-ssh-keys.yaml

# Apply
sops -d secrets/ruflo/ruflo-shell-ssh-keys.yaml | kubectl apply -f -
```

If the pod was running before the bootstrap landed, the `cont-init.d/30-authorized-keys` hook only fires at boot — so the new keys won't be live until you trigger a re-copy:

```bash
kubectl exec -n ruflo-system deploy/ruflo -c ruflo-shell -- \
  bash -c 'cp /etc/ssh-keys/authorized_keys "${AGENT_HOME:-/home/agent}/.ssh/authorized_keys" \
           && chmod 600 "${AGENT_HOME:-/home/agent}/.ssh/authorized_keys"'
```

Or just `kubectl rollout restart deploy/ruflo -n ruflo-system` and let `cont-init.d` re-fire on the new pod. (The same hook bites every shell sidecar — there's a [frank-gotchas entry]({{< relref "/docs/building/29-ruflo#shareprocessnamespace-vs-s6-overlay-v3" >}}) for it.)

## Adding and Removing Tools

The shell sidecar's tool inventory is declarative — `apps/ruflo/manifests/configmap-shell-inventory.yaml`:

```yaml
data:
  inventory.yaml: |
    mise:
      - python@3.12
      - node@20
      - rust@stable
    npm-global:
      - "claude-flow@alpha"
      - "@openai/codex"
    pipx:
      - black
      - ruff
    cargo:
      - ripgrep
      - eza
    removed:
      mise: []
      npm-global: []
      pipx: []
      cargo: []
```

Edit, commit, push. ArgoCD syncs the ConfigMap. The boot-time reconciler picks up the new declaration on the next pod restart and installs/removes accordingly. To trigger immediately without a restart:

```bash
ssh ruflo -- ruflo-shell-reconcile
```

### The `removed:` Arrays

Removing a tool from the upper arrays does NOT uninstall it — that's intentional, so removing a declaration doesn't surprise an in-flight session. To actively uninstall, add the tool to the matching `removed:` list:

```yaml
removed:
  cargo: [eza]   # forces `cargo uninstall eza` on next reconcile
```

Once reconcile runs and reports the removal, you can drop the entry from `removed:` (or leave it as a record).

### Interactive Installs (Layer-3 Escape Hatch)

For discovery work, just install on the pod — `mise install`, `npm i -g`, `pipx install`, `cargo install`. All four managers persist their state under `${AGENT_HOME}` (i.e. `/home/agent/{.local/share/mise, .cargo/bin, .local/pipx, .local/share/mise/installs/node/20.../lib}`) which is mounted from the `ruflo-shell-home` PVC. Tools survive pod bounces.

```bash
ssh ruflo -- cargo install fd-find
kubectl rollout restart deploy/ruflo -n ruflo-system
ssh ruflo -- which fd     # /home/agent/.cargo/bin/fd — survived the bounce
```

### When to Promote to the Inventory

Promote an interactive install when:

1. You want the tool to survive a PV migration (the inventory ConfigMap is the source of truth — interactive installs are in PV state).
2. You want the next operator (or a freshly recreated PVC) to inherit the tool.
3. You want the boot-time reconcile and the Telegram-on-failure alert path to cover it.

Otherwise leave it interactive. Discovery week is meant to lean on this.

### The mise-Activation Workaround (Pending Upstream Fix)

`install-inventory.sh` in the current `agent-shell-base` has a known bug: after `mise install <tool>`, it doesn't run `mise use --global <tool>`, so subsequent steps that resolve `npm` / `python` fall through to the system installs and fail (EACCES on `/usr/lib/node_modules/`, missing `pyyaml`, etc.). Workaround on the live pod:

```bash
ssh ruflo -- 'mise use --global node@20 rust@stable python@3.12'
ssh ruflo -- 'mise exec -- pip install pyyaml'
ssh ruflo -- ruflo-shell-reconcile      # re-run after activation
```

The fix belongs in `agent-shell-base`. Once it ships, this workaround goes away.

## Reading the Install Log

Every reconcile run writes a per-tool log to `/var/log/cont-init.d/install-inventory.log` and a one-line MOTD summary to `/run/motd.dynamic`. The next SSH login sees the summary on the banner:

```
✓ ruflo-shell: 7 installed, 0 already present, 0 removed @ 2026-05-03T14:22:11Z
```

A `failed=N` count flips the banner to a warning glyph and triggers a Telegram alert via the `ruflo-shell-alerts` ExternalSecret. The alert contains the tool, the manager, the exit code, and the last 40 lines of the install log. Recovery flow:

```bash
ssh ruflo
sudo less /var/log/cont-init.d/install-inventory.log    # full log
ruflo-shell-reconcile                                   # re-try after fixing
```

If the Telegram alert path is silent on a known failure, check: (a) the `ruflo-shell-alerts` Secret exists and is `SecretSynced=True`; (b) the `notify-telegram.sh` helper is on PATH on the pod; (c) `FRANK_C2_TELEGRAM_BOT_TOKEN` and `FRANK_C2_TELEGRAM_CHAT_ID` exist in Infisical.

## Bumping Images

### `ruflo-shell` (Layer-1 changes)

Bump the `ruflo-shell` image when you want to change something baked **at build time** — i.e. anything that lives outside `${AGENT_HOME}`. Examples: a new tool that should live in `/usr/local/bin`, an s6 service unit, a `cont-init.d` hook fix, an MOTD template change.

The image is built by the `derio-net/agent-images` matrix CI. Workflow:

1. Land the change in the `agent-images` repo (PR against `main`).
2. CI builds and pushes `ghcr.io/derio-net/ruflo-shell:<short-sha>`.
3. The lockstep bumper opens a PR in `frank` updating `apps/ruflo/manifests/deployment.yaml` to the new SHA.
4. Merge → ArgoCD syncs → Deployment rolls.

### `ruflo-server` (upstream ruvocal)

The `ruflo-server` image is a thin wrapper around `ruvnet/ruflo` at a pinned upstream SHA. To bump:

1. Edit `agent-images/ruflo-server/Dockerfile` — change the `RUFLO_UPSTREAM_SHA=…` build arg.
2. CI rebuilds; new tag `ghcr.io/derio-net/ruflo-server:<short-sha>`.
3. Lockstep bumper PR in `frank`.

Read the upstream changelog before bumping — ruvocal has had a few "the data layer is now …" surprises (Mongo → RVF/Postgres). If `DATABASE_URL` start being honored at a new SHA, drop the parked `ruflo-db` and migrate state out of the RVF JSON file before flipping the image.

### When to Add to the Inventory Instead

If the change is "a new CLI tool the operator wants on the shell," prefer the inventory ConfigMap over rebuilding `ruflo-shell`. Inventory edits are PR-and-sync; image bumps are PR-build-PR-sync. Bake into the image only when:

- The tool needs to live in `/usr/local/bin` (root-owned, system-wide).
- The tool has heavy dependencies you don't want to install on every pod re-create.
- The tool participates in the s6/`cont-init.d` lifecycle.

Everything else: inventory.

## Backup and Recovery

Three Longhorn-backed PVCs:

| PVC | Size | Holds |
|-----|------|-------|
| `ruflo-data` | 5Gi | RVF JSON store (`/app/db/ruvocal.rvf.json` + indices) |
| `ruflo-shell-home` | 10Gi | mise installs, cargo bin, pipx, claude-flow CLI state, dotfiles |
| `ruflo-workspace` | 20Gi | shared between containers; project checkouts, scratch space |

Plus the `ruflo-db` StatefulSet's PVC (20Gi, parked).

Cluster-wide recurring backup policy applies (see [Operating on Storage & Backups]({{< relref "/docs/operating/02-storage-backups" >}})). Schedule, retention, and offsite (Cloudflare R2) target are inherited from the cluster default.

To restore a single PVC:

```bash
# 1. Scale Deployment to 0
kubectl scale deploy/ruflo -n ruflo-system --replicas=0

# 2. Delete the PVC
kubectl delete pvc ruflo-data -n ruflo-system

# 3. In Longhorn UI (192.168.55.201) → Volumes → ruflo-data backup → Restore
#    Restore as PVC named `ruflo-data` in namespace `ruflo-system`.

# 4. Scale back up
kubectl scale deploy/ruflo -n ruflo-system --replicas=1
```

The `ruflo-data` PVC is the one to back up religiously — it holds every hive, run, and conversation. The other two are reproducible from declarative state (image + inventory ConfigMap + git).

## Swarm-Run Cookbook

> **Corrected 2026-06-05, after the first real end-to-end attempt.** The
> original version of this section described a `claude-flow orchestrate
> --hive hive.yaml` flow that does not exist in the v3 CLI (`ruflo v3.10.x`),
> and an env block that belongs to the *ruvocal* container, not the shell
> sidecar. What follows is what actually works — discovered the honest way,
> by running it.

Three facts to internalize before the recipe:

1. **`claude-flow swarm`/`hive-mind` build coordination state only** —
   topologies, message bus, task queues, consensus. The *workers* that do
   the actual work are **Claude Code processes** (`hive-mind spawn
   --claude` / `claude -p`). No authenticated `claude` CLI on the shell =
   swarms that initialize beautifully and execute nothing.
2. **Worker tokens bill Anthropic, not LiteLLM.** The zero-direct-key,
   local-only posture covers ruvocal's chat surface; claude-flow workers
   ride the `claude` CLI's own auth (subscription OAuth or
   `ANTHROPIC_BASE_URL` override — see the local-models note below).
3. **Always use login shells over SSH** (`ssh ruflo` interactive, or
   `ssh ruflo 'bash -lc ...'`). sshd scrubs container env and only login
   shells get the `/etc/profile.d/` shims that put the mise-managed
   `claude-flow` on PATH. `ssh ruflo -- cmd` silently sees neither.

One-time prerequisite (persists on the `ruflo-shell-home` PVC):

```bash
ssh ruflo
claude          # then /login — subscription OAuth via browser
```

The recipe:

```bash
ssh ruflo

# 1. Sanity checks.
claude-flow --version             # ruflo v3.10.x
claude-flow status                # reaches ruvocal at localhost:3000; [STOPPED] pre-run is normal
claude -p "reply with exactly: AUTH-OK" --model haiku    # must print AUTH-OK

# 2. Work in a real directory — the swarm operates on cwd.
cd /workspace/projects/<repo>     # or a sandbox

# 3. Initialize coordination (cap agents — workers bill your subscription).
claude-flow swarm init -m 3
claude-flow swarm start -o "Rewrite README.md into a clean structured README and commit on branch swarm/readme" -s development
# prints agent slots, then tells you execution happens via Claude Code

# 4. Spawn the actual workers and hand them the task (queen-led variant):
claude-flow hive-mind init -t hierarchical-mesh
claude-flow hive-mind spawn --claude --count 2
claude-flow hive-mind task "Rewrite README.md ... commit on branch swarm/readme"

# 5. Watch.
claude-flow hive-mind status
claude-flow swarm status
# and the run shows up in the web UI at https://ruflo.cluster.derio.net

# 6. Clean up.
claude-flow hive-mind shutdown
```

The shell sidecar's own env carries only `LITELLM_BASE_URL` — the
`OPENAI_API_KEY`/`OPENAI_BASE_URL` pair lives in the **ruvocal** container
and powers the chat surface, not the swarm workers.

**Local models under the Claude Code harness?** Possible in principle:
`claude` honors `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`, and LiteLLM
speaks the Anthropic `/v1/messages` format, so workers *can* be pointed at
the local qwen lineup. Expect a real quality cliff — the Claude Code harness
(tool schemas, thinking, edit discipline) is tuned for Claude-family models.
Tracked as a future experiment, not part of this cookbook.

## Common Operations

### Restarting Ruflo

The Deployment uses `strategy: Recreate` (every container's PVC is RWO). Rolling updates would deadlock — the new pod can't mount any of the three volumes while the old pod holds them.

```bash
kubectl rollout restart deploy/ruflo -n ruflo-system
kubectl rollout status deploy/ruflo -n ruflo-system --timeout=120s
```

Expect ~30–60s of downtime while the new pod attaches the three PVCs and the s6 init in `ruflo-shell` finishes its `cont-init.d` chain. The web UI bounces; SSH connections drop.

### Forcing a Reconcile Without a Restart

```bash
ssh ruflo -- ruflo-shell-reconcile
```

That re-reads the inventory and installs/removes against the current state on the `ruflo-shell-home` PVC. Useful after a ConfigMap edit when you don't want to wait for a pod bounce.

### Manually Driving the Database Tier (Parked Postgres)

The `ruflo-db` StatefulSet is parked but green — kept around in case a future re-vendor flips ruvocal's data layer back to Postgres. Treat it as inert. If you need to confirm it's alive:

```bash
kubectl exec -n ruflo-system ruflo-db-postgresql-0 -c postgresql -- \
  psql -U ruflo -d ruflo -c '\dt'
```

If you're satisfied that the data layer will never flip back, the cleanup is: delete `apps/ruflo-db/`, delete its `Application` CR, drop the StatefulSet's PVC. Out of scope for this layer.

## Troubleshooting

### Pod Stuck `0/2` or `1/2`

Both containers must reach Ready. Common causes:

- **`ruflo` container `Pending` or `CrashLoopBackOff`** — most likely the LiteLLM virtual key is wrong (401 from upstream LiteLLM at boot) or the `ruflo-data` PVC is unwritable. Check:
  ```bash
  kubectl logs -n ruflo-system deploy/ruflo -c ruflo --previous | tail -30
  kubectl describe pvc ruflo-data -n ruflo-system
  ```
- **`ruflo-shell` container `Init:Error`** — the s6-overlay v3 init refuses to start as non-pid-1. If you see `s6-overlay-suexec: fatal: can only run as pid 1`, check that `shareProcessNamespace` is **not** set on the Pod spec (it's incompatible with agent-shell-base — see the building post and the gotchas file).
- **`ruflo-shell` container `Running` but sshd not answering** — `cont-init.d/30-authorized-keys` short-circuited because the SOPS Secret wasn't applied yet. Apply the Secret and follow the recovery in [Connecting → Authorised-Keys Bootstrap](#authorised-keys-bootstrap).

### 502 from the Web UI

Traefik returns 502 when ruvocal's `/api/v2/feature-flags` readiness probe is failing. The pod is up but the kubelet has marked it NotReady, so the Service has no endpoints.

```bash
kubectl get endpoints -n ruflo-system ruflo
kubectl describe pod -n ruflo-system -l app.kubernetes.io/name=ruflo
```

If the probe is failing, it's almost always upstream — LiteLLM is down, OpenRouter is rate-limiting, or the LiteLLM virtual key has been revoked.

### 401 Loop on Model Calls (After a Working Boot)

The LiteLLM virtual key (`RUFLO_LITELLM_KEY`) was revoked or rotated in Infisical. The pod has the cached value; ESO re-syncs every 5 minutes. Force a re-sync:

```bash
kubectl annotate externalsecret ruflo-llm -n ruflo-system \
  force-sync=$(date +%s) --overwrite
kubectl rollout restart deploy/ruflo -n ruflo-system
```

### Image / File Upload Returns 500

If attaching an image (or a tool fetching a file by URL) 500s with `TypeError: upload.once is not a function` — or uploads "succeed" but the image renders blank on re-open — the `RvfGridFSBucket` GridFS-shim parity fix is missing from the running bundle. This was fixed in ruflo-server `0ff7014` (frank #464); a regressed or pre-fix image brings it back.

```bash
# Confirm the fix is present in the deployed bundle:
kubectl -n ruflo-system exec deploy/ruflo -c ruflo -- \
  sh -c 'grep -l "objectMode: true" /app/build/server/chunks/database-*.js'
# expect a match. Then check live logs during an upload attempt:
kubectl -n ruflo-system logs deploy/ruflo -c ruflo --since=5m | \
  grep -E 'upload.once|ERR_INVALID_ARG_TYPE|is not a function' && echo PRESENT-BAD || echo CLEAN
```

If the grep finds no `objectMode` match, the deployed image predates the fix — bump `apps/ruflo/manifests/deployment.yaml` to a ruflo-server SHA ≥ `0ff7014`. Note that no Frank model currently advertises `multimodal:true`, so the UI image-attach control is gated off; the upload path is exercised by tool-fetched files and the HTTP route, not the attach button. See the GridFS-shim section in `docs/runbooks/frank-gotchas/paperclip-ruflo.md`.

### Telegram Alerts Stop

Check the alert ExternalSecret:

```bash
kubectl get externalsecret ruflo-shell-alerts -n ruflo-system
kubectl describe externalsecret ruflo-shell-alerts -n ruflo-system
```

The alert helper resolves `FRANK_C2_TELEGRAM_BOT_TOKEN` / `FRANK_C2_TELEGRAM_CHAT_ID` at send time. If those rotate in Infisical, ESO syncs the new values within 5 minutes.

## Gotchas

- **`shareProcessNamespace: true` is incompatible with the shell sidecar.** s6-overlay v3 must be pid 1 in its container's namespace. Cross-container debugging goes through `kubectl exec -c <other>` instead.
- **`/` is the wrong probe path.** ruvocal SSR-renders the model list at request time, so probes against `/` are full upstream-dependency checks. Use `/api/v2/feature-flags` (already configured).
- **`OPENAI_API_KEY` must be a LiteLLM virtual key**, not the OpenRouter key. LiteLLM authenticates against its own key store. Symptom of a wrong key: 401 on every model-list call, 500 on `/`.
- **The data layer is RVF, not Postgres.** Mounting a PVC at `/app/db` is essential — without it, every restart starts from a fresh empty `ruvocal.rvf.json` and every hive vanishes.
- **RVF's `GridFSBucket` is a shim** — its file upload/download/copy-on-fork paths needed a parity fix (real `Writable`/`Readable`/cursor) to stop 500-ing. Carried as a build-time patch, upstreamed as ruvnet/ruflo#2293. A pre-fix image regresses file uploads (see Troubleshooting above).
- **`mise install` doesn't activate.** Until the upstream `agent-shell-base` fix lands, manual `mise use --global …` after first reconcile is required (see workaround above).
- **The `cont-init.d/30-authorized-keys` hook only fires at pod boot.** Rotating SSH keys mid-life requires either a `kubectl exec` re-copy or a pod bounce.

## References

- [Building Post: Ruflo]({{< relref "/docs/building/29-ruflo" >}}) — architecture and rationale
- [Building Post: Agent Images and the VK-Local Sidecar]({{< relref "/docs/building/28-agent-images-sidecar" >}}) — the agent-shell-base lineage
- [Operating on Paperclip]({{< relref "/docs/operating/18-paperclip" >}}) — the org-chart counterpart
- [Operating on Storage & Backups]({{< relref "/docs/operating/02-storage-backups" >}}) — Longhorn snapshot policy
- [ruvnet/ruflo](https://github.com/ruvnet/ruflo) — upstream
