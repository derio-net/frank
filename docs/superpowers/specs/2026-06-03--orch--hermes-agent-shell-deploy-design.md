# Deploy hermes-agent-shell pod on Frank (gpu-1)

**Date:** 2026-06-03
**Status:** Draft
**Layer:** `orch` (15 — AI Agent Orchestrator)
**Image source:** `derio-net/agent-images` — `hermes-agent-shell` (delivered by the
`2026-06-01-agent-shells-batch` plan, Phase 2)

## Problem

`agent-images` just shipped `hermes-agent-shell`: an SSH-able, single-harness
shell image that runs the Nous Research [`hermes` agent](https://github.com/NousResearch/hermes-agent)
wired BYOK to an OpenAI-compatible endpoint. Frank has no standalone pod
running it. We want a dedicated, operator-accessed pod on `gpu-1` so the
`hermes` agent can run against Frank's in-cluster LiteLLM gateway, with
PV-resident state (config, sessions, skills, memories) that survives restarts
and image bumps.

This is **not** the in-paperclip "hermes shim" (paperclip's `paperclip` container
already embeds a hermes binary via the shared `/paperclip` PVC). This is a
standalone shell pod whose only job is to host `hermes` interactively.

## Solution

A new ArgoCD app `hermes-agent-shell` (raw-manifests, single-source App-of-Apps
pattern) deploying a single-container Deployment on `gpu-1`, modeled on
`secure-agent-pod` (the existing standalone interactive-shell pod) and borrowing
the secret/inventory/MOTD wiring patterns from `paperclip-shell` / `ruflo-shell`.

```
agent-base
└── agent-shell-base
    └── hermes-agent-shell   ← image we deploy (BYOK → Frank LiteLLM)
```

### Container & placement

- **Image:** `ghcr.io/derio-net/hermes-agent-shell:95e719b9164e3e16b6e304202ff567f22aeed39c`
  — current `agent-images` main HEAD. That SHA includes the Phase 2
  `hermes-agent-shell` delivery (`56bc131`) and the `#105` reconcile fix
  (`95e719b`), and matches the agent-images SHA already pinned cluster-wide
  (paperclip-shell, secure-agent-kali, vk-local). Bumped thereafter by the
  existing agent-images-bump workflow.
- **Image user:** `agent` / `/home/agent` (UID/GID 1000), inherited from
  `agent-shell-base`. `HERMES_VERSION=0.15.2` baked (upstream tag `v2026.5.29.2`);
  floats forward via inventory `harnesses:` or an image bump.
- **Deployment:** `replicas: 1`, `strategy: Recreate` (RWO PVC cannot mount on
  two pods), `terminationGracePeriodSeconds: 45` (s6 `cont-finish.d` shutdown).
- **Placement:** `nodeSelector: kubernetes.io/hostname: gpu-1` +
  `tolerations: nvidia.com/gpu:NoSchedule` (defensive, per the gpu-1 gotcha).
  **No GPU requested** — inference is remote via LiteLLM; gpu-1 is chosen as
  Frank's largest CPU/RAM box (the same reason paperclip/secure-agent-pod sit
  there), not for the GPU.
- **securityContext:** pod `fsGroup: 1000`; container `runAsUser/Group: 1000`,
  `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`.
- **Resources:** requests `cpu: 500m` / `memory: 1Gi`; limits `cpu: "2"` /
  `memory: 4Gi`. Lighter than secure-agent-pod (no vk-local executor fleet); a
  single interactive `hermes` process plus the s6 supervision tree.
- **Probes:** TCP readiness + liveness on the sshd port (`2222`), matching the
  other shells.

### Storage & SSH access

- **PVC `hermes-agent-shell-home`** — `longhorn`, RWO, **20Gi** (matches
  `paperclip-shell-home` / `ruflo-shell-home`), mounted at `/home/agent`. Holds
  `~/.hermes/` (config, sessions, skills, memories) and any inventory-installed
  toolchain. PV-resident per the multi-harness standard.
