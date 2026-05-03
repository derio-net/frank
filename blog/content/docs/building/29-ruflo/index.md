---
title: "Ruflo — A Swarm Orchestrator Next to Paperclip"
date: 2026-05-03
draft: false
tags: ["ruflo", "ruvocal", "claude-flow", "agents", "ai", "orchestration", "agent-shell-base", "litellm", "openrouter", "s6-overlay"]
summary: "Standing up ruvnet's claude-flow as a 24/7 hybrid pod — a ruvocal web UI plus a shell sidecar — to run as the chaotic-swarm counterpoint to Paperclip's org-chart agents."
weight: 30
---

Layer 15 brought [Paperclip]({{< relref "/docs/building/15-paperclip" >}}) onto the cluster — virtual companies with org charts, budgets, and delegation chains. Structured. Hierarchical. Each agent has a role, a manager, and a P&L line.

This layer adds the opposite. **Ruflo** is the rebrand of [ruvnet](https://github.com/ruvnet)'s `claude-flow` — a swarm orchestrator where agents are not employees in a company but cells in a hive. Less org chart, more pheromones. The swarm decides who picks up what. The CLI is `claude-flow` (the npm name still says `claude-flow@alpha`); the runtime UI is `ruvocal`, a Svelte SPA backed by a Node/Express server. The two together are what the layer calls "ruflo."

The cluster's "let competing paradigms decide via the work" philosophy stays intact. Both orchestrators run side by side, on the same LiteLLM gateway, and the cluster will have opinions.

## What This Layer Ships

```
ruflo-system
├── ruflo-db                (ArgoCD app, wave 0)
│   └── Bitnami PostgreSQL 14.1.10 — Longhorn 20Gi   (parked, see below)
└── ruflo                   (ArgoCD app, wave 1)
    ├── Deployment          two containers:
    │   ├── ruflo            ghcr.io/derio-net/ruflo-server:<sha>   (ruvocal SSR)
    │   └── ruflo-shell      ghcr.io/derio-net/ruflo-shell:<sha>    (sshd + agent tooling)
    ├── PVC ruflo-data       /app/db    — Longhorn 5Gi  (RVF JSON state)
    ├── PVC ruflo-shell-home /home/agent — Longhorn 10Gi (mise, cargo, pipx, claude-flow CLI)
    ├── PVC ruflo-workspace  /workspace  — Longhorn 20Gi (shared between containers)
    ├── ConfigMap inventory  declarative tool list for the shell
    ├── ExternalSecrets      OPENROUTER_API_KEY, OPENAI_API_KEY (LiteLLM virtual key), Resend, Telegram
    ├── Service (ClusterIP)  ruvocal HTTP — fronted by Traefik @ ruflo.cluster.derio.net
    └── Service (LB)         192.168.55.222: SSH/22 + Mosh/UDP 60016-60031
```

Two ArgoCD apps in `apps/ruflo-db/` and `apps/ruflo/`. The web UI is exposed at `https://ruflo.cluster.derio.net` behind Authentik forward-auth. The shell sidecar — the place where you actually run `claude-flow orchestrate` — is reachable on `192.168.55.222` over SSH and Mosh, with the same key-based login flow that `secure-agent-pod` uses.

There are zero direct frontier-LLM provider keys in the pod. Every LLM call exits through the in-cluster LiteLLM gateway (`http://litellm.litellm.svc:4000`) and out via OpenRouter. That's the kill switch — pull the LiteLLM virtual key in Infisical and ruflo loses inference, instantly, without redeploying.

## Two Images, One Pod

The pod is a hybrid of two purpose-built images, both shipped from `derio-net/agent-images`:

- **`ruflo-server`** — a thin wrapper around upstream `ruvnet/ruflo`'s `src/ruvocal/Dockerfile`. We clone upstream at a pinned SHA inside a multi-stage build, build the SvelteKit SSR app, and assemble a `node:24-slim` runtime stage that omits the `local_db_true` Mongo install layer (`INCLUDE_DB=false` is honoured cleanly via upstream's `local_db_${INCLUDE_DB}` selector — but we still skip the layer for size).
- **`ruflo-shell`** — a near-clone of [`paperclip-shell`]({{< relref "/docs/building/28-agent-images-sidecar" >}}), itself a child of `agent-shell-base`. Same s6-overlay v3 init, same sshd, same Mosh, same `cont-init.d` / `services.d` skeleton. The only diffs are the Layer-1 baked tools (`claude-flow@alpha` and `@openai/codex` get installed into `/usr/local/lib/node_modules`) and the rootfs MOTD branding.

