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
- `configmap.yaml`: add `TRUST_PROXY: "loopback,uniquelocal"` (Traefik reaches
  the pod from the RFC 1918 pod CIDR); add `PAPERCLIP_ANNOUNCEMENTS_ENABLED:
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
- `scripts/tests/test_config_reaches_the_process.py`: drop or rewrite the
  `apps/paperclip/manifests:paperclip` exemption whose stated reason (shell
  inventory/MOTD read per login) no longer exists; a test asserting the pod is
  pure upstream (single container, no init containers, image from
  `ghcr.io/paperclipai/paperclip`, no `agent-bin` on `PATH`) guards R1.
- Docs (R9): update `blog/content/docs/building/15-paperclip` and
  `operating/18-paperclip` with a dated "fresh start" section rather than
  rewriting history; README (`/update-readme`); remove the `.221` row from
  `agents/rules/frank-infrastructure.md`; in `frank-gotchas.md` and
  `docs/runbooks/frank-gotchas/paperclip-ruflo.md` mark the shell/shim/LiteLLM-agent
  entries historical; flip the obsolete manual-ops
  (`orch-paperclip-hire-hermes-litellm-agent`, `…-opencode-…`,
  `orch-paperclip-reconcile-shared-agent-clis`,
  `paperclip-shell-ssh-keys-sops-bootstrap`, and any other shell-only op)
  to a retired status via the plan's blocks + `/sync-runbook`; retire the
  acceptance-matrix rows that claim shell behaviour.
- Close #820 with a comment pointing at this PR, `--delete-branch`.

### Live sequence (manual operations, after merge)

The image change and the wipe share one maintenance window, in this order, so
the 57 v2026.916 migrations never matter against the data being thrown away:

1. **Pause the mirror first** (R8): set the companies repo's Gitea hook to
   `el-live-mirror-sync` `active: false` (Gitea API, admin creds from
   `gitea-secrets`). Assert via `GET …/hooks`.
2. **Merge**, wait for ArgoCD `paperclip` to sync, assert the live Deployment
   carries the new image and one container (never accept `Synced` alone).
3. **Wipe** (R5): delete PVCs `paperclip-data` and
   `data-paperclip-db-postgresql-0`, then the two pods. The StatefulSet
   recreates its PVC; ArgoCD (selfHeal) recreates `paperclip-data`. Postgres
   initialises fresh with the existing `paperclip-db-postgresql` password Secret
   (assert the Secret is untouched before deleting). Paperclip applies the full
   migration journal to an empty DB.
4. **Sweep the retired objects** (R2/R3, `prune: false`): delete Service
   `paperclip-shell`, PVC `paperclip-shell-home`, Secret
   `paperclip-shell-ssh-keys`, ExternalSecrets `paperclip-llm-key` and
   `paperclip-shell-alerts` (Owner policy deletes their Secrets), ConfigMaps
   `paperclip-hermes`, `paperclip-opencode`, `paperclip-shell-inventory`,
   `paperclip-shell-motd-tips`. Assert each is gone and `.221` is unallocated;
   assert the Application is `Synced` afterwards.
5. **Bootstrap** (R6): `kubectl exec deploy/paperclip -- pnpm paperclipai auth
   bootstrap-ceo`, open the invite through `https://paperclip.cluster.derio.net`
   (Authentik forward-auth still fronts it), create the admin.
6. **Prove it** (R7): create a throwaway company, connect Claude via
   Connections, hire one Claude-adapter agent, assign a trivial task, observe
   it complete. Keep the company as a sandbox or delete it — operator's call.

Steps 1–6 are handed over as one idempotent script under `scripts/tmp/`
(gitignored) plus the manual-operation blocks; the operator runs the parts
needing interactive sign-in.

### Resuming the mirror (out of scope, recorded for later)

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
  Authentik-fronted Traefik; if `PAPERCLIP_PUBLIC_URL`-derived URLs and
  `TRUST_PROXY` disagree, sign-in fails same-origin. Mitigation: R4 + verify
  via the request log's `req.ip` (upstream's own advice); fallback is the LB
  `192.168.55.212`, already in `PAPERCLIP_ALLOWED_HOSTNAMES`.
- **Chart re-renders the DB password:** if the postgres chart regenerated
  `paperclip-db-postgresql` on a re-render, a fresh PVC would initialise with
  one password and the app read another. Step 3 asserts the Secret before and
  after.
- **Native runner default on:** v2026.916 enables `enableNativeRunner` for
  self-hosted; it only affects explicitly configured agents, so the R7 proof
  uses the legacy Claude adapter path unless onboarding chooses otherwise.
