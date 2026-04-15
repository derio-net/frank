# Agent Images & vk-local Sidecar — Design

**Status:** Draft
**Layer:** `agents`
**Spec date:** 2026-04-15

## Goal

Break the coupling between the Kali image rebuild cadence and the VibeKanban (VK) fork release cadence, so that commits merged to `derio-net/vibe-kanban` main reach production without rebuilding `secure-agent-kali`. Do this in a way that also serves future secure-agent-pod tenants (Hermes, Content Factory, etc.) rather than special-casing VK.

## Motivation

Today, `secure-agent-pod` runs VibeKanban in "local mode" as a child process inside the Kali container. VK is installed via `npm install -g vibe-kanban@0.1.42`, baked into the `secure-agent-kali` image. This means:

- Fork commits never reach production — only what npm publishes (currently `0.1.42`, predating every fork change the team has landed).
- Shipping a VK fix requires a Kali image rebuild, even if nothing about Kali changed.
- `vk-remote` and `vk-relay` (already fork-built as one container image with two entrypoints, deployed separately) can drift in protocol version from the local server they talk to.

The prior attempt to put VK in its own container (three-container sidecar: VK server + Postgres + ElectricSQL) failed because VK in remote-server mode couldn't see the agent's workspace filesystem. That constraint is real: VK spawns worktrees and execs coding-agent CLIs (`claude`, `gh`) on the same filesystem where the agent lives. Separate pods with separate PVCs won't work for the local server.

## Constraints

1. **VK-local and the agent shell share one filesystem view.** Worktrees, SQLite DB, and coding-agent configs all live under `/home/claude`. Anything that execs `claude` must see the same `~/.claude/` directory.
2. **`agent-home` PVC is RWO** (per `apps/secure-agent-pod/manifests/pvc-agent-home.yaml`). Multiple pods cannot mount it simultaneously. Multiple containers in the same pod can.
3. **`secure-agent-pod` uses `strategy: Recreate`** (RWO PVC requires it). All image bumps bounce the whole pod. Bounces are ~20–40s on gpu-1.
4. **The secure-agent-pod pattern is a template** for future pods (Hermes, Content Factory — see `willikins/references/secure-pod-template.md`). Any tooling-layer decisions must assume ≥3 eventual consumers.
5. **Declarative-only.** Image tags are SHA-pinned in git; no `:latest` in manifests. Automation opens PRs; ArgoCD handles the sync.

## Architecture

### Image topology

```
ghcr.io/derio-net/agent-base:<sha>
  FROM debian:bookworm-slim
  + user claude:1000, /home/claude skeleton
  + claude, gh, git, node, bun, python3, uv, curl, jq, tini, supercronic
  + ca-certificates, shell defaults
      │
      ├──► ghcr.io/derio-net/secure-agent-kali:<sha>
      │       FROM agent-base + Kali archive keyring + sshd + pentest tools
      │       + kubectl, talosctl, omnictl, Infisical CLI
      │
      ├──► ghcr.io/derio-net/vk-local:<sha>
      │       FROM agent-base
      │       + COPY --from=ghcr.io/derio-net/vibe-kanban-build:<fork-sha> /server /usr/local/bin/vibe-kanban
      │       + kubectl, talosctl (same reasoning as kali — VK-launched claude sessions need parity with interactive claude sessions)
      │
      ├──► (future) ghcr.io/derio-net/hermes-agent:<sha>
      └──► (future) ghcr.io/derio-net/content-factory:<sha>
```

### Repo topology

Three repos, with clear ownership seams:

| Repo | Responsibility | CI output |
|------|----------------|-----------|
| `derio-net/agent-images` (new) | `base/Dockerfile`, `kali/Dockerfile`, `vk-local/Dockerfile`. Matrix CI builds all three on every push, tagged with the commit SHA. | `agent-base`, `secure-agent-kali`, `vk-local` images in GHCR |
| `derio-net/vibe-kanban` (existing fork) | Fork source. New job publishes the compiled `server` binary as a thin artifact image (`FROM scratch` + `COPY target/release/server /server`). | `vk-remote`, `vibe-kanban-build` in GHCR |
| `derio-net/frank` (existing) | Deployment manifests. New bumper workflow opens lockstep PRs updating image SHAs. | — |