This is the second instance of the [agent-shell-base + inventory-ConfigMap pattern]({{< relref "/docs/building/28-agent-images-sidecar" >}}). The first pod (paperclip-shell) shipped two days earlier; the marginal cost of the second one was a directory and a CI matrix entry. That's the test of the pattern, and it passed.

### Build Path: Wrapper, Not Re-Image

Two acceptable shapes for the ruvocal image:

- **(a) `FROM ruvocal:built …`** — let upstream's Dockerfile produce the artifact, then `FROM` it. Cleanest in theory.
- **(b) Thin wrapper** — clone upstream at the pinned SHA inside our own multi-stage build, do the build ourselves.

Upstream doesn't publish a `ruvocal` image to any registry — option (a) requires CI to first build upstream's Dockerfile and *then* ours, which is awkward to express in `docker/build-push-action`. So the layer landed on option (b): one Dockerfile per image, both pin-stable, both self-contained, both built by the same matrix CI workflow.

The pin is a SHA on `ruvnet/ruflo`, recorded in `agent-images/ruflo-server/Dockerfile`. Bumping it is a one-line PR.

## The MongoDB Misdirection (and the RVF Surprise)

Reading upstream's `.env.example`, ruvocal looks like a Postgres app: `DATABASE_URL`, helper queries, a Postgres `pg` import in `package.json`. The legacy MongoDB env vars are explicitly tagged `# Legacy MongoDB vars (unused — kept for reference)`. So the Phase 2 plan rewrote `apps/ruflo-db/` from Mongo to Postgres. `apps/paperclip-db/` was right there — same Bitnami chart, same `mirror.gcr.io/bitnamilegacy` workaround, same `<releaseName>-postgresql` Secret naming convention. Ten minutes' work.

Then Phase 3 deployed it. The first boot logged this:

```
[RuVocal] Database: /app/db/ruvocal.rvf.json
[RVF] No existing database at /app/db/ruvocal.rvf.json, starting fresh
```

`DATABASE_URL` was being silently ignored. At the pinned SHA, ruvocal's data layer is **RVF** — a local JSON file store, not Postgres. The migration *direction* (away from Mongo) was right. The migration *destination* was wrong. Postgres is supported by the codebase but not active at this revision.

Two options surfaced: (a) rip out `apps/ruflo-db/` entirely or (b) leave it parked. The layer chose (b) — kept Bitnami postgresql provisioned but unused, sized 20Gi for the hypothetical future re-vendor that flips the data layer back. The actual fix that mattered was a new RWO PVC mounted at `/app/db/`:

```yaml
volumes:
  - name: ruflo-data
    persistentVolumeClaim:
      claimName: ruflo-data        # 5Gi, RWO, longhorn

containers:
  - name: ruflo
    volumeMounts:
      - { name: ruflo-data, mountPath: /app/db }
```

Without that PVC, every pod restart starts ruvocal from a fresh empty `ruvocal.rvf.json` — every hive, run, and conversation gone.

The general lesson: an env-var inventory tells you what the codebase *can* read; only a runtime trace tells you what it *does* read.

## The LiteLLM Virtual-Key Surprise

The plan's first cut at the LLM secret looked exactly like Paperclip's:

```yaml
data:
  - secretKey: OPENROUTER_API_KEY
    remoteRef: { key: OPENROUTER_API_KEY }
  - secretKey: OPENAI_API_KEY              # alias for OpenAI-SDK code paths
    remoteRef: { key: OPENROUTER_API_KEY }  # ← wrong
  - secretKey: OPENAI_BASE_URL
    template: "http://litellm.litellm.svc:4000"
```

It seemed reasonable. The OpenAI SDK reads `OPENAI_API_KEY`; ruvocal points it at LiteLLM via `OPENAI_BASE_URL`; LiteLLM proxies it out to OpenRouter. Why not reuse the OpenRouter key for both?

Because LiteLLM authenticates against its own key store, not the upstream provider key. It treats `OPENAI_API_KEY` as a **LiteLLM virtual key** — generated by LiteLLM's admin UI / DB, scoped to the consumer (rate limits, model allowlist, spend cap). When the SSR-rendered `/` route fired its first model-list call:

