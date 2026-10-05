# Paperclip fresh start — wipe, pure upstream v2026.916.1, pause the companies mirror

**Date:** 2026-10-04
**Layer:** orch (Layer 15, fix/extension — no new blog post; existing posts updated)
**Status:** Draft
**Supersedes:** PR #820 (`chore(paperclip): bump to v2026.916.1`), which closes unmerged

## Context

The operator does not use the current Paperclip instance: it holds companies and
agents that do not work, and is wrapped in Frank-specific glue built up across
2026-05..08. The goal is a clean slate on **unmodified upstream Paperclip**, so
the operator can find out what Paperclip itself can do on Frank before the
reworked `agentic-stoa/companies` company is deployed onto it.

Findings that shaped the design:

1. **The server is already unpatched upstream** (`ghcr.io/paperclipai/paperclip:sha-8e6edcd`).
   Everything Frank-specific sits *around* it, as one dependency chain:
   - the `paperclip-shell` sidecar boots an inventory installer
     (`paperclip-shell-inventory` CM) that puts `opencode-ai` and a
     `hermes-agent` venv (pinned `v2026.4.16`) onto the shared `/paperclip`
     PVC under `agent-bin/`;
   - the `paperclip` container puts `agent-bin/` on `PATH`, reads
     `paperclip-opencode` / `paperclip-hermes` CMs (LiteLLM wiring), gets the
     LiteLLM virtual key as `OLLAMA_*`/`LITELLM_*` env, and the `hermes-init`
     init container seeds a writable `HERMES_HOME`;
   - the sidecar is also the operator's SSH/Mosh shell (`192.168.55.221`,
     SOPS SSH keys, own home PVC, Telegram alert secret, MOTD tips CM).
2. **Upstream v2026.916.1 ships the agent CLIs itself**: its production stage
   `npm install --global` installs `@anthropic-ai/claude-code`, `@openai/codex`,
   `opencode-ai`, `@google/gemini-cli` and `@moonshot-ai/kimi-code`. So the
   installer half of the sidecar is redundant for every bundled adapter, and the
   Claude/Codex sign-in path (Connections, v2026.916.0) needs no Frank glue.
3. **v2026.916.0 breaking change: `X-Forwarded-Host` is honoured only from a
   peer allowed by `TRUST_PROXY`** (Express `trust proxy` syntax; unset = trust
   nothing). Paperclip sits behind Traefik.
4. **First admin on an empty authenticated instance** is minted by
   `pnpm paperclipai auth bootstrap-ceo` inside the container (upstream
   `doc/DOCKER.md`), which prints a one-time invite URL.
5. **The companies → Paperclip sync is one-way.** A merge to
   `agentic-stoa/companies` `main` → Gitea mirror → Gitea push hook →
   `el-live-mirror-sync` (Tekton) → POST to a Paperclip routine trigger whose
   URL lives in Infisical (`STOA_LIVE_MIRROR_FIRE_URL`). Nothing flows from the
   Paperclip UI back to the repo. A wipe destroys the routine, so the trigger
   would fire at a dead URL on every merge.
6. **Every Frank Application here runs `prune: false`**, so deleting a manifest
   removes nothing live (frank-gotchas, ArgoCD). Each retired object needs an
   explicit delete, asserted gone.

## Requirements

R1. Paperclip runs the unmodified upstream image at v2026.916.1 (`sha-d554c47`), with no Frank-added containers, init containers, agent-CLI installs or adapter configuration in its pod.
R2. The `paperclip-shell` sidecar and everything that exists only for it are retired from git and from the cluster: the shell LoadBalancer (freeing `192.168.55.221`), its home PVC, SSH-key Secret, alert ExternalSecret, inventory and MOTD ConfigMaps, laptop client-setup files, and its entry in the agent-images bump workflow.
R3. The LiteLLM wiring that existed only for the Hermes/OpenCode shims is removed: `paperclip-hermes` and `paperclip-opencode` ConfigMaps, the `hermes-init` init container, the `agent-bin` `PATH`/`HERMES_HOME`/`XDG_CONFIG_HOME` env, the `OLLAMA_*` env and the `paperclip-llm-key` ExternalSecret.
R4. Paperclip trusts forwarded headers from Traefik: `TRUST_PROXY` is set so a request through `https://paperclip.cluster.derio.net` is treated as same-origin.
R5. The instance starts empty: the Paperclip database and the `/paperclip` data volume are wiped with no backup, so no prior company, agent, user, routine or run survives.
R6. The operator can sign in at `https://paperclip.cluster.derio.net` as the instance's first admin, created through upstream's bootstrap invite.
R7. One agent using a bundled adapter (Claude), authenticated through Paperclip's Connections with the operator's own subscription sign-in, completes one assigned task in a throwaway company.
R8. While the reworked company does not exist, merges to `agentic-stoa/companies` do not fire into Paperclip: the companies repo's Gitea push hook to `el-live-mirror-sync` is inactive, and the Tekton chain, its secrets and its ArgoCD Application stay deployed so resuming is a re-point plus a re-activate.
R9. Docs describe the new reality: the existing Layer 15 building/operating posts, README, `frank-infrastructure.md`, the Paperclip gotchas and the manual-operations runbook stop describing the shell, the shims and the hired LiteLLM agents as current.

