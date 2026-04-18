---
title: "Agent Images and the VK-Local Sidecar — Unbaking VibeKanban"
date: 2026-04-18
draft: false
tags: ["agents", "docker", "sidecar", "github-actions", "multi-stage", "cross-repo-dispatch", "rust-embed"]
summary: "Splitting VibeKanban out of the Kali agent pod into a shared-volume sidecar, and moving Dockerfiles into a new multi-image repo with matrix CI and cross-repo dispatch — three rebuilds, two gotchas, one clean boundary."
weight: 29
---

The `secure-agent-pod` started its life as a single container: Kali Linux, a non-root `claude` user, sshd, kubectl, and a globally `npm install`-ed VibeKanban baked straight into the image (layer 21, [Secure Agent Pod]({{< relref "building/21-secure-agent-pod" >}})). That worked. It also meant every VibeKanban bugfix required rebuilding a 1.8 GB Kali image, every Kali tool upgrade risked breaking the node binary, and the image itself was welded to a single consumer.

This post unbakes all of it.

The work splits into three moves:

1. A new repo, `derio-net/agent-images`, that publishes a shared `agent-base` and per-pod children (`secure-agent-kali`, `vk-local`) via matrix CI.
2. A sidecar in the pod: kali keeps everything it had *except* VibeKanban, and a second container runs a compiled-from-source VK server binary. They share `/home/claude` as a PVC.
3. A lockstep bumper in `frank`: whenever any upstream image advances, a single PR opens updating all three references together.

Along the way, two gotchas that cost me an hour each: a port-8081 bind race where the old in-process VK won, and a Rust build script that *silently* embeds a placeholder HTML page when the frontend isn't built.

## Why split?

The fused pod violated a separation that I'd already established elsewhere on the cluster: **where code runs is separate from how code is built.** The pod is the runtime; the image is a build artifact; the Dockerfile belongs to whoever maintains the image. Packing Kali tools and a VibeKanban server into one Dockerfile made image updates atomic, but it also made them *coupled* — you couldn't ship a VK patch without a Kali rebuild.

The second reason is re-use. The next `secure-agent-<flavour>` pod I wanted to build — a hardened Python data-science sandbox — would share 80% of its base with Kali. Claude Code, gh CLI, node, bun, uv, supercronic, the non-root user, the entrypoint scaffolding. Copy-pasting that into every pod's Dockerfile is a promise to forget to update one of them.

A base image is the obvious fix. But a base image needs a home. `frank` already has too many responsibilities, and the GPU pod and agent pods aren't really "cluster apps" in the sense that ArgoCD should manage their *source*. So a new repo gets to own it.

## Architecture

```
derio-net/vibe-kanban          derio-net/agent-images              derio-net/frank

fork CI:                       matrix CI:                          bumper CI:
  build vk-remote       ┐       build agent-base                    on dispatch:
  build vk-build────────┼─COPY─► build secure-agent-kali             collect SHAs
                        │       build vk-local                       open 1 PR bumping
repository_dispatch─────┘       repository_dispatch───────────────►  vk-remote + vk-local
                                                                      + secure-agent-kali
                                                                     (ArgoCD syncs → bounce)
```

Three repos, three CI loops, two `repository_dispatch` hops. Any push to the fork eventually produces a reviewable PR in `frank` — no manual coordination, no Slack ping, no "remember to bump the tag".

## The new repo: `agent-images`

The repo is tiny:

```
agent-images/
├── .github/workflows/build.yaml
├── base/Dockerfile
├── kali/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── assets/{sshd_config,crontab.txt}
└── vk-local/Dockerfile
```

`base/Dockerfile` is a `FROM debian:bookworm-slim` with every tool that *every* agent pod needs — Claude Code CLI, gh, node 22, bun, python3, uv, git, tini, supercronic, a non-root `claude` user (UID 1000 to match the PVC). About 40 lines.

Each child starts with `FROM ghcr.io/derio-net/agent-base:${AGENT_BASE_SHA}` and layers on what's specific. `kali/` adds the Kali archive, `kali-tools-top10`, nmap, netcat, kubectl/talosctl/omnictl, and sshd. `vk-local/` adds nothing — it just `COPY --from=vk-artifact /server /usr/local/bin/vibe-kanban` from an upstream artifact image (more on that below) and sets `EXPOSE 8081`.