`derio-net/secure-agent-kali` (current standalone repo) is absorbed into `agent-images` and archived.

### Pod layout (secure-agent-pod)

Two containers in one pod, sharing the `agent-home` PVC:

```yaml
spec:
  strategy:
    type: Recreate   # unchanged — RWO PVC
  template:
    spec:
      securityContext:
        fsGroup: 1000
      volumes:
        - name: agent-home
          persistentVolumeClaim: { claimName: agent-home }
        # ... agent-configs, ssh-keys unchanged
      containers:
        - name: kali
          image: ghcr.io/derio-net/secure-agent-kali:<sha>
          # UNCHANGED except: no more vibe-kanban child process, no port 8081
          volumeMounts:
            - { name: agent-home, mountPath: /home/claude }
          # ... rest unchanged

        - name: vk-local
          image: ghcr.io/derio-net/vk-local:<sha>
          ports:
            - { name: vk-http, containerPort: 8081, protocol: TCP }
          env:
            - { name: PORT, value: "8081" }
            - { name: HOST, value: "0.0.0.0" }
            - { name: VK_SHARED_API_BASE, value: "https://vk.cluster.derio.net" }
            - { name: VK_SHARED_RELAY_API_BASE, value: "https://vk.cluster.derio.net" }
          envFrom:
            - { secretRef: { name: agent-secrets-tier1, optional: true } }
            - { secretRef: { name: agent-secrets-tier2, optional: true } }
          volumeMounts:
            - { name: agent-home, mountPath: /home/claude }   # SAME PVC as kali
          securityContext:
            runAsUser: 1000
            runAsGroup: 1000
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
          # resources + probes similar to kali's current VK child-process footprint
```

The VibeKanban Service (currently targeting 8081 on the kali pod) retargets the sidecar — no manifest change needed if the Service selects by pod label, since it still hits the one pod.

### Why this satisfies the workspace constraint

Both containers mount `agent-home` at `/home/claude`. When vk-local execs `claude` under `/home/claude/repos/foo/worktrees/bar`, the working directory, the binary (from PVC-resident `~/.local/bin/claude` or image-baked `/usr/local/bin/claude`), and the config (`~/.claude/`) are all visible — same view, same inodes. The kali container sees the same worktree and can be used for interactive shell access to it. No remote-exec, no cross-pod IPC.

## Image-by-image design

### `agent-base`

Base for all agent pods. Discipline: **tools go here only if ≥2 children need them.**

Included:
- Identity: user `claude` (UID 1000, GID 1000), `/home/claude` directory owned by claude
- Init: `tini` as PID 1
- Certs: `ca-certificates`
- Shell: `bash`, sane `/etc/profile.d/` defaults
- Core CLIs: `claude`, `gh`, `git`, `git-lfs`, `curl`, `wget`, `jq`, `yq`
- Language runtimes: `node` (v22), `bun`, `python3`, `uv`
- Scheduler: `supercronic`

Explicitly NOT in base:
- `kubectl`, `talosctl`, `omnictl` — only kali and vk-local need them today; hermes/content-factory won't. Duplicated across those two Dockerfiles.
- `ffmpeg`, `imagemagick` — content-factory only.
- Piper, edge-tts — hermes only.
- `sshd` — kali only.

Base distro: `debian:bookworm-slim`. Rationale: Kali is Debian-derived (so `secure-agent-kali` can layer Kali repos on top); Node native modules and `claude`'s runtime expect glibc; Alpine/musl breaks native addons. Distroless is too minimal to allow per-child `apt install`.

### `secure-agent-kali`

