# K8s-Native Agentic Runs — Design

**Status:** Draft
**Layer:** agents (12 — Agentic Control Plane)
**Date:** 2026-06-07
**Repos touched:** `frank` (this spec, cluster wiring), `super-fr` (runner adapter), `agent-images` (provisioning layer), `runs-fr` (new — web shell gateway)

## Implementation Plans

| Plan | Repo | Status |
|------|------|--------|
| [2026-06-08-runs-fr-gateway-skeleton](https://github.com/derio-net/runs-fr/tree/main/docs/superpowers/plans/2026-06-08-runs-fr-gateway-skeleton) (Component C) | `derio-net/runs-fr` | Planned |

## Context

`super-fr`'s `fr-isolation` runs feature work in a **git worktree + devcontainer**, driven
by `devcontainer up`/`exec`. That requires a Docker daemon/socket — which is **not available
inside the cluster's agent pods** (secure-agent-pod, hermes-agent-shell, etc.): they run on
Talos/Kubernetes with `runAsNonRoot`, `allowPrivilegeEscalation: false`, `capabilities: drop
[ALL]`, and no docker/podman/dind. So the isolation mechanism the fr-* skills assume cannot
run where the agents actually live.

VibeKanban sidesteps this today by using **git worktrees inside one long-lived pod** (no
devcontainer). It works, but cramming many runs into one container is the root of three
documented Frank gotchas: the VK **OOM cascade** (`limits.memory` too tight; queued sessions
retain memory), **worktree heap residue** (~17 MiB per orphaned worktree, daily prune cron),
and the **30s-MCP-timeout zombie executions** (DB rows stuck `running` forever).

This design makes agentic runs **Kubernetes-native**: the unit of isolation becomes a **pod**
(a clean-room clone, nothing shared), not a docker container or a worktree. The base repo is
never present in the run pod, so the entire "never touch the base repo" guard apparatus
becomes structurally unnecessary. It preserves the property the operator values most about
VK — **there is always a live, attachable session if needed** — and it yields a reusable,
portable product (`runs-fr`) as a side effect.

This spec covers a **walking skeleton**: the thinnest end-to-end slice that exercises every
architectural seam exactly once. Breadth (autonomous dispatch daemon, fr-goal mode, the other
harnesses, full capability composition) is deferred to named follow-up specs.

## Goals

- Run an agentic phase in an isolated **pod-per-run** with a **per-run PVC**, with no Docker
  socket and no privileged container.
- Provision the run pod at boot via a **composable, deterministic, CI-validated** mechanism
  (no agentic loops in the tests) — formalizing today's ad-hoc `cont-init.d` patterns.
- Keep an **always-attachable** session: browse live runs and drop into a pod's terminal from
  a web UI, resume-after-drop, behind SSO.
- Ensure run **logs survive the ephemeral pod** — shipped off-pod (fluent-bit → VictoriaLogs),
  tagged by run, so a reaped pod is still auditable.
- Ship the web gateway as a **standalone, cluster-agnostic product** (`runs-fr`).

## Non-goals (deferred to follow-up specs)

- The autonomous **bridge daemon** (`fr apply --to k8s` auto-pickup) — runs are hand-spawned
  in the skeleton.
- **fr-goal** mode and its in-session Q&A flow.
- Harnesses beyond **claude** (codex, pi, hermes+local model).
- Full **skills/plugins/MCP** composition matrix (skeleton wires a minimal set).
- The gateway's future **dashboard/GUI** (dispatch, status, metrics surfaces).
- A custom **operator/CRD** (`FrRun`). Plain Kubernetes objects first; an operator is a
  possible later evolution, not the starting point.

## Architecture

Three components joined by one declarative contract.

### The RunSpec (the seam)

A single declarative object describing one run. The runner produces it, the provisioning
layer consumes it, the gateway reads it (as pod labels) to list and route. Designing it well
is most of the architecture. Minimal fields for the skeleton:

```
runId            # stable id; becomes the tmux session name + label values
harness          # "claude" (skeleton); later codex|pi|hermes|...
harnessVersion   # EXACT pin — drives the L2 boot-time update. "latest" is dev-only and must
                 # resolve-and-RECORD the concrete version at boot (a floating pin breaks the
                 # reproducibility posture below)
repo             # git URL to clone clean-room
branch           # feature branch to check out / create
issue            # GitHub Issue / phase the run executes
profile          # fr profile name (e.g. frank "dev")
credsRef         # ESO/Secret reference for the harness credentials
capabilitiesRef  # resolves to a layered capability bundle (see below); run overlay optional
resources        # requests/limits for the pod (bounds the run)
```

Surfaced on the pod as labels (`fr.run/id`, `fr.run/plan`, `fr.run/phase`, `fr.run/harness`,
`fr.run/repo`, `fr.run/branch`) so the gateway and reaper select by label.

### Capability composition (the `capabilitiesRef` layers)

A run pod is a **clean room** — there is no operator `~/.claude`. Today a large part of
effective capability is *ambient* there and undeclared: user-level **plugins** (`super-fr`,
`superpowers`, `super-fr-dispatch`), user-level **skills** (the `~/.agents` /
`derio-net/agent-skills` symlink convention + lockfile-pinned third-party), **MCP servers,
settings, hooks, global CLAUDE.md**. Only the **repo-level** contract (`frank/agents/*`,
`AGENTS.md`) travels with the clone. The abstraction's job is to convert the ambient,
machine-resident part into something **declared, pinned, and reproducible**.

A **capability bundle** is a declarative, lockfile-pinned manifest of
`{plugins[], skills[], mcp[], settings/hooks}` — the `~/.agents` lockfile convention lifted
out of "ambient on a laptop" into a named, versioned artifact. Resolved in **three layers**
at L2 provisioning:

```
global base bundle   # shared, versioned registry: claude + super-fr + superpowers
                     # + super-fr-dispatch + core skills/MCP
   ⊕ repo overlay    # frank/agents/* + repo-specific skills/MCP — travels with the clone
   ⊕ run overlay     # RunSpec capabilitiesRef: add / pin / disable for this one run
   = resolved, pinned capability set → L2 installs it → Tier-1 probe asserts presence
```

- **Discoverable** — a registry the *author* browses (`fr capabilities list` / `resolve`) and
  the *agent* introspects in-pod (the Tier 2 "report your tools" prompt is the receipt for
  what the bundle declared).
- **Clean boundary** — run pods get **only the resolved bundle, never a mirror of the
  operator's personal `~/.claude`** (browser-harness, brave-clawdia, RTK, personal hooks stay
  out). Reproducibility *and* the masking/privacy posture the repo rules already require for
  shared/portable artifacts.