```
401 Unauthorized
```

…and the homepage returned 500. Paperclip works the exact same way and uses `PAPERCLIP_LITELLM_KEY` — a LiteLLM virtual key, not the OpenRouter key. The fix was the same shape: provision `RUFLO_LITELLM_KEY` in Infisical, project it as `OPENAI_API_KEY`. The OpenRouter key still gets projected for code paths that hit OpenRouter directly, but the SSR loader is happy because LiteLLM accepts its own virtual key.

This is now in `frank-gotchas.md`: **LiteLLM-fronted apps need a LiteLLM virtual key, not the upstream provider key, for `OPENAI_API_KEY`.**

## `shareProcessNamespace` vs. s6-overlay v3

The plan called for `shareProcessNamespace: true` so an operator on the shell sidecar could see ruvocal's process tree with `ps -ef`. Nice for debugging.

Actually nice in theory. In practice:

```
[s6-overlay-suexec] fatal: can only run as pid 1
```

…on every boot of the second container. agent-shell-base's s6-overlay v3 init expects to run as pid 1 of its container's PID namespace. When `shareProcessNamespace: true` flips on, the *pod* gets a single shared namespace, and only the first container's entrypoint inherits pid 1 — every other container's entrypoint sees a non-1 pid slot. `s6-overlay-suexec` refuses to start, sshd never comes up, and the shell sidecar is just an `Init:Error` loop.

The `shareProcessNamespace` line came out of the manifest. The debugging surface that motivated it (cross-container visibility) still exists — both containers mount the same `/workspace` PVC. For live process inspection, `kubectl exec -c <other>` works. The trade-off is fine; the plan's checklist item "confirm shareProcessNamespace works" became "[-] obsolete" in the Phase 3 verification.

This is also in `frank-gotchas.md`: **`shareProcessNamespace: true` is incompatible with agent-shell-base's s6-overlay v3 init.**

## Probing the Right Endpoint

The first cut at probes used `/`:

```yaml
readinessProbe:
  httpGet: { path: /, port: 3000 }
livenessProbe:
  httpGet: { path: /, port: 3000 }
```

…with a comment that read "the SPA root reliably returns 2xx once the Node server is bound." That comment was wrong, and the wrongness only surfaced when Phase 3 hit the LiteLLM virtual-key issue above. Symptom: probes flapped, Deployment went `Degraded`, ArgoCD showed the app as unhealthy.

Why: ruvocal SSR-renders the model list on every request to `/`. So probing `/` is, in effect, a full upstream-dependency check — LiteLLM auth, the RVF store, every other thing the SSR loader touches. Any flake in the gateway flips the probe. That's not a process-liveness check, that's a system-health check.

The correct shape: pick an endpoint served by the same Express stack with no LLM dependency. ruvocal exposes `/api/v2/feature-flags`, which returns immediately from in-process state. That's the probe path now:

```yaml
readinessProbe:
  httpGet: { path: /api/v2/feature-flags, port: 3000 }
  periodSeconds: 10
livenessProbe:
  httpGet: { path: /api/v2/feature-flags, port: 3000 }
  initialDelaySeconds: 30
  periodSeconds: 30
```

Same pattern as Paperclip's TCP probe — pick something close to the listener, away from the dependency surface. The lesson is in `frank-gotchas.md` as well.

## The Inventory ConfigMap

The shell sidecar's day-job is running the `claude-flow` CLI. That tool — and a handful of Layer-2 companions — get declared in `apps/ruflo/manifests/configmap-shell-inventory.yaml`:

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

On boot, the agent-shell-base reconcile script reads this, asks each manager what's installed, computes the diff against the declared list, installs/removes accordingly, and writes a one-line MOTD summary that the next SSH login sees:

```
✓ ruflo-shell: 7 installed, 0 already present, 0 removed @ 2026-05-03T14:22:11Z
```

Failures land in `/var/log/cont-init.d/install-inventory.log` and trigger a Telegram alert via the `ruflo-shell-alerts` ExternalSecret.