`FROM ghcr.io/derio-net/agent-base:${AGENT_BASE_SHA}`. Adds:
- Kali archive keyring and meta packages (pentest toolset)
- sshd with non-root user configuration (same 2222 port as today)
- kubectl, talosctl, omnictl, Infisical CLI
- Existing `/opt/` config seeding and entrypoint (reused from current `secure-agent-kali` repo)

What drops from the current image:
- `npm install -g vibe-kanban@0.1.42`
- `vibe-kanban &` in entrypoint
- Port 8081 EXPOSE

The image stays structurally identical otherwise; the delta is "remove VK, inherit from base."

### `vk-local`

`FROM ghcr.io/derio-net/agent-base:${AGENT_BASE_SHA}`. Adds:
- `COPY --from=ghcr.io/derio-net/vibe-kanban-build:${VK_FORK_SHA} /server /usr/local/bin/vibe-kanban`
- kubectl, talosctl (duplicated with kali, as per discipline — promote on third consumer)
- Default `$HOME=/home/claude`, runs as UID 1000
- Entrypoint: `exec /usr/local/bin/vibe-kanban` (tini from base handles PID 1)
- No sshd, no cron, no supervisor — this is a single-process server container

### `vibe-kanban-build` (fork-side artifact image)

Built by a new job in `derio-net/vibe-kanban`'s CI on every main push. Multi-stage:
- Stage 1: `rust:1.83-bookworm` builder compiles `crates/server` in release mode
- Stage 2: `FROM scratch` + `COPY --from=builder /build/target/release/server /server`

Result: a <30MB image whose only purpose is to provide the binary to `vk-local`'s Dockerfile via `COPY --from=`. Never deployed anywhere.

Why an image and not a GitHub Release asset: `COPY --from` is the cleanest cross-build primitive in Docker, and it stays inside the GHCR ecosystem we already authenticate to.

## Build & bump pipeline

### `derio-net/agent-images` CI

One matrix workflow:

```yaml
# Pseudocode — real workflow in the plan
jobs:
  build-base:
    outputs: { sha: ${{ github.sha }} }
    steps:
      - build-push base/Dockerfile → ghcr.io/derio-net/agent-base:${{ github.sha }}
  build-children:
    needs: build-base
    strategy:
      matrix: [kali, vk-local]
    steps:
      - build-push ${{ matrix.image }}/Dockerfile
        --build-arg AGENT_BASE_SHA=${{ needs.build-base.outputs.sha }}
        --build-arg VK_FORK_SHA=${{ latest_vibe-kanban-build_sha }}  # only for vk-local
        → ghcr.io/derio-net/${{ matrix.image }}:${{ github.sha }}
  dispatch-bumper:
    needs: build-children
    steps:
      - repository_dispatch → derio-net/frank (event: agent-images-bumped, sha: <commit-sha>)
```

Optimization pass later: GHA path filters so a kali-only change doesn't rebuild vk-local. Not in v1 — correctness first.

### `derio-net/vibe-kanban` CI additions

Existing workflow builds `vk-remote`. Add:
- `build-server-artifact` job → `ghcr.io/derio-net/vibe-kanban-build:<fork-sha>`
- `dispatch-agent-images` step: fires `repository_dispatch` at `agent-images` to trigger a vk-local rebuild with the new fork SHA.

### `derio-net/frank` bumper

New workflow `.github/workflows/agent-images-bump.yaml`. Triggered by `repository_dispatch` from `agent-images`. For each received SHA:

1. Clone frank.
2. Update `apps/secure-agent-pod/manifests/deployment.yaml`:
   - `kali` container image → `ghcr.io/derio-net/secure-agent-kali:<sha>`
   - `vk-local` container image → `ghcr.io/derio-net/vk-local:<sha>`
3. Update `apps/vk-remote/manifests/deployment.yaml` **if** the `agent-images` commit was triggered by a vk-fork bump (the `vibe-kanban-build` SHA landed in vk-local this cycle) — bump both `vk-remote` and `relay` containers to the matching `vk-remote` image SHA.
4. Open PR: `chore(agents): bump agent-images to <sha>`. Include in the PR body: fork SHAs consumed, list of affected deployments.
5. Auto-merge label only if all CI passes. Opt-in, not default.

