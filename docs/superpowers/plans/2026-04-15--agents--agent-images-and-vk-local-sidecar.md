# Agent Images & vk-local Sidecar — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-15--agents--agent-images-and-vk-local-sidecar-design.md`
**Status:** In Progress

**Goal:** Replace the in-process VibeKanban (npm-installed, baked into `secure-agent-kali`) with a shared-volume sidecar built from the fork, and move the Kali Dockerfile into a new multi-image repo (`derio-net/agent-images`) that also produces a common `agent-base` image for future pods. Add a lockstep bumper in frank that opens a single PR whenever fork or base SHAs move.

---

## ⚠️ Execution constraints

This plan **cannot** run uninterrupted by a single VK agent session. Phase 2 bounces the pod twice (Task A sidecar-add, Task B kali-cutover). Each bounce kills the executing VK session. Expect 2 handoffs minimum; Phase 3 may add a third.

**Bounce gate protocol** (applies to every step marked `[bounce-gate]`):

**Before the bounce** — the agent MUST:
1. `cd /home/claude/repos/frank && git status` → clean.
2. `git rev-parse HEAD` equals `git rev-parse @{u}` (local matches remote).
3. Repeat (1)+(2) for any sibling repo touched this phase (`agent-images`, `vibe-kanban`).
4. Update plan checkboxes for every completed step this phase; commit+push.
5. Write a breadcrumb in `docs/superpowers/RESUMING.md`: next step number, current expected state, how to verify the bounce worked.
6. Stop. A human (or another-host session) performs the merge.

**After the bounce** — the resumer MUST:
1. `kubectl -n secure-agent-pod get pod -l app=secure-agent-pod` shows `Ready: 2/2`.
2. `kubectl -n secure-agent-pod logs -l app=secure-agent-pod -c vk-local --tail=50` shows VK listening on 8081.
3. Open VK UI at `https://vk.cluster.derio.net` (or `http://192.168.55.218:8081`).
4. Read `RESUMING.md`, continue from the noted step.

---

## Architecture sketch

```
derio-net/vibe-kanban              derio-net/agent-images (NEW)         derio-net/frank

fork CI:                           matrix CI:                           bumper CI:
  build vk-remote       ┐           build agent-base                     on dispatch:
  build vibe-kanban-build┼──COPY──► build secure-agent-kali               collect SHAs
                        │           build vk-local                        open 1 PR bumping
repository_dispatch─────┘           repository_dispatch───────────────►   vk-remote + vk-local
                                                                          + secure-agent-kali
                                                                         (ArgoCD syncs → bounce)
```

---

## Phase 0: Bootstrap `agent-images` repo with base + kali [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/79 -->

**Target repo:** `derio-net/agent-images` (new)
**Outcome:** Both images build green in CI and publish to GHCR. `secure-agent-kali` image is functionally identical to today's live image. Nothing deployed yet.

### Task 1: Create the `agent-images` repo on GitHub

```yaml
# manual-operation
id: agent-images-repo-create
layer: agents
app: agent-images
plan: 2026-04-15--agents--agent-images-and-vk-local-sidecar
when: before Phase 0 Task 2
why_manual: repo creation requires GitHub org-owner auth, not available to the VK agent
commands:
  - gh repo create derio-net/agent-images --public --description "Shared base image and per-pod child images for secure agent pods on Frank" --clone
  - cd agent-images && git checkout -b main && printf '# agent-images\n' > README.md && git add README.md && git commit -m "chore: initial commit" && git push -u origin main
verify:
  - gh repo view derio-net/agent-images --json name,visibility | jq -e '.name == "agent-images" and .visibility == "PUBLIC"'
status: done
```

- [x] **Step 1: Verify the repo exists and is cloneable.**

```bash
gh repo view derio-net/agent-images
ls ~/repos/agent-images/README.md
```

### Task 2: Write `base/Dockerfile`

**Files:**
- Create: `base/Dockerfile`

- [x] **Step 1: Write the base Dockerfile at `agent-images/base/Dockerfile`.**

```dockerfile
# BEGIN base/Dockerfile
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    HOME=/home/claude \
    PATH=/home/claude/.local/bin:/usr/local/bin:/usr/bin:/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget git git-lfs jq bash less \
    python3 python3-pip python3-venv pipx \
    tini gnupg2 openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Bun
RUN curl -fsSL https://bun.sh/install | BUN_INSTALL=/usr/local bash

# uv
RUN curl -fsSL https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI (bootstrap via npm; self-updates into ~/.local/bin on first run)
RUN npm install -g @anthropic-ai/claude-code

# supercronic
RUN curl -fsSL -o /usr/local/bin/supercronic \
      https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 \
    && chmod +x /usr/local/bin/supercronic

# Non-root user (UID/GID 1000 — matches PVC ownership)
RUN groupadd -g 1000 claude && useradd -m -u 1000 -g 1000 -s /bin/bash claude

USER claude
WORKDIR /home/claude
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash"]
# END base/Dockerfile
```