CI uses a matrix:

```yaml
jobs:
  build-base:
    runs-on: ubuntu-latest
    outputs:
      sha: ${{ github.sha }}
    # ... build and push agent-base with cache-from/cache-to GHA cache

  build-children:
    needs: build-base
    strategy:
      matrix:
        image:
          - { name: secure-agent-kali, context: kali,     build_args: "AGENT_BASE_SHA=${{ needs.build-base.outputs.sha }}" }
          - { name: vk-local,          context: vk-local, build_args: "AGENT_BASE_SHA=${{ needs.build-base.outputs.sha }}\nVK_FORK_SHA=${{ github.event.client_payload.vk_fork_sha || 'latest' }}" }
    runs-on: ubuntu-latest
    # ... same build-push pattern, one per matrix entry
```

The `needs: build-base` dependency means children always inherit the just-built base SHA from the same commit. This guarantees a `secure-agent-kali:<sha>` and `vk-local:<sha>` were built against `agent-base:<sha>` with matching digests — no "last-night base image had different glibc" surprises.

Dispatch chains are simple:

```yaml
  dispatch-frank:
    needs: build-children
    runs-on: ubuntu-latest
    steps:
      - run: gh api repos/derio-net/frank/dispatches -f event_type=agent-images-bumped -f client_payload[agent_images_sha]=${{ github.sha }}
        env: { GH_TOKEN: ${{ secrets.DISPATCH_PAT }} }
```

## The fork artifact

VibeKanban is an npm-published binary, but `secure-agent-kali` previously installed it via `npm install -g @vibe-kanban/cli`. That worked but meant every upgrade had to re-download and re-pack node_modules into the image, and the whole thing had to be re-installed at pod bootstrap because the PVC mount at `/home/claude` hid the image-baked files.

The sidecar version runs the Rust server binary directly. To get that binary, `derio-net/vibe-kanban` (my fork) now publishes an artifact-only image whenever its main branch moves:

```dockerfile
# BEGIN crates/server/Dockerfile (vibe-kanban fork)
FROM node:24-alpine AS fe-builder
WORKDIR /app
RUN corepack enable
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY packages/{local-web,ui,web-core}/package.json packages/{local-web,ui,web-core}/
COPY patches/ patches/
RUN pnpm install --frozen-lockfile
COPY packages/ packages/
COPY shared/ shared/
RUN pnpm -C packages/local-web build

FROM rust:1.93-slim-bookworm AS builder
WORKDIR /build
RUN apt-get install -y pkg-config libssl-dev clang libclang-dev
COPY . .
COPY --from=fe-builder /app/packages/local-web/dist packages/local-web/dist
RUN cargo build --release --package server

FROM scratch
COPY --from=builder /build/target/release/server /server
```

That `COPY --from=fe-builder ...` line is not cosmetic. I'll come back to that in the gotchas.

The published image is `ghcr.io/derio-net/vibe-kanban-build:<fork-sha>` — a `FROM scratch` image containing nothing but `/server`. The `vk-local` Dockerfile in `agent-images` pulls that file out:

```dockerfile
ARG VK_FORK_SHA=latest
FROM ghcr.io/derio-net/vibe-kanban-build:${VK_FORK_SHA} AS vk-artifact
FROM ghcr.io/derio-net/agent-base:${AGENT_BASE_SHA}
COPY --from=vk-artifact /server /usr/local/bin/vibe-kanban
```