- The bundle is the explicit form of a today-hidden input: it turns "works on my laptop" into
  a reviewable, pinned manifest. The split falls exactly on "does it travel with the clone?" —
  repo-level is already solved; the bundle exists to capture the user-level part that isn't.

### Component A — Run-pod provisioning (`agent-images`)

Layered by **update cadence**, so fast-moving harnesses don't force fully-baked-image churn
and slow substrate isn't reinstalled at runtime:

- **L0 — shell substrate (baked, slow):** `agent-shell-base` as-is — OS, s6-overlay, sshd,
  tmux (resurrect/continuum), mosh, common toolchain (node, bun, uv, gh, git). Rebuilt rarely.
- **L1 — harness baseline (baked, medium):** a `multi-agent-shell`-style image with all
  harnesses preinstalled at a known-good baseline. Ages *gracefully* — it's only a floor.
- **L2 — boot provisioning (NOT baked; runs at pod start, RunSpec-driven):** a composable set
  of deterministic units that:
  - **update the selected harness** to `harnessVersion`, using the **memory-safe install
    recipe** the gotchas mandate (curl the binary to `~/.local/share/<h>/versions/<ver>` +
    symlink — never `claude install`, which buffers ~245 MB ~17× and group-OOMs the pod).
  - **inject credentials** for that harness via ESO-managed Secret → the BYOK `profile.d`
    re-export shim pattern (`/proc/1/environ` → login shells).
  - **assemble capabilities** — skills/plugins/MCP via the `~/.agents` symlink + lockfile
    convention.