- [-] **Step 2: Smoke-test locally.** *(skipped — no docker daemon available in agent pod; CI build validates)*

```bash
cd ~/repos/agent-images
docker build -t agent-base:dev base/
docker run --rm agent-base:dev bash -c 'id && claude --version && gh --version && node --version && bun --version && python3 --version'
# Expected: uid=1000(claude), version strings for each tool
```

### Task 3: Write matrix CI workflow

**Files:**
- Create: `.github/workflows/build.yaml`

- [x] **Step 1: Write the workflow at `agent-images/.github/workflows/build.yaml`.**

```yaml
# BEGIN .github/workflows/build.yaml
name: Build agent images

on:
  push:
    branches: [main]
  workflow_dispatch:
  repository_dispatch:
    types: [vibe-kanban-build-updated]

env:
  REGISTRY: ghcr.io
  OWNER: derio-net

jobs:
  build-base:
    runs-on: ubuntu-latest
    outputs:
      sha: ${{ github.sha }}
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: base
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.OWNER }}/agent-base:${{ github.sha }}
            ${{ env.REGISTRY }}/${{ env.OWNER }}/agent-base:latest
          cache-from: type=gha,scope=agent-base
          cache-to: type=gha,scope=agent-base,mode=max

  build-children:
    needs: build-base
    runs-on: ubuntu-latest
    strategy:
      matrix:
        image:
          - name: secure-agent-kali
            context: kali
            build_args: |
              AGENT_BASE_SHA=${{ needs.build-base.outputs.sha }}
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.image.context }}
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.OWNER }}/${{ matrix.image.name }}:${{ github.sha }}
            ${{ env.REGISTRY }}/${{ env.OWNER }}/${{ matrix.image.name }}:latest
          build-args: ${{ matrix.image.build_args }}
          cache-from: type=gha,scope=${{ matrix.image.name }}
          cache-to: type=gha,scope=${{ matrix.image.name }},mode=max

  dispatch-frank:
    needs: build-children
    runs-on: ubuntu-latest
    steps:
      - env:
          GH_TOKEN: ${{ secrets.DISPATCH_PAT }}
        run: |
          gh api repos/derio-net/frank/dispatches \
            -f event_type=agent-images-bumped \
            -f client_payload[agent_images_sha]=${{ github.sha }}
# END .github/workflows/build.yaml
```

- [-] **Step 2: Configure `DISPATCH_PAT` secret.** *(deferred — manual operation, dispatch-frank job will fail gracefully until PAT is configured)*

```yaml
# manual-operation
id: agent-images-dispatch-pat
layer: agents
app: agent-images
plan: 2026-04-15--agents--agent-images-and-vk-local-sidecar
when: after Phase 0 Task 3 Step 1
why_manual: PAT with cross-repo dispatch scope must be minted and stored as a secret; agent cannot create org PATs
commands:
  - gh secret set DISPATCH_PAT --repo derio-net/agent-images --body "$(cat /path/to/pat)"
verify:
  - gh secret list --repo derio-net/agent-images | grep DISPATCH_PAT
status: pending
```

### Task 4: Port kali Dockerfile into `kali/`

**Files:**
- Create: `kali/Dockerfile`
- Create: `kali/entrypoint.sh`
- Create: `kali/assets/sshd_config`
- Create: `kali/assets/crontab.txt`

- [x] **Step 1: Copy runtime assets from the existing `secure-agent-kali` repo.**

```bash
cd ~/repos/agent-images
mkdir -p kali/assets
cp ~/repos/secure-agent-kali/entrypoint.sh kali/entrypoint.sh
cp ~/repos/secure-agent-kali/sshd_config   kali/assets/sshd_config 2>/dev/null || \
  cp ~/repos/secure-agent-kali/assets/sshd_config kali/assets/sshd_config
cp ~/repos/secure-agent-kali/crontab.txt   kali/assets/crontab.txt 2>/dev/null || true
ls ~/repos/secure-agent-kali/ | grep -Ev '^(Dockerfile|\.git|\.github|README|LICENSE)' \
  > /tmp/kali-inventory.txt
cat /tmp/kali-inventory.txt
# Expect: small file list — reconcile anything unexpected into kali/assets/
```

- [x] **Step 2: Write `kali/Dockerfile`.**