## Design

### Repo changes (one PR)

**`apps/paperclip/manifests/`**
- `deployment.yaml`: image → `ghcr.io/paperclipai/paperclip:sha-d554c47` (comment
  records v2026.916.1 = `d554c4789ed3930f8a53ac9fdf6503b3187097da` and that the
  CLIs are bundled upstream); remove the `hermes-init` init container, the
  `paperclip-shell` container, the `PATH`/`XDG_CONFIG_HOME`/`HERMES_HOME`/
  `OLLAMA_*` env, the `paperclip-llm-key` envFrom, the opencode/hermes mounts,
  and the volumes `opencode-config`, `hermes-config`, `shell-home`,
  `shell-ssh-keys`, `shell-inventory`, `shell-motd-tips`. Keep: `data` PVC,
  `paperclip-config`, `paperclip-auth`, the optional `paperclip-brave` /
  `paperclip-resend` env, `DATABASE_URL`, the gpu-1 pin, `Recreate`, resources
  and probes (unchanged — sizing is out of scope).
- `configmap.yaml`: add `TRUST_PROXY: "loopback,10.244.0.0/16"` — loopback
  plus the pod CIDR only (Cilium `ipam.mode: kubernetes`, Talos default
  `podSubnets`; confirmed live from `kubectl get nodes -o
  jsonpath='{..podCIDR}'` before shipping). Traefik reaches the pod from a
  pod IP; a LAN client hitting `192.168.55.212` directly arrives from a
  `192.168.55.0/24` / node address and stays untrusted. `uniquelocal` was
  rejected: it covers all of RFC 1918, LAN included, and would hand any LAN
  host the forwarded-header trust v2026.916.0 took away. Add `PAPERCLIP_ANNOUNCEMENTS_ENABLED:
  "false"` alongside the existing telemetry opt-outs (new in v2026.916.0,
  default on, phones home to `pages.paperclip.ing`).
- Delete: `configmap-hermes.yaml`, `configmap-opencode.yaml`,
  `configmap-shell-inventory.yaml`, `configmap-shell-motd-tips.yaml`,
  `external-secret-llm.yaml`, `externalsecret-shell-alerts.yaml`,
  `pvc-shell-home.yaml`, `service-shell.yaml`.

**Elsewhere**
- Delete `apps/paperclip/client-setup/` and `secrets/paperclip/`
  (SOPS SSH-key bootstrap; the live Secret is deleted by manual-op).
- `.github/workflows/agent-images-bump.yml`: drop `paperclip-shell` from the
  image allowlist (the image itself stays buildable in agent-images; retiring
  it there is a separate repo and out of scope).
- `scripts/tests/test_config_reaches_the_process.py`: **drop** the
  `apps/paperclip/manifests:paperclip` exemption. After R1 the pod mounts no
  ConfigMap volume (`paperclip-config` is envFrom only), so
  `test_exempt_list_has_no_dead_entries` fails if the entry stays.
- New guard test (R1 + R3) over the rendered `apps/paperclip/manifests`:
  exactly one container and no init containers; image from
  `ghcr.io/paperclipai/paperclip`; no `agent-bin` on `PATH`; no
  `OLLAMA_*`, `HERMES_HOME` or `XDG_CONFIG_HOME` env; no reference to
  `paperclip-llm-key` (envFrom or secretKeyRef); no ConfigMap/Service/PVC/
  ExternalSecret named `paperclip-shell*`, `paperclip-hermes`,
  `paperclip-opencode` or `paperclip-llm-key` in the directory; `TRUST_PROXY`
  present and not containing `uniquelocal` or `true`.