- **SSH keys** — SOPS-bootstrap Secret `hermes-agent-shell-ssh-keys` in namespace
  `hermes-agent-shell`, stored at `secrets/hermes-agent-shell/`, mounted read-only
  at `/etc/ssh-keys`, volume `optional: true`. The image's
  `cont-init.d/30-authorized-keys` copies `/etc/ssh-keys/authorized_keys` into
  `~/.ssh/authorized_keys` on boot. Reuse the operator public key already paired
  with the other shells. SOPS-bootstrap (not ESO) mirrors `secure-agent-pod`'s
  `agent-ssh-keys`, `paperclip-shell-ssh-keys`, and `ruflo-shell-ssh-keys`.

### Services (SSH + Mosh)

A single combined LoadBalancer Service (the newer ruflo/paperclip single-IP
pattern — MixedProtocolLBService works on Cilium 1.17 — not secure-agent-pod's
two-IP split) on **`192.168.55.226`** (next free in the `192.168.55.x` pool;
last allocated is `.225`):

- TCP `22 → 2222` (non-root sshd inside the container).
- UDP **`60032–60047`** mosh range. Distinct from the in-use ranges
  (secure-agent-pod & paperclip-shell `60000–60015`, ruflo-shell `60016–60031`)
  so the per-shell client wrapper is unambiguous. Container env
  `MOSH_SERVER_NETWORK_TMOUT=3600`; client pins `mosh-server new -p 60032:60047`.

Client-setup helpers under `apps/hermes-agent-shell/client-setup/laptop/`
(`ssh-config.snippet`, `mosh-wrapper.sh`, `README.md`), mirroring the other
shells.

### BYOK auth (LiteLLM) & alerts

`hermes-agent-shell` is the documented exception to the multi-harness standard's
"no API tokens" auth contract: hermes has no subscription/OAuth login flow, so
inference auth is BYOK via `OPENAI_BASE_URL` + `OPENAI_API_KEY`, supplied by the
Frank manifest and sourced via ESO from Infisical.