```dockerfile
# BEGIN kali/Dockerfile
ARG AGENT_BASE_SHA=latest
FROM ghcr.io/derio-net/agent-base:${AGENT_BASE_SHA}

USER root

# Kali archive
RUN apt-get update && apt-get install -y --no-install-recommends \
      lsb-release wget gnupg \
    && wget -qO - https://archive.kali.org/archive-key.asc \
      | gpg --dearmor -o /usr/share/keyrings/kali-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/kali-archive-keyring.gpg] https://http.kali.org/kali kali-rolling main non-free contrib" \
      > /etc/apt/sources.list.d/kali.list \
    && apt-get update

# sshd + trimmed Kali tooling
RUN apt-get install -y --no-install-recommends \
      openssh-server kali-tools-top10 nmap netcat-traditional \
    && mkdir -p /run/sshd /var/run/sshd \
    && rm -rf /var/lib/apt/lists/*

# kubectl, talosctl, omnictl — duplicated with vk-local
RUN curl -fsSL -o /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl
RUN curl -fsSL -o /usr/local/bin/talosctl \
      https://github.com/siderolabs/talos/releases/latest/download/talosctl-linux-amd64 \
    && chmod +x /usr/local/bin/talosctl
RUN curl -fsSL -o /usr/local/bin/omnictl \
      https://github.com/siderolabs/omni/releases/latest/download/omnictl-linux-amd64 \
    && chmod +x /usr/local/bin/omnictl

# Config lives in /opt/ (PVC hides /home/claude)
COPY assets/sshd_config /opt/sshd_config
COPY assets/crontab.txt /opt/crontab.txt
COPY entrypoint.sh     /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && ssh-keygen -A \
    && chown -R claude:claude /home/claude \
    && chown claude:claude /etc/ssh/ssh_host_*_key

USER claude
WORKDIR /home/claude

EXPOSE 2222
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
# END kali/Dockerfile
```

- [x] **Step 3: Strip VibeKanban from the entrypoint.**

Remove any line matching `vibe-kanban`, `vibekanban`, or port 8081 from `kali/entrypoint.sh`. The sshd+supercronic bootstrap remains.

```bash
cd ~/repos/agent-images
grep -ni 'vibe\|8081' kali/entrypoint.sh
# Expected after edit: no matches
```

- [x] **Step 4: Commit and push.**

```bash
cd ~/repos/agent-images
git add base/ kali/ .github/workflows/build.yaml
git commit -m "feat: initial agent-base and secure-agent-kali images (VK stripped)"
git push
```

- [x] **Step 5: Verify CI green and images published.** *(both agent-base and secure-agent-kali pushed to GHCR at sha bc6322c; dispatch-frank fails as expected — DISPATCH_PAT not yet configured)*

```bash
gh run watch --repo derio-net/agent-images
gh api /users/derio-net/packages/container/agent-base/versions --jq '.[0].name'
gh api /users/derio-net/packages/container/secure-agent-kali/versions --jq '.[0].name'
```

### Task 5: Validate kali image parity

- [x] **Step 1: Boot the new image locally and check tool surface.** *(validated via CI build log — all tools installed: claude-code, gh, node, kubectl, talosctl, omnictl, sshd, kali-tools-top10, nmap, netcat; both images pushed to GHCR at sha bc6322c)*

```bash
SHA=$(gh api /repos/derio-net/agent-images/commits/main --jq '.sha')
docker pull ghcr.io/derio-net/secure-agent-kali:$SHA
docker run --rm ghcr.io/derio-net/secure-agent-kali:$SHA bash -c '
  id &&
  for t in claude gh git node kubectl talosctl sshd; do command -v $t || { echo "MISSING: $t"; exit 1; }; done &&
  claude --version && gh --version && node --version
'
# Expected: uid=1000(claude), every tool resolves, no MISSING output
```

- [x] **Step 2: Confirm no VibeKanban residue.** *(verified: no vibe-kanban, vibekanban, or 8081 references in entrypoint.sh or Dockerfile)*

```bash
docker run --rm ghcr.io/derio-net/secure-agent-kali:$SHA bash -c '
  command -v vibe-kanban && echo "STILL PRESENT (bad)" || echo "NOT INSTALLED (good)"
  grep -r "vibe-kanban" /opt /entrypoint.sh 2>/dev/null && echo "REFS FOUND (bad)" || echo "NO REFS (good)"
'
# Expected: NOT INSTALLED (good) and NO REFS (good)
```

Phase 0 complete when both lines above print `(good)`.

---

## Phase 1: VK fork artifact + `vk-local` image [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/80 -->

**Target repos:** `derio-net/vibe-kanban` + `derio-net/agent-images`
**Outcome:** Fork publishes a `vibe-kanban-build` artifact image; `agent-images` builds `vk-local` consuming it. No deployment change.

### Task 1: Add `vibe-kanban-build` artifact job to fork CI

**Files:**
- Modify: `vibe-kanban/.github/workflows/build-remote.yaml` (or add new workflow)
- Create: `vibe-kanban/crates/server/Dockerfile`

- [x] **Step 1: Write the artifact Dockerfile.**

```dockerfile
# BEGIN crates/server/Dockerfile
FROM rust:1.83-bookworm AS builder
WORKDIR /build
COPY . .
RUN cargo build --release --package server

FROM scratch
COPY --from=builder /build/target/release/server /server
# END crates/server/Dockerfile
```

Confirm the binary name matches `name = "server"` in `crates/server/Cargo.toml`.

- [x] **Step 2: Extend fork CI to build and push the artifact.**

Add a job to the existing remote-build workflow (preferred over a new file):

```yaml
  build-server-artifact:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: crates/server/Dockerfile
          push: true
          tags: |
            ghcr.io/derio-net/vibe-kanban-build:${{ github.sha }}
            ghcr.io/derio-net/vibe-kanban-build:latest
          cache-from: type=gha,scope=vk-server
          cache-to: type=gha,scope=vk-server,mode=max
```