- `apps/tekton/webhooks.yaml`: add a `note:` to the `agentic-stoa/companies`
  → `live-mirror-sync` entry saying the hook is deliberately `active: false`
  pending the reworked company, naming the resume manual-op — the file is
  declared desired state, and an unexplained dead trigger reads as a broken
  pipeline.
- Docs (R9): update `blog/content/docs/building/15-paperclip` and
  `operating/18-paperclip` with a dated "fresh start" section rather than
  rewriting history; README (`/update-readme`); remove the `.221` row from
  `agents/rules/frank-infrastructure.md`; in `frank-gotchas.md` and
  `docs/runbooks/frank-gotchas/paperclip-ruflo.md` mark the shell/shim/LiteLLM-agent
  entries historical, and likewise the `paperclip-shell` mentions in
  `docs/runbooks/frank-gotchas/agent-shells.md` (live-shell list) and the
  `.221` reference in `docs/runbooks/frank-gotchas/networking.md`; flip the
  obsolete manual-ops (`orch-paperclip-hire-hermes-litellm-agent`,
  `…-opencode-…`, `orch-paperclip-reconcile-shared-agent-clis`,
  `paperclip-shell-ssh-keys-sops-bootstrap`, and any other shell-only op) to
  a retired status via the plan's blocks + `/sync-runbook`, and correct the
  `orch-create-infisical-secrets` note that calls `PAPERCLIP_LITELLM_KEY` /
  `paperclip-llm-key` "still required"; fix `scripts/paperclip-purge-fs.sh`
  (it execs into `-c paperclip-shell` and keeps `agent-bin`) to exec into the
  `paperclip` container; retire acceptance-matrix rows `paperclip-shell`
  (the 2/2-containers claim) and `paperclip-litellm-agents-operable`.
- Close #820 with a comment pointing at this PR, `--delete-branch`.

### Live sequence (manual operations, after merge)

Merging rolls the new image straight onto the **old** database: upstream runs
its whole pending migration set against data that step 3 discards. That run
is wasted work and may crashloop, but its outcome is harmless by construction:
whatever state it leaves is deleted minutes later. (The pending count is not
asserted here; the repo's rule is to count it from the journal diff, and on
this path it does not matter.) Expect `layer-15-workflows-down` (paperclip-system
Deployment/StatefulSet unavailable, `for: 5m`) to fire during steps 2–3; it
must have resolved before step 6.

1. **Pause the mirror first** (R8): set the companies repo's Gitea hook to
   `el-live-mirror-sync` to `active: false` (Gitea API, admin creds from
   `gitea-secrets`). Assert `active: false` via `GET …/hooks`.
2. **Merge.** Wait on the `paperclip` Application's sync **operation** reaching
   the merge revision and on the live Deployment carrying the new image with a
   single container. Do not wait on `Synced`: under `prune: false` the app is
   legitimately `OutOfSync` until step 4 deletes the orphans.
3. **Wipe** (R5). Order matters: deleting a PVC under a running pod only marks
   it Terminating, and a StatefulSet creates claims only when it creates a pod.
   a. Assert Secret `paperclip-db-postgresql` exists and record its
      `resourceVersion`. It is chart-generated, and `ignoreDifferences` on
      `/data` keeps the live password; it must not change.
   b. Record the UIDs of PVCs `data-paperclip-db-postgresql-0` and
      `paperclip-data`.
   c. Database first: `kubectl delete pvc data-paperclip-db-postgresql-0
      --wait=false`, then delete pod `paperclip-db-postgresql-0`. Wait for the
      old PVC to be gone, a new one Bound with a **different UID**, and the DB
      pod Ready. If the pod sits Pending on the deleted claim, delete the pod
      again; the StatefulSet then creates the claim.
   d. Then the data volume: `kubectl delete pvc paperclip-data --wait=false`,
      then the paperclip pod. ArgoCD selfHeal recreates `paperclip-data`.
      Wait for a new UID, Bound, and the pod Ready on the empty DB (the full
      migration journal applies here).
   e. Re-assert the DB Secret's `resourceVersion` is unchanged.