**TDD-as-infrastructure contract:** each provisioning unit is idempotent, returns
success/failure, and **carries a verification probe** asserting *presence / shape / version*
(e.g. `claude --version == pinned`, MCP list contains X, credential present and well-formed).
CI boots the L1 image against a fixture RunSpec, runs the L2 units, and asserts the probes.
This is **Tier 1** verification — see "Two-tier verification" below.

**Run-pod image layering is its own open question (do NOT assume the shell image's posture
carries over).** The existing agent images are *long-lived, interactive, hardened* (non-root,
caps dropped, PVC-at-home seeding). A *transient, boot-provisioned* run pod has different
pressures: an L2 harness update writes to system-ish paths and may want **root at boot, then
drop to agent at runtime**. The hardened root-vs-agent split and PVC-seed model may make
boot-time provisioning awkward. Component A must explicitly revisit the layering / privilege
model for the transient case rather than inheriting `agent-shell-base`'s long-lived posture
unexamined.

### Component B — K8s runner (`super-fr` + `frank`)

- A `K8sRunner` implementing the existing `fr_dispatch` **`Runner` protocol**
  (`discover_plans` + `tick`) — the same seam `VkRunner` plugs into. The framework half needs
  no changes; this is a second adapter.
- `fr run up <RunSpec>` (skeleton: a CLI verb; later the bridge daemon) renders a **Pod +
  per-run PVC** and submits them via the K8s API. The PVC holds the clean clone + uncommitted
  "fiddle" state, so the run survives a pod restart (s6 + tmux-resurrect bring the session
  back).
- Inside the pod, the entrypoint starts the harness **inside a tmux session named `runId`**,
  running **fr-execute** against the phase Issue → autonomously to a PR. (Skeleton autonomy:
  hand-spawned, agent executes on its own.)
- **Cleanup contract (ported from fr-isolation):** pod + PVC **persist after the PR is
  created** (the operator may keep pushing). After the PR is observed **merged**, `fr run
  down` reaps the pod + PVC. `ttlSecondsAfterFinished`/a reaper backstops orphans.

### Component C — `runs-fr` web shell gateway (new standalone repo + Helm chart)

The only genuinely new artifact, so it is **born portable** — `fr` is already an independent
CLI and `agent-images` splits at its layer seams; the gateway is the missing piece.

- **Lists live runs** — queries the K8s API by the `fr.run/*` label selector; shows run
  metadata (plan, phase, branch, Issue link, status).
- **Browser terminal into a chosen pod** — backend uses the Kubernetes **`pods/exec`
  subresource** (the SPDY/websocket channel `kubectl exec` rides) to run
  `tmux attach -t <runId>`, bridged to an **xterm.js** terminal over a websocket.