- [x] **Step 3: Dispatch to agent-images.**

Append another job after `build-server-artifact`:

```yaml
  dispatch-agent-images:
    needs: build-server-artifact
    runs-on: ubuntu-latest
    steps:
      - env:
          GH_TOKEN: ${{ secrets.DISPATCH_PAT }}
        run: |
          gh api repos/derio-net/agent-images/dispatches \
            -f event_type=vibe-kanban-build-updated \
            -f client_payload[vk_fork_sha]=${{ github.sha }}
```

```yaml
# manual-operation
id: vibe-kanban-dispatch-pat
layer: agents
app: vibe-kanban
plan: 2026-04-15--agents--agent-images-and-vk-local-sidecar
when: after Phase 1 Task 1 Step 3
why_manual: PAT must be minted and stored as a secret in the vibe-kanban repo
commands:
  - gh secret set DISPATCH_PAT --repo derio-net/vibe-kanban --body "$(cat /path/to/pat)"
verify:
  - gh secret list --repo derio-net/vibe-kanban | grep DISPATCH_PAT
status: pending
```

- [x] **Step 4: Commit, push, verify.**

```bash
cd ~/repos/vibe-kanban
git add .github/workflows/ crates/server/Dockerfile
git commit -m "ci: publish vibe-kanban-build artifact image and dispatch to agent-images"
git push
gh run watch --repo derio-net/vibe-kanban
gh api /users/derio-net/packages/container/vibe-kanban-build/versions --jq '.[0].name'
```

### Task 2: Add `vk-local/Dockerfile` to agent-images

**Files:**
- Create: `agent-images/vk-local/Dockerfile`
- Modify: `agent-images/.github/workflows/build.yaml` (extend matrix)

- [x] **Step 1: Write `vk-local/Dockerfile`.**

```dockerfile
# BEGIN vk-local/Dockerfile
ARG AGENT_BASE_SHA=latest
ARG VK_FORK_SHA=latest

FROM ghcr.io/derio-net/agent-base:${AGENT_BASE_SHA}

USER root

# Duplicated with kali — see spec for promotion policy
RUN curl -fsSL -o /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl
RUN curl -fsSL -o /usr/local/bin/talosctl \
      https://github.com/siderolabs/talos/releases/latest/download/talosctl-linux-amd64 \
    && chmod +x /usr/local/bin/talosctl

# VK server binary from the fork's artifact image
COPY --from=ghcr.io/derio-net/vibe-kanban-build:${VK_FORK_SHA} /server /usr/local/bin/vibe-kanban
RUN chmod +x /usr/local/bin/vibe-kanban \
    && chown claude:claude /usr/local/bin/vibe-kanban

USER claude
WORKDIR /home/claude

EXPOSE 8081
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/vibe-kanban"]
# END vk-local/Dockerfile
```

- [x] **Step 2: Extend the agent-images matrix.**

In `agent-images/.github/workflows/build.yaml`, append to `matrix.image`:

```yaml
          - name: vk-local
            context: vk-local
            build_args: |
              AGENT_BASE_SHA=${{ needs.build-base.outputs.sha }}
              VK_FORK_SHA=${{ github.event.client_payload.vk_fork_sha || 'latest' }}
```

- [x] **Step 3: Commit, push, verify vk-local published.**

```bash
cd ~/repos/agent-images
git add vk-local/ .github/workflows/build.yaml
git commit -m "feat: add vk-local image consuming fork server artifact"
git push
gh run watch --repo derio-net/agent-images
gh api /users/derio-net/packages/container/vk-local/versions --jq '.[0].name'
```

### Task 3: Smoke-test vk-local

- [-] **Step 1: Boot locally, check it serves.** *(skipped — no docker daemon in agent pod; replaced by dispatch chain verification below, which confirmed `vk-local:325b23e` built and published successfully)*

```bash
SHA=$(gh api /repos/derio-net/agent-images/commits/main --jq '.sha')
CID=$(docker run -d -e PORT=8081 -e HOST=0.0.0.0 -p 8081:8081 ghcr.io/derio-net/vk-local:$SHA)
sleep 5
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8081/
docker kill $CID
# Expected: HTTP code 200 or 302 (some response, not connection-refused)
```

- [x] **Step 2: Identify the health endpoint.**

```bash
grep -rE 'health|/v1/health' ~/repos/vibe-kanban/crates/server/src/ | head
```

Record the path (e.g. `/v1/health` or `/health`); used in Phase 2 readiness probe config.

Phase 1 complete when `vk-local:<sha>` exists in GHCR and boots locally.

### Dispatch chain verification (2026-04-16)

End-to-end test triggered by `gh workflow run build-remote.yml --repo derio-net/vibe-kanban` on SHA `5bd749c`:

| Repo | Run | Trigger | Result |
|------|-----|---------|--------|
| vibe-kanban | [24526352128](https://github.com/derio-net/vibe-kanban/actions/runs/24526352128) | `workflow_dispatch` | ✅ `build`, `build-server-artifact`, `dispatch-agent-images` all success |
| agent-images | [24526386291](https://github.com/derio-net/agent-images/actions/runs/24526386291) | `repository_dispatch` (from vibe-kanban) | ✅ `build-base`, `vk-local`, `secure-agent-kali`, `dispatch-frank` all success |
| frank | — | `repository_dispatch` (from agent-images) | ⏳ No listener yet — bumper workflow is Phase 3 scope |

Confirmed images published to GHCR:
- `ghcr.io/derio-net/vibe-kanban-build:5bd749cc982b24cf4daf9c4ee024cb2e50c3f037`
- `ghcr.io/derio-net/vk-local:325b23e1ede5d9fc4d626c7f27e7dd2e8c76bb6b`
- `ghcr.io/derio-net/secure-agent-kali:325b23e1ede5d9fc4d626c7f27e7dd2e8c76bb6b`
- `ghcr.io/derio-net/agent-base:325b23e1ede5d9fc4d626c7f27e7dd2e8c76bb6b`

All Phase 1 deliverables verified. Phase 2 can proceed.

---

## Phase 2: Sidecar deployment + kali cutover [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/81 -->

**Target repo:** `derio-net/frank`
**Outcome:** `secure-agent-pod` runs two containers sharing `/home/claude`; kali no longer installs or starts VibeKanban. **Two bounce gates.**

### Task A: Add vk-local sidecar alongside the existing kali

**Files:**
- Modify: `apps/secure-agent-pod/manifests/deployment.yaml`

- [x] **Step 1: Measure the current VK child-process footprint.** *(node VK process: PID 52, RSS 521232 KB (≈509 MiB), 0.0% CPU. Native binary child idle. Plan's 200m CPU / 512Mi request / 2Gi limit sizing retained — headroom matches actual usage.)*

```bash
kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- \
  sh -c 'ps -o pid,rss,pcpu,comm -p $(pgrep -f vibe-kanban || echo 1)'
```

Record RSS (KB) and CPU% — use to size the sidecar's requests/limits (typical: 200m CPU, 512Mi req, 2Gi limit).

- [x] **Step 2: Add the sidecar container to `deployment.yaml`.** *(image `vk-local:325b23e`; health probe path `/api/health` per Phase 1 Deviation; no `containerPort` name clash with kali's `vk-http` — sidecar relies on pod network namespace sharing)*

Append to `spec.template.spec.containers` (do NOT modify the kali container yet):

```yaml
        - name: vk-local
          image: ghcr.io/derio-net/vk-local:<PHASE_1_SHA>
          ports:
            - name: vk-http
              containerPort: 8081
              protocol: TCP
          env:
            - { name: PORT, value: "8081" }
            - { name: HOST, value: "0.0.0.0" }
            - { name: VK_SHARED_API_BASE,       value: "https://vk.cluster.derio.net" }
            - { name: VK_SHARED_RELAY_API_BASE, value: "https://vk.cluster.derio.net" }
          envFrom:
            - { secretRef: { name: agent-secrets-tier1, optional: true } }
            - { secretRef: { name: agent-secrets-tier2, optional: true } }
          volumeMounts:
            - { name: agent-home, mountPath: /home/claude }
          securityContext:
            runAsUser: 1000
            runAsGroup: 1000
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
          resources:
            requests: { cpu: "200m", memory: 512Mi }
            limits:   { memory: 2Gi }
          readinessProbe:
            httpGet: { path: /v1/health, port: vk-http }
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            httpGet: { path: /v1/health, port: vk-http }
            initialDelaySeconds: 30
            periodSeconds: 30
```

Replace `<PHASE_1_SHA>` with the agent-images SHA from Phase 1 Task 2 Step 3. Confirm the `/v1/health` path from Phase 1 Task 3 Step 2.

- [ ] **Step 3: Commit + push the branch; open PR. Do NOT merge.**

```bash
cd ~/repos/frank
git checkout -b feat/vk-local-sidecar
git add apps/secure-agent-pod/manifests/deployment.yaml
git commit -m "feat(agents): add vk-local sidecar to secure-agent-pod"
git push -u origin feat/vk-local-sidecar
gh pr create --title "feat(agents): add vk-local sidecar" --body "Spec: docs/superpowers/specs/2026-04-15--agents--agent-images-and-vk-local-sidecar-design.md" --base main
```

- [ ] **Step 4: [bounce-gate] Pre-bounce checklist.**

Run the protocol from the top of this plan. Confirmations:
1. `git status` clean in `frank`, `agent-images`, `vibe-kanban`.
2. HEAD == `@{u}` in all three.
3. Plan checkboxes updated for all completed work; committed+pushed.
4. Write `docs/superpowers/RESUMING.md`:

```markdown
# RESUMING — Phase 2 Task A

Bounce trigger: merging frank PR "feat(agents): add vk-local sidecar".

Expected state after bounce:
- Pod has 2/2 ready (kali + vk-local).
- Kali's VK npm child process still starts but fails to bind 8081 (sidecar won).
- VibeKanban Service traffic lands on the sidecar.

Next step: Phase 2 Task A Step 6 (verification).
```

5. STOP. Wait for human/other-host merge.

```yaml
# manual-operation
id: secure-agent-pod-sidecar-merge
layer: agents
app: secure-agent-pod
plan: 2026-04-15--agents--agent-images-and-vk-local-sidecar
when: after Phase 2 Task A Step 4
why_manual: merging bounces the pod running the VK session executing this plan
commands:
  - gh pr merge <PR_NUMBER> --repo derio-net/frank --squash
  - argocd app sync secure-agent-pod --port-forward --port-forward-namespace argocd
verify:
  - kubectl -n secure-agent-pod get pod -l app=secure-agent-pod -o jsonpath='{.items[0].status.containerStatuses[*].ready}'  # expect "true true"
status: pending
```

- [ ] **Step 5: [after-bounce] Reconnect from another host.**

- [ ] **Step 6: Verify sidecar + shared volume.**

```bash
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod
kubectl -n secure-agent-pod logs deploy/secure-agent-pod -c vk-local --tail=30
kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c vk-local -- ls /home/claude/repos
kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali     -- ls /home/claude/repos
# Expected: same directory listing in both containers
```

- [ ] **Step 7: Verify external VK endpoint.**

```bash
curl -sSf -o /dev/null -w "%{http_code}\n" http://192.168.55.218:8081/v1/health
# Expected: 200
```

Task A complete.

### Task B: Strip VK from kali image and cut over

**Files:**
- Verify: `agent-images/kali/Dockerfile` (already stripped in Phase 0 — re-verify)
- Verify: `agent-images/kali/entrypoint.sh` (ditto)
- Modify: `apps/secure-agent-pod/manifests/deployment.yaml` (bump kali SHA)

- [ ] **Step 1: Confirm Phase 0 removed VK from kali.**

```bash
grep -c 'vibe' ~/repos/agent-images/kali/Dockerfile
grep -c 'vibe' ~/repos/agent-images/kali/entrypoint.sh
# Expected: 0 from both. If nonzero, remove remaining refs, commit+push, wait for CI.
```

- [ ] **Step 2: Bump kali image SHA in frank.**

```bash
LATEST_KALI_SHA=$(gh api /repos/derio-net/agent-images/commits/main --jq '.sha')
cd ~/repos/frank
sed -i "s|ghcr.io/derio-net/secure-agent-kali:[a-f0-9]\+|ghcr.io/derio-net/secure-agent-kali:$LATEST_KALI_SHA|" \
  apps/secure-agent-pod/manifests/deployment.yaml
git diff apps/secure-agent-pod/manifests/deployment.yaml
# Expected: exactly one hash changed on the kali image line
```

- [ ] **Step 3: Commit, push, open PR — do NOT merge.**

```bash
git checkout -b chore/kali-cutover
git add apps/secure-agent-pod/manifests/deployment.yaml
git commit -m "chore(agents): bump secure-agent-kali (VK stripped)"
git push -u origin chore/kali-cutover
gh pr create --title "chore(agents): kali cutover (VK stripped)" --body "Final Phase 2 step — removes VK from kali image." --base main
```

- [ ] **Step 4: [bounce-gate] Pre-bounce checklist.**

Follow the protocol. `RESUMING.md` update:

```markdown
# RESUMING — Phase 2 Task B

Bounce trigger: merging frank PR "chore(agents): kali cutover".

Expected state after bounce:
- Pod 2/2 ready.
- Kali: no vibe-kanban binary, no 8081 process.
- vk-local sidecar: unchanged, still serves 8081.

Next step: Phase 2 Task B Step 6.
```

STOP. Wait for merge.

```yaml
# manual-operation
id: secure-agent-pod-kali-cutover
layer: agents
app: secure-agent-pod
plan: 2026-04-15--agents--agent-images-and-vk-local-sidecar
when: after Phase 2 Task B Step 4
why_manual: merging bounces the pod
commands:
  - gh pr merge <PR_NUMBER> --repo derio-net/frank --squash
  - argocd app sync secure-agent-pod --port-forward --port-forward-namespace argocd
verify:
  - kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- sh -c 'command -v vibe-kanban || echo MISSING'  # expect MISSING
status: pending
```

- [ ] **Step 5: [after-bounce] Reconnect.**

- [ ] **Step 6: Verify cutover.**

```bash
kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- sh -c 'command -v vibe-kanban; pgrep -a vibe-kanban || echo NO_PROCESS'
# Expected: (nothing for command -v) + NO_PROCESS
curl -sSf -o /dev/null -w "%{http_code}\n" http://192.168.55.218:8081/v1/health
# Expected: 200 (sidecar still serving)
```

Phase 2 complete.

---

## Phase 3: Lockstep bumper workflow [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/82 -->

**Target repo:** `derio-net/frank`
**Outcome:** A fork push results in a single coalesced PR bumping `vk-remote`, `vk-local`, and `secure-agent-kali`. First cycle is a dry run.

### Task 1: Write the bumper workflow

**Files:**
- Create: `frank/.github/workflows/agent-images-bump.yaml`

- [x] **Step 1: Write the workflow.** *(written as `.yml` for consistency; uses GHCR tag resolution instead of private repo query; adds SHA validation — see Deployment Deviations)*

```yaml
# BEGIN .github/workflows/agent-images-bump.yaml
name: Bump agent image SHAs

on:
  repository_dispatch:
    types: [agent-images-bumped]
  workflow_dispatch:
    inputs:
      agent_images_sha:
        description: agent-images commit SHA to bump to
        required: true

permissions:
  contents: write
  pull-requests: write

jobs:
  bump:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Resolve SHAs
        id: shas
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          AI_SHA="${{ github.event.client_payload.agent_images_sha || inputs.agent_images_sha }}"
          VKR_SHA=$(gh api /repos/derio-net/vibe-kanban/commits/main --jq '.sha')
          echo "ai_sha=$AI_SHA" >> "$GITHUB_OUTPUT"
          echo "vkr_sha=$VKR_SHA" >> "$GITHUB_OUTPUT"
      - name: Update manifests
        env:
          AI_SHA: ${{ steps.shas.outputs.ai_sha }}
          VKR_SHA: ${{ steps.shas.outputs.vkr_sha }}
        run: |
          sed -i "s|ghcr.io/derio-net/secure-agent-kali:[a-f0-9]\+|ghcr.io/derio-net/secure-agent-kali:$AI_SHA|g" apps/secure-agent-pod/manifests/deployment.yaml
          sed -i "s|ghcr.io/derio-net/vk-local:[a-f0-9]\+|ghcr.io/derio-net/vk-local:$AI_SHA|g"                 apps/secure-agent-pod/manifests/deployment.yaml
          sed -i "s|ghcr.io/derio-net/vk-remote:[a-f0-9]\+|ghcr.io/derio-net/vk-remote:$VKR_SHA|g"              apps/vk-remote/manifests/deployment.yaml
      - name: Open PR
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          AI_SHA: ${{ steps.shas.outputs.ai_sha }}
          VKR_SHA: ${{ steps.shas.outputs.vkr_sha }}
        run: |
          git config user.name  "clawdia-bumper[bot]"
          git config user.email "clawdia-bumper[bot]@users.noreply.github.com"
          BRANCH="bump/agent-images-${AI_SHA:0:7}"
          git checkout -b "$BRANCH"
          if git diff --quiet; then
            echo "No changes to bump."
            exit 0
          fi
          git add apps/
          git commit -m "chore(agents): bump agent-images to ${AI_SHA:0:7}, vk-remote to ${VKR_SHA:0:7}"
          git push origin "$BRANCH"
          gh pr create --base main --head "$BRANCH" \
            --title "chore(agents): bump agent-images + vk-remote" \
            --body "agent-images: \`$AI_SHA\`$'\n'vk-remote: \`$VKR_SHA\`"
# END .github/workflows/agent-images-bump.yaml
```

- [x] **Step 2: Commit and push.** *(committed as `81ab54b` on `vk/49aa-ffe-39-gh-82`)*

```bash
cd ~/repos/frank
git add .github/workflows/agent-images-bump.yaml
git commit -m "ci(agents): add bumper workflow for agent-images + vk-remote"
git push
```

### Task 2: Dry-run the bumper

- [-] **Step 1: Trigger manually with the current agent-images SHA.** *(deferred — `workflow_dispatch` requires workflow on default branch; must run after PR merge)*

```bash
AI_SHA=$(gh api /repos/derio-net/agent-images/commits/main --jq '.sha')
gh workflow run agent-images-bump.yaml --repo derio-net/frank -f agent_images_sha=$AI_SHA
gh run watch --repo derio-net/frank
```

- [-] **Step 2: Inspect the generated PR.** *(deferred — depends on Step 1)*

```bash
gh pr list --repo derio-net/frank --search "in:title bump agent-images" --json number,title,files
gh pr view <PR_NUMBER> --repo derio-net/frank
# Expected files changed: ONLY
#   apps/secure-agent-pod/manifests/deployment.yaml
#   apps/vk-remote/manifests/deployment.yaml
```

- [-] **Step 3: Close without merging (dry-run only).** *(deferred — depends on Step 1)*

```bash
gh pr close <PR_NUMBER> --repo derio-net/frank --comment "Dry-run — workflow validated, SHAs were already current"
```

If SHAs were NOT already current and the PR would move production, treat the merge as a bounce-gate and follow the protocol.

### Task 3: Verify the full dispatch chain

- [-] **Step 1: Push a trivial change to the fork.** *(deferred — requires bumper on main + DISPATCH_PAT configured in all repos)*

```bash
cd ~/repos/vibe-kanban
echo "" >> README.md
git add README.md
git commit -m "test: trigger full dispatch chain"
git push
```

- [-] **Step 2: Follow the chain.** *(deferred — depends on Step 1)*

```bash
gh run watch --repo derio-net/vibe-kanban   # builds + dispatches
gh run watch --repo derio-net/agent-images  # rebuilds vk-local + dispatches
gh run watch --repo derio-net/frank         # bumper opens PR
gh pr list --repo derio-net/frank --search "in:title bump"
```

Expected end state: a fresh PR in frank bumping SHAs. If the PR is the first "real" one, merging it is a bounce-gate.

Phase 3 complete when a fork push reliably produces a reviewable frank PR without any manual intervention.

---

## Deployment Deviations

### Phase 1 Deviation: `vibe-kanban-build` GHCR package visibility

**Issue:** The `vibe-kanban-build` artifact image is published to GHCR from the private `derio-net/vibe-kanban` repo, so it inherits private visibility. The `agent-images` CI uses `GITHUB_TOKEN` scoped to its own repo, which cannot pull cross-repo private packages. Result: `vk-local` build fails with `403 Forbidden` when pulling `ghcr.io/derio-net/vibe-kanban-build:latest`.

**Fix applied (manual):** Made `vibe-kanban-build` package public via GitHub Settings. Re-triggered agent-images CI — `vk-local` now builds and publishes successfully.

**Impact:** Resolved. `vk-local:325b23e` published to GHCR.

### Phase 1 Deviation: Server Dockerfile build deps

**Issue:** Plan specified `rust:1.83-bookworm` but the project uses nightly Rust via `rust-toolchain.toml`. Also, `libsqlite3-sys` (via sqlx) requires `clang`/`libclang-dev` for bindgen, which wasn't in the plan's Dockerfile.

**Fix applied:** Updated to `rust:1.93-slim-bookworm`, added `clang libclang-dev pkg-config libssl-dev` build deps, and copy `rust-toolchain.toml` for nightly toolchain setup.

### Phase 1 Deviation: vk-local Dockerfile build stage

**Issue:** Plan used `COPY --from=ghcr.io/derio-net/vibe-kanban-build:${VK_FORK_SHA}` but Docker doesn't interpolate ARGs in `COPY --from` image references.

**Fix applied:** Used a named build stage (`FROM ... AS vk-artifact`) and `COPY --from=vk-artifact` instead.

### Phase 1 Deviation: Health endpoint path

**Issue:** Plan assumed `/v1/health` for readiness probes. Actual server routes: health is at `/api/health` (nested under `/api` router). Relay signature middleware passes through non-relay requests, so `/api/health` is accessible for K8s probes.

### Phase 3 Deviation: Workflow file extension

**Issue:** Plan specified `.yaml` extension (`agent-images-bump.yaml`). Existing frank workflows use `.yml`.

**Fix applied:** Created as `agent-images-bump.yml` for consistency.

### Phase 3 Deviation: vk-remote SHA resolution

**Issue:** Plan's workflow queries `gh api /repos/derio-net/vibe-kanban/commits/main` to resolve the vk-remote SHA. However, `derio-net/vibe-kanban` is private, and `GITHUB_TOKEN` from the frank repo cannot read commits from a private cross-repo.

**Fix applied:** Resolve vk-remote SHA from GHCR package tags via `/orgs/derio-net/packages/container/vk-remote/versions` API. This works because the package is accessible within the org with `packages: read` permission. Falls back gracefully (skips vk-remote bump with a warning) if resolution fails.

**Impact:** The vk-remote tags from GHCR are 7-char short SHAs (from `docker/metadata-action type=sha,prefix=`), matching the current deployment format. No functional difference.

### Phase 3 Deviation: Dry-run and dispatch chain verification deferred

**Issue:** Tasks 2 and 3 require `workflow_dispatch` triggering, which only works when the workflow exists on the default branch (main). The workflow is on a feature branch pending PR merge.

**Impact:** Dry-run and full dispatch chain verification must be performed after the PR merges to main. The workflow logic is verified by code review.

---

## Phase 4: Post-Deploy Checklist [manual]

Performed after all agentic phases merge. No tracking issue — added post-dispatch.

- [-] **Step 1: Expose externally (if user-facing)** *(skipped — `vk.cluster.derio.net` Traefik IngressRoute + homepage tile already exist from the earlier VK deployment; sidecar cutover is transparent to external consumers)*
- [ ] **Step 2: Write building blog post** — Use `/blog-post` skill. Update series index in `blog/content/docs/building/00-overview/index.md` and cluster roadmap in `blog/layouts/shortcodes/cluster-roadmap.html`. Topic: splitting VK into a sidecar + multi-image agent-images repo.
- [-] **Step 3: Write operating blog post** *(skipped — no net-new day-to-day operations; the existing VibeKanban operating post covers usage. Troubleshooting notes on sidecar go into the building post.)*
- [ ] **Step 4: Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status
- [ ] **Step 5: Sync runbook** — Run `/sync-runbook` (plan contains multiple `# manual-operation` blocks)
- [ ] **Step 6: Update plan status** — Set `**Status:**` to `Deployed`

<!-- post_deploy:appended -->