4. **Sweep the retired objects** (R2/R3; `prune: false`): delete Service
   `paperclip-shell`, PVC `paperclip-shell-home`, Secret
   `paperclip-shell-ssh-keys`, ExternalSecrets `paperclip-llm-key` and
   `paperclip-shell-alerts`, ConfigMaps `paperclip-hermes`,
   `paperclip-opencode`, `paperclip-shell-inventory`,
   `paperclip-shell-motd-tips`. Assert each is absent, **including Secrets
   `paperclip-llm-key` and `paperclip-shell-alerts`** (Owner policy should GC
   them; assert, don't assume), and that no Service holds `192.168.55.221`.
   Then the Application must be `Synced`.
5. **Bootstrap** (R6): `kubectl exec deploy/paperclip -- pnpm paperclipai auth
   bootstrap-ceo`, open the invite through `https://paperclip.cluster.derio.net`
   (Authentik forward-auth still fronts it), create the admin.
6. **Prove it** (R7): create a throwaway company, connect Claude via
   Connections, hire one Claude-adapter agent, assign a trivial task, observe it
   complete. Then `kubectl rollout restart deploy/paperclip`, assign a second
   trivial task, and observe it complete without re-signing in. This proves the
   credential lives somewhere durable (DB or `/paperclip`), not in an
   ephemeral home directory. If it does not survive, the fix belongs in this
   PR (point the CLI home at the PVC) before the row flips. Keep the company as
   a sandbox or delete it: operator's call.

Steps 1–6 are handed over as one idempotent script under `scripts/tmp/`
(gitignored) plus the manual-operation blocks. The operator runs the parts
that need interactive sign-in.

## Test Plan

| Req | Check | When |
|-----|-------|------|
| R1, R3 | Guard test over `apps/paperclip/manifests` (see Design) | CI |
| R2 | Guard test (no shell manifests/workflow entry) + step 4 absence assertions incl. Secrets and `.221` | CI + post-merge |
| R4 | Paperclip request log shows `req.ip` = a `10.244.x.x` Traefik pod IP for a request via `paperclip.cluster.derio.net`; a direct `curl -H 'X-Forwarded-Host: evil.invalid' http://192.168.55.212:3100/…` is not treated as that host (same-origin guard rejects / host ignored) | post-merge |
| R5 | New PVC UIDs ≠ recorded old UIDs (step 3); before step 5, the health endpoint reports bootstrap not done and the UI shows no companies | post-merge |
| R6 | Operator signs in as admin through the public URL | post-merge |
| R7 | Task completes, survives a pod restart (step 6) | post-merge |
| R8 | Hook `active: false` via Gitea API; after the next natural merge to the companies repo, no new `live-mirror-sync-*` TaskRun in `tekton-pipelines`. No test push to the third-party repo. `webhooks.yaml` note present (CI) | post-merge + CI |
| R9 | `git grep` finds no current-tense `paperclip-shell` / `192.168.55.221` / `paperclip-llm-key` outside historical sections, implemented plans and blog history | CI-time check in the PR |

## Resuming the mirror (out of scope, recorded for later)

When the reworked company is imported and its routine exists: put the new
routine's public trigger URL in Infisical `STOA_LIVE_MIRROR_FIRE_URL`, force-sync
the `live-mirror-paperclip` ExternalSecret, re-activate the Gitea hook, and
verify one merge produces a successful TaskRun. Recorded as a `planned`
manual-operation so it is not lost.

## Out of scope

- Exploring Paperclip's capabilities beyond the R7 proof (separate effort).
- Reworking the companies repo; resuming the mirror.
- Re-adding local-model (LiteLLM) agents — revisit only if exploration needs it.
- Revoking the `PAPERCLIP_LITELLM_KEY` virtual key in LiteLLM / Infisical, and
  retiring the `paperclip-shell` image in agent-images (follow-up issues).
- Paperclip resource sizing / node placement.

## Risks

- **Bootstrap invite vs forward-auth:** the invite URL is opened through
  Authentik-fronted Traefik. If `PAPERCLIP_PUBLIC_URL`-derived URLs and
  `TRUST_PROXY` disagree, sign-in fails the same-origin guard. Mitigation: R4's
  check (`req.ip` is a Traefik pod IP). With `TRUST_PROXY` scoped to the pod
  CIDR, the LB `192.168.55.212` fallback still works for the raw `Host`, but
  forwarded headers from it are ignored by design.
- **Chart re-renders the DB password:** if the postgres chart regenerated
  `paperclip-db-postgresql` on a re-render, a fresh PVC would initialise with
  one password and the app read another. Step 3 asserts the Secret before and
  after.
- **Native runner default on:** v2026.916 enables `enableNativeRunner` for
  self-hosted; it only affects explicitly configured agents, so the R7 proof
  uses the legacy Claude adapter path unless onboarding chooses otherwise.