(`ARG` in `COPY --from=image:${ARG}` doesn't interpolate, so you need the named build stage trick.)

## The sidecar in `frank`

The old deployment had one container. The new one has two:

```yaml
spec:
  template:
    spec:
      containers:
        - name: kali
          image: ghcr.io/derio-net/secure-agent-kali:<sha>
          env:
            - { name: PORT, value: "18081" }       # dead config post-cutover
            - { name: HOST, value: "127.0.0.1" }   # see gotcha below
          volumeMounts:
            - { name: agent-home, mountPath: /home/claude }
        - name: vk-local
          image: ghcr.io/derio-net/vk-local:<sha>
          ports:
            - { name: vk-http, containerPort: 8081 }
          env:
            - { name: PORT, value: "8081" }
            - { name: HOST, value: "0.0.0.0" }
          volumeMounts:
            - { name: agent-home, mountPath: /home/claude }
          readinessProbe: { httpGet: { path: /api/health, port: vk-http } }
```

Both containers mount the same `agent-home` PVC at `/home/claude`. That's the whole contract between them: kali does ad-hoc work (SSH sessions, Claude Code runs, git clones), and every file lands in a place `vk-local` can also see. There's no IPC, no shared memory, no RPC — the filesystem is the interface.

The Service routes 8081 to the `vk-http` port, which is now on the sidecar. External consumers (`vk.cluster.derio.net`, `http://192.168.55.218:8081`) can't tell the difference.

## The lockstep bumper

When `agent-images` or `vibe-kanban` publishes a new image, `frank` needs to know. The bumper is one workflow that listens for `repository_dispatch` and opens a PR:

```yaml
on:
  repository_dispatch:
    types: [agent-images-bumped]
  workflow_dispatch:
    inputs: { agent_images_sha: { required: true } }

jobs:
  bump:
    runs-on: ubuntu-latest
    permissions: { contents: write, pull-requests: write }
    steps:
      - uses: actions/checkout@v4
      - name: Resolve SHAs
        run: |
          AI_SHA="${{ github.event.client_payload.agent_images_sha || inputs.agent_images_sha }}"
          VKR_SHA=$(gh api /orgs/derio-net/packages/container/vk-remote/versions --jq '.[0].metadata.container.tags[] | select(test("^[a-f0-9]{7}$"))' | head -1)
          # ...
      - name: Update manifests
        run: |
          sed -i "s|secure-agent-kali:[a-f0-9]\+|secure-agent-kali:$AI_SHA|" apps/secure-agent-pod/manifests/deployment.yaml
          sed -i "s|vk-local:[a-f0-9]\+|vk-local:$AI_SHA|" apps/secure-agent-pod/manifests/deployment.yaml
          sed -i "s|vk-remote:[a-f0-9]\+|vk-remote:$VKR_SHA|" apps/vk-remote/manifests/deployment.yaml
      - name: Open PR
        run: |
          git config user.name "clawdia-bumper[bot]"
          git checkout -b "bump/agent-images-${AI_SHA:0:7}"
          if git diff --quiet; then echo "No diff" && exit 0; fi
          git commit -am "chore(agents): bump agent-images to ${AI_SHA:0:7}, vk-remote to ${VKR_SHA}"
          git push origin HEAD
          gh pr create --base main --title "chore(agents): bump agent-images + vk-remote" --body "..."
```

One push to the fork, one PR in `frank`. The human reviews a 6-line diff, clicks merge, and ArgoCD picks up the rest. No tag hunting, no manual sed, no accidentally bumping vk-local without bumping vk-remote and ending up with a version mismatch.

## Gotcha 1: the port-8081 bind race

The plan said: *"the lighter sidecar will win the 8081 bind race because the kali npm VK boots slower."* That plan assumed the universe is fair. It is not.

On every pod restart, kali's supercronic bootstrap ran `/home/claude/.local/bin/vibe-kanban start` before the sidecar's Rust binary had finished its cold start. Kali grabbed port 8081. The sidecar came up, tried to bind, failed with `EADDRINUSE`, and went into CrashLoopBackOff. 246 restarts in 20 hours.

The fix was mechanical — make the loser losable:

```yaml
- name: kali
  env:
    - { name: PORT, value: "18081" }
    - { name: HOST, value: "127.0.0.1" }
```

Kali's in-process VK now binds `127.0.0.1:18081`, which no one routes to. The sidecar owns `0.0.0.0:8081` unopposed. Once the Task B rebuild strips VK from the kali image entirely, those env vars become dead config — I left them in place because the Task B diff had to be a single line, and the cleanup can come later.

The lesson: **"shouldn't happen" is not a design.** Two processes racing for the same port is a bug even when you know which one will win. Make outcomes deterministic by *structure*, not by timing.

## Gotcha 2: "Please build @vibe/local-web first"

After the sidecar cutover, `vk-local` responded on port 8081. `/api/health` returned 200. Everything looked good — until I opened the UI in a browser and saw:

```
<!DOCTYPE html>
<html><head><title>Build web app first</title></head>
<body><h1>Please build @vibe/local-web first</h1></body></html>
```

Five words, six hours of wondering if the React SPA was failing to hydrate. It wasn't. The server was *intentionally* serving that HTML.

`crates/server/src/routes/frontend.rs` uses `rust-embed`:

```rust
#[derive(RustEmbed)]
#[folder = "../../packages/local-web/dist"]
struct FrontendAssets;
```

At compile time, every file in that directory gets compiled into the binary as a `&[u8]` constant. If the directory doesn't exist? Well, `rust-embed` errors out — *unless* something else creates it first. And something else does:

```rust
// crates/server/build.rs
let dist_path = Path::new("../../packages/local-web/dist");
if !dist_path.exists() {
    fs::create_dir_all(dist_path).unwrap();
    fs::write(dist_path.join("index.html"),
              r#"<!DOCTYPE html>...<h1>Please build @vibe/local-web first</h1>..."#).unwrap();
}
```

The build script creates a dummy `index.html` with the placeholder. `rust-embed` happily embeds *that*. `cargo build` succeeds. The binary ships. The UI says what it says.

This is a friendly-looking footgun in a full-stack monorepo: a Rust build system that silently covers for a missing frontend build. The fix, as shown in the Dockerfile above, is to not miss the frontend build — the `fe-builder` stage runs `pnpm -C packages/local-web build` *before* the Rust stage, and the resulting `dist/` gets `COPY`-ed into position before `cargo build` runs.

The lesson: **if your build accepts a missing input with a warning, that warning needs to fail CI.** A build that completes in a state the runtime can't recover from is worse than a build that fails outright.

## Verification

After all three PRs merged and ArgoCD synced:

```bash
$ kubectl -n secure-agent-pod get pod -l app=secure-agent-pod -o jsonpath='{range .items[0].spec.containers[*]}{.name}={.image}{"\n"}{end}'
kali=ghcr.io/derio-net/secure-agent-kali:95e364f81c392ae9ba2a5508d36897c399b2f037
vk-local=ghcr.io/derio-net/vk-local:95e364f81c392ae9ba2a5508d36897c399b2f037

$ kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- command -v vibe-kanban || echo "VK GONE"
VK GONE

$ kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c vk-local -- ls /home/claude/repos
agent-images  frank  secure-agent-kali  superpowers-for-vk  vibe-kanban

$ kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- ls /home/claude/repos
agent-images  frank  secure-agent-kali  superpowers-for-vk  vibe-kanban

$ curl -sS http://192.168.55.218:8081/ | head -3
<!DOCTYPE html>
<html lang="en">
  <head>
```

Both containers see the same repos directory. The kali container no longer has the VK binary. The sidecar serves the real React app. The shared volume is the interface; the pod is the runtime; the Dockerfiles live in a repo that has one job.

## What's next

The `agent-images` repo makes it trivial to add a third pod. The next one I'm planning is a Python data-science sandbox with pandas, DuckDB, polars, and a Jupyter Lab sidecar — same pattern, different tool surface. That repo already has the CI scaffolding, matrix build, dispatch chain, and version-pin discipline. Adding a new image is: write a Dockerfile, add a matrix entry, push. The bumper catches up on its own.

The frontend-embed gotcha also generalised into a `.claude/rules/frank-gotchas.md` entry. Next time a Rust monorepo has a build script that *creates* missing inputs, I'll know to look for the placeholder before I debug the SPA.

## References

- `agent-images` repo — [github.com/derio-net/agent-images](https://github.com/derio-net/agent-images)
- VibeKanban fork (Dockerfile fix in PR #6) — [github.com/derio-net/vibe-kanban](https://github.com/derio-net/vibe-kanban)
- Plan and deviation log — `docs/superpowers/plans/2026-04-15--agents--agent-images-and-vk-local-sidecar.md`
- Prior art, same layer — [Secure Agent Pod]({{< relref "building/21-secure-agent-pod" >}}), [VK Remote Self-Host]({{< relref "building/26-vk-remote-self-host" >}})
- `rust-embed` — [github.com/pyrossh/rust-embed](https://github.com/pyrossh/rust-embed)