### End-to-end flow — fork commit case

```
fork main push
  └─► vibe-kanban CI: build vk-remote + vibe-kanban-build (fork-sha)
        └─► repository_dispatch to agent-images
              └─► agent-images CI: rebuild vk-local with new VK_FORK_SHA,
                  also rebuild base + kali (cheap rebuilds from cache if nothing changed)
                    └─► repository_dispatch to frank
                          └─► frank CI: open PR bumping vk-local, kali, vk-remote, relay
                                └─► review/merge → ArgoCD sync → pod bounce
```

Total wall-clock: 5–10 min from fork push to ArgoCD sync, excluding human review.

### End-to-end flow — tool update case

Direct commit to `agent-images` base/Dockerfile → base rebuild → both children rebuild → frank PR bumping kali + vk-local (no vk-remote, since fork didn't move) → merge → sync → bounce.

## Error handling & rollback

- **Bad vk-local image:** revert the frank PR that bumped it. ArgoCD re-syncs to the prior SHA. The bumper never force-merges; every bump is a reviewable commit.
- **Fork binary crashes on boot:** vk-local container CrashLoopBackOff. kali container stays up (SSH still works). The Service exposing 8081 drops because vk-local isn't ready; agent's interactive SSH session is unaffected. Fix: revert the bump.
- **Base image breaks kali but not vk-local (or vice versa):** both get the same base SHA in one bumper PR. If one child fails CI pre-merge, the PR doesn't merge. If it passes CI but fails at runtime, revert the PR and the base SHA effectively pins back.
- **Tool drift between kali and vk-local:** impossible by construction — both build from the same `agent-base:<sha>` every time.
- **PVC ownership drift:** both containers run as UID 1000; pod-level `fsGroup: 1000` ensures PVC files are group-writable by 1000 regardless of which container wrote last.

## Testing strategy

- **agent-images CI per-image smoke tests:** after build, `docker run --rm <image> <some-command>` — e.g., `vk-local: /usr/local/bin/vibe-kanban --version`, `kali: sshd -t`, `base: claude --version && gh --version && node --version`.
- **Staging namespace before bumping prod:** optional — deploy the new pod to a `secure-agent-pod-staging` namespace with a scratch PVC, confirm VK UI loads and a dummy task starts a worktree, then promote to prod. If that's too much ceremony for a dev pod, skip and accept revert-on-failure.
- **Bumper dry-run mode:** first deployment of the bumper workflow runs in "open PR without auto-merge label" mode for a few cycles to catch logic errors in the SHA-update step.

## Migration plan

Sequence:

1. **Create `derio-net/agent-images` repo** with `base/` Dockerfile; CI builds and pushes `agent-base:<sha>`.
2. **Port secure-agent-kali's Dockerfile into `agent-images/kali/`** as `FROM agent-base:<sha>`, drop VK bits. First build validated against current live pod — image should boot, sshd should listen, `claude` version matches.
3. **Add `agent-images/vk-local/` Dockerfile.** Stub binary (e.g., `/usr/local/bin/vibe-kanban` is a shell script echoing "not yet wired") to validate the image shape before touching the fork.
4. **Add vibe-kanban-build artifact job in the fork CI.** First run produces a real binary image. Wire `agent-images/vk-local/` `COPY --from=` against it.
5. **Deploy to secure-agent-pod:** update `deployment.yaml` to add the vk-local container. Keep kali's VK npm install for this one commit — both running side-by-side briefly is fine (vk-local binds 8081, kali's process fails to bind, that's OK).
6. **Cut over:** remove VK install + process from the (new) kali image. Verify VK UI works through the sidecar only.
7. **Ship the bumper workflow in frank.** First cycle: manually trigger it and review the PR by hand.
8. **Archive `derio-net/secure-agent-kali` repo.** Update references in `CLAUDE.md`, blog posts, specs.

Rollback at any step: revert the frank PR. The old npm-based kali image is still in GHCR; changing the tag back restores the prior behavior exactly.

## Decisions log

- **Multi-Dockerfile in one repo, not multi-target.** Readable ownership, clean CI matrix, avoids 600-line Dockerfiles.
- **Debian bookworm-slim base, not Alpine or distroless.** Glibc compatibility for `claude` and native Node modules; Kali layering requires Debian-derived; children still need `apt`.
- **`kubectl`/`talosctl` duplicated across kali and vk-local, not promoted to base.** Hermes and content-factory won't need them; promote on the third consumer, not pre-emptively.
- **vk-local as a sidecar in the existing pod, not a separate Deployment.** RWO PVC, single-filesystem view constraint. A separate pod would require RWX PVC + larger redesign; out of scope for v1.
- **Fork binary shipped via `vibe-kanban-build` artifact image, not a GitHub Release.** `COPY --from` is the idiomatic Docker cross-build primitive; stays in GHCR auth domain; no tarball download step.
- **Bumper PRs are reviewable, not auto-merged.** Opt-in auto-merge label comes after the workflow has been trusted for a few cycles.

## Out of scope (v2 candidates)

- **RWX PVC split** of kali + vk-local into separate Deployments. Would reduce bounce scope (fork bumps wouldn't drop SSH). Worth revisiting if pod bounces become painful.
- **Hermes and content-factory adoption.** Their Dockerfiles join `agent-images/` as new children, reusing `agent-base`. Each gets its own plan.
- **Intermediate `agent-dev` layer** (carries kubectl/talosctl for kali + vk-local). Only worth introducing if a third consumer needs the same dev toolchain.
- **Path-filtered CI** in agent-images (don't rebuild children when only their sibling's Dockerfile changed). Performance optimization, not correctness.
- **Multi-arch builds.** Current children are amd64 only. If a pod needs arm64 (raspi-1/2), add `docker buildx` platforms in the matrix.

## Open questions

- **VK database path stability:** the current npm-based VK writes SQLite to `~/.local/share/vibe-kanban/db.sqlite`. Confirm the `server` binary from the fork uses the same default path, or provide a config override. If path differs, a one-time migration step is needed during cutover.
- **Resource limits for the vk-local sidecar:** today's VK child process is implicitly capped by the kali container's 32Gi memory limit. Split out explicit requests/limits for vk-local — probably 500m CPU / 2Gi memory, to be measured.
- **Readiness probe for vk-local:** does the fork's `server` expose an HTTP `/health` endpoint, or do we TCP-probe 8081? Resolve before writing the deployment manifest.
- **Bumper PR coalescing:** when a fork commit fires two dispatches (one from the fork to trigger agent-images, one from agent-images to trigger frank), do we want one coalesced PR bumping vk-remote + vk-local + kali, or two PRs? A single coalesced PR is cleaner but requires the bumper to wait for both SHAs. Two PRs are simpler to implement but could interleave with other pushes. Lean toward a single coalesced PR keyed on the fork SHA; confirm in the plan.

## Success criteria

- A commit to `derio-net/vibe-kanban` main produces a bumper PR in frank within 10 minutes, updating vk-local + vk-remote + relay SHAs in lockstep.
- Merging the bumper PR results in a secure-agent-pod bounce that ends with vk-local serving the new fork binary, verified by `curl http://vk-local.secure-agent-pod.svc:8081/version` or equivalent.
- `secure-agent-kali` image contains no VibeKanban binary, no npm install of `vibe-kanban`, no `vibe-kanban &` in entrypoint.
- Adding a new agent pod (e.g., hermes) consists of adding one Dockerfile to `agent-images/hermes/`, not inventing a new image pipeline.
- Adding a new tool needed by two+ pods requires editing exactly one Dockerfile (the base).