- **Dedicated LiteLLM virtual key.** New Infisical entry `HERMES_LITELLM_KEY`,
  backed by its own LiteLLM virtual key (independently observable / revocable in
  LiteLLM, not entangled with paperclip's `PAPERCLIP_LITELLM_KEY`). ESO
  `ExternalSecret hermes-agent-shell-llm-key` → Secret exposing `OPENAI_API_KEY`.
- **Container env:**
  - `OPENAI_BASE_URL=http://litellm.litellm.svc:4000/v1` — Frank's real
    in-cluster LiteLLM DNS (the image README's `litellm.litellm-system` is an
    upstream-generic placeholder; Frank's namespace is `litellm`, confirmed
    against paperclip/ruflo which both use `litellm.litellm.svc:4000`).
  - `OPENAI_API_KEY` ← `hermes-agent-shell-llm-key` secret.
- **Telegram alerts** — ESO `ExternalSecret hermes-agent-shell-alerts` syncing
  `FRANK_C2_TELEGRAM_BOT_TOKEN` / `FRANK_C2_TELEGRAM_CHAT_ID`; consumed via
  `envFrom … secretRef … optional: true` (fail-open per the
  `envFrom.secretRef` gotcha). Powers the inventory installer's
  `notify-telegram.sh`.

### Inventory ConfigMap

ConfigMap `hermes-agent-shell-inventory` mounted at `/etc/hermes-agent-shell/`
(the image's reconcile reads `/etc/hermes-agent-shell/inventory.yaml`). Ship
**sparse** for the initial deploy so the boot reconcile is a clean no-op, with
the multi-harness standard's three keys present:

```yaml
harnesses:
  hermes: latest        # float; pin a PyPI version later if desired
mcp-servers:
  hermes: []
skills:
  hermes: []
```

### App CR conventions

Application CR at `apps/root/templates/hermes-agent-shell.yaml`, namespace via
`apps/root/templates/ns-hermes-agent-shell.yaml`:

- `project: infrastructure`, single `source` (`path: apps/hermes-agent-shell/manifests`).
- `syncPolicy.automated.selfHeal: true`, `prune: false`.
- `syncOptions: ServerSideApply=true`, `RespectIgnoreDifferences=true`,
  `CreateNamespace=false` (namespace templated separately, matching secure-agent-pod).
- `ignoreDifferences` on Secret `/data`.
- `resources-finalizer.argocd.argoproj.io` finalizer.
- ArgoCD Telegram sync-notification annotations (`subscribe.on-sync-running.telegram`,
  `subscribe.on-sync-succeeded.telegram`), mirroring secure-agent-pod.

## Scope

**In scope:** the new ArgoCD app (namespace, Deployment, combined SSH+Mosh
Service, home PVC, inventory ConfigMap, two ExternalSecrets), the Application CR
+ Namespace template, the SOPS ssh-keys bootstrap secret + its runbook,
client-setup helpers, the two manual-operation bootstraps, and the post-deploy
documentation (blog building+operating posts, README, frank-infrastructure.md
service-table row, runbook sync).

**Out of scope:** any change to `agent-images` (the image ships as-is);
exposing the shell on a web domain / homepage tile (it is SSH/Mosh-only);
cross-harness skill unification; pinning a specific hermes PyPI version or
pre-loading MCP servers / skills (inventory ships sparse — operator fills later);
replacing or touching the in-paperclip hermes shim.

## Phases

Two phases (operator chose this shape — a manual bootstrap gate, then the
agentic build-out):

- **Phase 0 — Manual bootstrap (human-only):** create the two secrets that must
  exist before the workload is meaningful.
  1. Mint a LiteLLM virtual key and store it as `HERMES_LITELLM_KEY` in Infisical.
  2. Generate/collect the operator SSH public key, build the
     `hermes-agent-shell-ssh-keys` Secret, SOPS-encrypt it into
     `secrets/hermes-agent-shell/`, and apply it out-of-band.
  Both are `# manual-operation` blocks → synced to the runbook.
- **Phase 1 — Agentic deploy + verify:** author all manifests, the Application
  CR + Namespace, ESOs, ConfigMap, client-setup helpers; sync via ArgoCD; verify
  end-to-end (pod Healthy, ESOs resolved, SSH in, MOTD shows the BYOK row,
  `hermes --version` runs, `OPENAI_BASE_URL` reachable); then the post-deploy
  checklist (building+operating blog posts, README, service-table row, runbook
  sync, status → Deployed).

Both phases depend only on Phase 0 → Phase 1 ordering. The pod boots even if
Phase 0 is incomplete (both secret volumes/refs are `optional: true`) — it just
can't reach LiteLLM and sshd accepts no keys until the bootstraps land. That is
the declarative-only exception for bootstrap secrets, by design.

## Manual operations

```yaml
# manual-operation
id: orch-hermes-litellm-virtual-key
layer: orch
app: hermes-agent-shell
plan: 2026-06-03--orch--hermes-agent-shell-deploy
when: Phase 0, before the pod can reach LiteLLM
why_manual: >
  LiteLLM virtual keys are minted via the LiteLLM admin API / UI and stored in
  Infisical; neither is reconstructable from git. ESO then syncs the key into
  the cluster. The key is per-agent so its budget/usage is independently
  observable and revocable.
commands:
  - "Mint a virtual key in LiteLLM (admin UI or /key/generate) scoped to the hermes agent."
  - "Store it in Infisical as HERMES_LITELLM_KEY (same project/env the other Frank keys use)."
verify:
  - "kubectl -n hermes-agent-shell get externalsecret hermes-agent-shell-llm-key -o jsonpath='{.status.conditions[0].reason}' → SecretSynced"
  - "kubectl -n hermes-agent-shell get secret hermes-agent-shell-llm-key -o jsonpath='{.data.OPENAI_API_KEY}' | base64 -d | head -c4 → non-empty"
status: pending

# manual-operation
id: orch-hermes-shell-ssh-keys
layer: orch
app: hermes-agent-shell
plan: 2026-06-03--orch--hermes-agent-shell-deploy
when: Phase 0, before SSH access works
why_manual: >
  SSH authorized_keys is a SOPS-bootstrap Secret applied out-of-band (matching
  secure-agent-pod / paperclip-shell / ruflo-shell). SOPS secrets must NOT be
  ArgoCD-managed.
commands:
  - "ssh-keygen or reuse the existing operator key already paired with the other shells."
  - "kubectl create secret generic hermes-agent-shell-ssh-keys --namespace=hermes-agent-shell --from-file=authorized_keys=<pubkey> --dry-run=client -o yaml > secrets/hermes-agent-shell/hermes-agent-shell-ssh-keys.yaml"
  - "sops --encrypt --in-place secrets/hermes-agent-shell/hermes-agent-shell-ssh-keys.yaml"
  - "sops --decrypt secrets/hermes-agent-shell/hermes-agent-shell-ssh-keys.yaml | kubectl apply -f -"
verify:
  - "kubectl -n hermes-agent-shell get secret hermes-agent-shell-ssh-keys"
  - "ssh -p 22 agent@192.168.55.226 'hermes --version' → prints a version"
status: pending
```

## Files to create

```
apps/hermes-agent-shell/manifests/deployment.yaml
apps/hermes-agent-shell/manifests/service.yaml                 # combined TCP 22 + UDP 60032-60047
apps/hermes-agent-shell/manifests/pvc-home.yaml
apps/hermes-agent-shell/manifests/configmap-inventory.yaml
apps/hermes-agent-shell/manifests/externalsecret-llm.yaml
apps/hermes-agent-shell/manifests/externalsecret-alerts.yaml
apps/hermes-agent-shell/client-setup/laptop/{ssh-config.snippet,mosh-wrapper.sh,README.md}
apps/root/templates/hermes-agent-shell.yaml                    # Application CR
apps/root/templates/ns-hermes-agent-shell.yaml                 # Namespace
secrets/hermes-agent-shell/README.md                           # SOPS bootstrap runbook
```

## Post-deploy checklist

- **Step 1 (external web exposure): SKIP** — SSH/Mosh-only operator service, no
  web UI, no homepage tile. (The frank-infrastructure.md service-table row is
  still added — it documents the LB IP, not a web exposure.)
- **Step 2:** building blog post (`orch` layer) via `/blog-post`; update
  `building/00-overview` series index + `cluster-roadmap.html`.
- **Step 3:** operating blog post (day-to-day: SSH in, run hermes, reconcile
  inventory, rotate keys, check MOTD).
- **Step 4:** `/update-readme`.
- **Step 5:** `/sync-runbook` (two manual-operation blocks above).
- **Step 6:** plan `**Status:**` → Deployed once observed end-to-end.

## Risks / open items

- **Two manual bootstraps gate first-green.** Acceptable: both refs are
  `optional: true`, so the pod boots regardless; hermes simply can't reach
  LiteLLM and sshd accepts no keys until they land. Standard declarative-only
  bootstrap exception.
- **Mosh range reuse vs. distinct.** Because each Service has its own LB IP, the
  same UDP range on a different IP would not actually collide; we allocate a
  distinct `60032–60047` purely to keep per-shell client wrappers unambiguous
  (matches the ruflo precedent).
- **gpu-1 port-forward flakiness gotcha** applies to verification — use
  `kubectl get application -n argocd -o wide` and `kubectl exec` for in-pod
  checks rather than `kubectl port-forward`.