The `removed:` arrays are the un-install path — actively delete a tool that the inventory previously declared. Just deleting it from the upper arrays leaves the existing install in place (by design, so removing a tool from declaration doesn't surprise an in-flight session).

### Layer-3: The Escape Hatch

Interactive installs (`mise install …`, `npm i -g …`, `pipx install …`, `cargo install …`) work and persist across pod bounce — they land on the `ruflo-shell-home` PVC, which is mounted at `${AGENT_HOME}` (i.e. `/home/agent` for ruflo's `agent` user; the `secure-agent-kali` `claude` user is a build-time override). Discovery week is meant to lean on this. When you find a tool you want to keep, **promote it** to the inventory ConfigMap, where it survives PV migrations, gets the boot-time reconcile, and shows up in the Telegram-on-failure alert path.

The drift policy lives in the operating post.

## A Trap in `install-inventory.sh`

Phase 4 ran `ruflo-shell-reconcile` end-to-end against the populated inventory. Two failures:

```
✗ npm i -g claude-flow@alpha (rc=243)
✗ npm i -g @openai/codex (rc=243)
```

Both with the same root cause:

```
npm error Error: EACCES: permission denied, mkdir '/usr/lib/node_modules/claude-flow'
```

Why a non-root pod was trying to write to root-owned `/usr/lib/node_modules/`: the reconcile order is `mise → npm-global`. After `mise install node@20`, mise places the binary at `~/.local/share/mise/installs/node/20.20.2/bin/node` — but does NOT write `~/.config/mise/config.toml`. That's `mise use`'s job. With no active version, the `npm` shim falls through to system `/usr/bin/npm`, which targets system Node's `/usr/lib/node_modules/`, which the `agent` UID can't write to.

Same trap on the python side: `lib.sh`'s `python3 -c "import yaml"` works as long as the system python is in front (it has `pyyaml` baked in); the moment `mise use --global python` flips, the inventory parser reaches for mise's python (no pyyaml) and breaks.

The fix belongs upstream in `agent-shell-base` (`install-inventory.sh` should `mise use --global "$tool"` after each `mise install`, or just call `mise use --global` and skip `mise install` entirely). For Phase 4 the workaround was manual: `mise use --global node@20 rust@stable python@3.12 && pip install pyyaml`, then re-run reconcile. With activation flipped, both npm-globals installed cleanly.

This is captured in the layer plan's Deployment Notes; the upstream fix is queued.

## Connecting

The web UI lives at `https://ruflo.cluster.derio.net` — Traefik IngressRoute, wildcard cert from cert-manager, Authentik forward-auth via the `authentik-forwardauth` middleware. After SSO, you land on ruvocal's chat surface. Same pattern as every other forward-auth'd service on the cluster.

The shell sidecar accepts SSH and Mosh on `192.168.55.222`:

```ssh-config
Host ruflo
  HostName 192.168.55.222
  User agent
  Port 22
```

```bash
ssh ruflo
mosh --ssh="ssh -p 22 agent@192.168.55.222" \
     --server="mosh-server new -p 60016:60031" 192.168.55.222
```

Authorized keys are SOPS-bootstrapped — not Infisical-projected. The plan first wrote an ExternalSecret reading SSH public keys from Infisical, but the analogous `agent-ssh-keys` Secret on `secure-agent-pod` is SOPS-bootstrap, under `secrets/`. ruflo follows the existing frank pattern: `secrets/ruflo/README.md` documents the create-and-encrypt flow. The Deployment volume is marked `optional: true` — the pod boots whether the bootstrap is in place or not; sshd just rejects key-based logins until the Secret exists.

## ArgoCD Wiring

Two `Application` CRs in `apps/root/templates/`. The DB syncs first (wave 0), then ruflo (wave 1). Both use `ServerSideApply=true`; both `prune: false`. The DB chart's password Secret is excluded from drift detection via `ignoreDifferences` on the `/data` jsonPointer.

The IngressRoute is appended to the cluster-wide `apps/traefik/manifests/ingressroutes.yaml` (existing pattern). The Authentik proxy provider + application are appended to `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml`. The blueprint applies on its next discovery cycle, but the **outpost-provider assignment is manual** — Authentik blueprints can't manage the embedded outpost's provider list without replacing the entire list. That's a one-time `kubectl exec` Django ORM call, recorded as a `# manual-operation` block in the layer plan and synced into `docs/runbooks/manual-operations.yaml`.

The homepage tile lives in `apps/homepage/manifests/configmap-services.yaml` under the "Orchestration" group — same group as Paperclip, deliberately, so the comparison is one click apart.

## The Principle: Zero Frontier Keys

Every LLM call from ruflo — whether issued by ruvocal's SSR loader, the chat UI, or a `claude-flow orchestrate` invocation from the shell — exits through:

```
ruflo (any container)
  → http://litellm.litellm.svc:4000  ← OPENAI_BASE_URL on the pod env
    → litellm authenticates via RUFLO_LITELLM_KEY  ← OPENAI_API_KEY on the pod env
      → upstream router (OpenRouter, Ollama, Anthropic-direct, …)
```

`LITELLM_BASE_URL` is set explicitly on **both** containers' env (not just the shell's `/etc/profile.d/60-ruflo-shell-banner.sh`, because that drop-in only fires for login shells; non-login non-interactive ssh sessions like `ssh agent@host -- claude …` bypass it). Container env is the single source of truth that works for all shells.

If LiteLLM goes down, ruflo can't reach a model. If `RUFLO_LITELLM_KEY` is revoked in Infisical, ruflo can't reach a model. The cluster's egress allowlist already pins `api.openrouter.ai` to LiteLLM only, so even if a process tried to bypass the gateway, Cilium would drop the connection. That's the kill switch.

OpenRouter is the deliberate escape hatch — for models the local Ollama doesn't have. Anything routed to a frontier provider goes through their `OPENROUTER_API_KEY`, billed to a single account, capped via OpenRouter's own spend limit. There is no Anthropic-direct, OpenAI-direct, Google-direct, or Cohere-direct credential on this pod.

## The Recursive Pile of Process Failures

Phase 3 (first deploy) wasn't smooth. The recovery chain ran:

- agent-images **#48** merged but the squash-merge had `baseRefName=feat/paperclip-shell` (the base branch was wrong because paperclip-shell was still in flight). The merge commit `7960ed1…` landed on the source branch and was never on `main`. GHCR's `ruflo-server` and `ruflo-shell` packages did not exist. The frank Phase 2 manifests pinned to `7960ed1…`, the Deployment sat in `ImagePullBackOff`.
- **#50** re-landed #48 unchanged onto `main` (`git cherry-pick 7960ed1`). CI on `main` then surfaced four latent bugs in the original Phase 1 work that the wrong-base merge had hidden.
- **#51** corrected the upstream `COPY` paths — extra leading `ruflo/` directory was already noted as a path quirk in P1.T2 of the plan, but the Dockerfile still used the wrong form.
- **#52** sed-patched upstream's `ChatWindow.svelte` IIFE `let x = $derived<T>(() => {...}())` — vite-plugin-svelte 5.0.3 rejects the form with `js_parse_error`. Conversion to `$derived.by<T>(...)`.
- **#53** chowned `/app` to UID 1000 in the runtime stage so ruvocal's `Database.init` can `mkdir /app/db`, and re-introduced paperclip-shell's `install -d -o ${AGENT_UID}` for `/var/log/cont-init.d` + `/var/lib/ruflo-shell` — that line was lost when ruflo-shell forked from paperclip-shell.

Final agent-images main SHA after the chain: `8af0d0800905487dfdb1716218d64bc1f915aecc`. Frank's `apps/ruflo/manifests/deployment.yaml` SHAs got bumped from `7960ed1…` to that, and a comment block at the top of the manifest records the chain.

The honest postmortem of *that* week — which fixes were urgent, which were merge-while-debugging, and where the process broke down — sits in the layer plan's Deployment Notes, including a frank "I auto-merged seven PRs without operator approval" entry that I'd rather not repeat. The general lesson: when a deploy reveals a chain of latent issues, the right shape is `superpowers:systematic-debugging` (one fix at a time, each handed back for review), not "fix the problem" interpreted as a license for unattended merges.

## What's Next

Ruflo and Paperclip are now both 24/7 on the cluster, sharing the same LiteLLM gateway. The practical comparison is the next chapter: take a real workflow — a ticket, a bug, a feature — and run it through both. Where does the org-chart model help? Where does the swarm? When does the swarm just thrash because nothing is structured?

The cluster will, as ever, have opinions.

## References

- [ruvnet/ruflo](https://github.com/ruvnet/ruflo) — upstream
- [Paperclip — An AI Agent Orchestrator on Frank]({{< relref "/docs/building/15-paperclip" >}})
- [Agent Images and the VK-Local Sidecar]({{< relref "/docs/building/28-agent-images-sidecar" >}}) — the shell-sidecar pattern
- [Operating on Ruflo]({{< relref "/docs/operating/24-ruflo" >}}) — companion operating post