- **Stateless** — the session (claude's PTY) lives in the pod inside tmux, so the gateway can
  restart/scale/redeploy without dropping anyone. **tmux named session + reconnecting web
  terminal ≈ mosh's resume-after-drop**, with no per-pod IPs or UDP ranges.
- **Cluster-agnostic by construction** — namespace, label selector, and auth method are
  **config inputs**; nothing frank-specific is compiled in. Distributed as an image + Helm
  chart; deployed to Frank via an ArgoCD app pointing at the chart.
- **Containment** — `pods/exec` is effectively root-in-namespace, so on Frank the gateway is
  gated behind **Authentik forward-auth** (Traefik `authentik-forwardauth` middleware +
  blueprint provider + manual outpost assignment) and its ServiceAccount gets
  **`pods/list` + `pods/exec` in the runs namespace only**. (Mirrors how secure-agent-pod's
  broad RBAC is justified by being a single trusted tenant.) The "trust a header" auth is only
  sound if the gateway is **unreachable except through the forward-auth proxy** — the proxy must
  SET and OVERWRITE the header (never merely add it), and the gateway Service stays `ClusterIP`
  with Ingress opt-in (a directly-reachable Service lets any client spoof the header straight
  into `pods/exec`).

## Walking-skeleton scope (this spec)

The spine, each seam exercised once:

```
RunSpec (minimal, real)
  → fr run up        spawns pod + per-run PVC from the RunSpec
  → L2 provisioning  3 probed units: update claude · inject 1 cred · attach skills
  → claude runs fr-execute on ONE phase, in tmux session <runId>   (autonomous)
  → runs-fr gateway  list + browser-attach (Authentik-gated)
  → PR opened
  → fr run down      reaps pod + PVC
```

- **One harness** (claude), **one profile** (frank `dev`), **hand-spawned** (no daemon).
- **Minimal capability bundle, real layering:** a small lockfile-pinned base (claude +
  super-fr + superpowers + super-fr-dispatch + core skills) ⊕ frank's repo overlay
  (`frank/agents/*`), no run overlay yet. Proves the three-layer resolve + the no-personal-
  `~/.claude` boundary; the full registry + `fr capabilities` is A+.
- **Gateway is feature-minimal but architecturally portable** — image + chart, config-driven
  seams, in `runs-fr` from the first commit.
- A **dedicated namespace** for run pods (e.g. `fr-runs`), so the gateway's RBAC and the
  reaper's selectors are scoped.

## Two-tier verification (why both are required)

Provisioning correctness and agent-behavioral compatibility are different things, and the
deterministic tier cannot prove the second. **Both tiers are required before a feature is
"complete."**

- **Tier 1 — deterministic, no open-ended agent (CI, every build):** the L2 probes. Proves
  the pod comes up *provisioned* — right versions, credential present & well-formed, skills/
  MCP present. Fast, repeatable, gates the image build. No task loop.
- **Tier 2 — real-agent smoke-test, driven the production way (required completion gate):**
  spawn the agent **exactly as a real run does** — interactively, in the named tmux session,
  via the same provisioning path — then send it an assertion prompt (e.g. *"report which
  config files you loaded and list your available fr skills"*), capture its answer from the
  session (`tmux send-keys` → `tmux capture-pane`), and assert on it. **Not** `claude -p` /
  headless: that's a *different invocation path* than prod, so it can pass while the
  interactive path has an auth or config-load quirk — the exact "find out too late" failure.
  The pod is reaped afterward anyway, so testing the real interactive path is free. It proves
  the things only a real agent surfaces: the harness **accepts** the credential (auth
  handshake succeeds, not just a token file exists), **fr + superpowers coexist**, and the
  right config is read (**AGENTS.md vs CLAUDE.md**). The prompt is a single Q&A, so it stays
  bounded and assertable without an open task loop. Extends the cluster's "a layer isn't
  Deployed until its workflow ran end-to-end" rule to "…with the real agent." Must be run with
  **every harness intended for prod** before that harness is considered shippable.

## Test plan / verification (end-to-end)

1. **Tier 1 — CI (component A, no cluster, no open-ended agent):** build L1 image; run L2
   units against a fixture RunSpec; assert every probe (`claude --version` == pin, credential
   present & well-formed, MCP/skills present). Failure of any probe fails the build.
2. **Tier 2 — real-agent smoke-test (production path):** spawn the agent interactively in the
   tmux session (same path as a real run), `tmux send-keys` the assertion prompt, `tmux
   capture-pane` the answer, and assert auth==authenticated, AGENTS.md loaded, fr +
   superpowers both visible. **Completion gate** — feature is not complete until this passes
   for claude (and, in follow-ups, every other prod harness). Pod is reaped after.
3. **Provisioning on-cluster:** `fr run up` a real RunSpec → pod Running → `kubectl exec` the
   probes pass live; tmux session `<runId>` exists with claude in it.
4. **Gateway:** hit `runs-fr` behind Authentik (browser) → run appears in the list → click →
   xterm attaches to the tmux session → close tab, reopen → session resumed (claude still
   working). Confirm an unauthenticated request is rejected by forward-auth.
5. **Autonomous execute:** the pod's claude runs fr-execute to completion → a PR is opened on
   the feature branch. (This run is the proof, not just Synced/Healthy.)
6. **Logs survive reap:** confirm the run's logs (provisioning, session, fr-execute output)
   are queryable in VictoriaLogs *by runId* **after** the pod is gone.
7. **Reap:** after the PR merges, `fr run down` deletes pod + PVC; verify nothing orphaned
   (`kubectl get pods,pvc -n fr-runs -l fr.run/id=<runId>` empty).

## Decomposition & sequencing (follow-up specs)

This skeleton fixes the **RunSpec contract** and the A/B/C boundaries. Subsequent specs
thicken each component independently:

- **B+:** the autonomous **bridge daemon** (`fr apply --to k8s` → tick → spawn), in
  `super-fr` (`fr_dispatch`/a `fr_k8s` adapter) + a `frank` ArgoCD app + narrow RBAC; runner
  registry entry; metrics like the VK bridge.
- **A+:** the full **multi-harness** matrix (codex/pi/hermes+local); the full **capability
  bundle registry** (versioned shared base bundles, repo overlays, run overlays) + `fr
  capabilities list/resolve` for discovery; each provisioning unit CI-probed.
- **B++:** **fr-goal** mode and the **in-session Q&A** flow (agent asks in the tmux session
  and blocks; operator attaches via the gateway and answers; Issue-comment fallback).
- **C+:** the gateway **read-only kanban view** (runs by state — scheduled / running /
  finished / failed — with filters), the broader **dashboard/GUI** (dispatch, status, run
  history), and a clean open-source release of `runs-fr`.
- **Observability+:** the detailed log policy — *which* streams are kept (provisioning,
  session transcript, fr-execute output), their **TTL/retention**, and **secret redaction**
  for the session transcript (a harness transcript can leak credentials) — plus run metrics
  (durations, success/failure counts, queue depth) à la the VK bridge gauges.

## Risks & open considerations

- **RunSpec churn:** it's the seam three components depend on; an early wrong shape is
  expensive. Skeleton keeps it minimal but real, and explicitly versionable.
- **`pods/exec` blast radius:** mitigated by namespace-scoped RBAC + Authentik gating;
  revisit if the gateway ever needs multi-tenant access.
- **Credential pre-auth limits:** subscription-based harnesses (claude/codex) may not have a
  clean headless pre-auth path; the L2 credential-injection unit must encode whatever the
  supported mechanism is, and its probe must prove the harness is actually authenticated, not
  merely that a token file exists.
- **Boot latency vs. freshness:** L2 updating the selected harness on every boot adds startup
  time; acceptable for pod-per-run, but the probe/update step should be fast-pathed when the
  baseline already matches the pin.
- **Behavioral compatibility surfaces late:** Tier 1 can't catch a harness rejecting a
  credential, an incompatible skill combo, or a config-read regression. The Tier 2 smoke-test
  is the guard — and because harnesses churn, it must be **re-run on every harness bump**, not
  only at feature time (wire it into the harness-bump path, like the image-bump verify step).
- **Capability drift / pinning:** the global base bundle is a shared input across runs and
  repos — if it floats, runs become non-reproducible. It must be versioned + lockfile-pinned
  like any other dependency, and the no-personal-`~/.claude` boundary must be enforced (a stray
  inherited hook or MCP server is both a reproducibility and a privacy leak).
- **Session-transcript redaction:** shipping the session log off-pod for audit risks leaking
  credentials the agent echoes; the redaction policy is a follow-up but the risk is real from
  the first run — until it lands, treat session-transcript shipping conservatively.
- **Spec ownership across repos:** this umbrella lives in `frank`; the `super-fr` and
  `agent-images` portions get their own specs/plans in those repos as B and A are built.
