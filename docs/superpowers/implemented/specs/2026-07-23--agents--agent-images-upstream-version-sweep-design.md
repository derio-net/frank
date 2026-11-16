# agent-images Upstream Version Sweep

**Layer:** agents (cross-repo — `derio-net/agent-images` owns the pin bumps; `derio-net/frank` owns live verification + docs)
**Status:** Deployed
**Date:** 2026-07-23
**Repo:** `derio-net/frank` (spec home) / `derio-net/agent-images` (primary change)
**Motivated by:** no upstream-version watcher exists for `agent-images`. Every pin in every
Dockerfile has drifted untracked since it was last set by hand. A measurement pass (2026-07-23)
found one pin that is **actively wrong** (`talosctl` is 3 minor versions behind the cluster it
talks to, outside Talos's supported skew) and several multi-release gaps.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-23--agents--agent-images-version-sweep | `derio-net/agent-images` | `2026-07-23--agents--agent-images-version-sweep` | — |
| 2026-07-23--agents--agent-images-sweep-verify | `derio-net/frank` | `2026-07-23--agents--agent-images-sweep-verify` | agent-images plan (its build must publish first) |

---

## §1 Measured inventory (2026-07-23)

Every version-bearing `ARG`/`FROM` across `agent-images`, measured against its upstream registry
on 2026-07-23. **Frank is fully in sync with `agent-images` main (`a59f499`)** — every
`ghcr.io/derio-net/*` pin under `apps/` is at that SHA — so there is no frank-side drift to fix.
All drift is upstream-of-the-image.

| Pin | File | Current | Upstream | Class | Gap |
|---|---|---|---|---|---|
| `TALOSCTL_VERSION` | `infra-shell`, `kali` | `v1.9.5` | **cluster runs v1.12.6**; latest `v1.13.7` | rebuild-only | **3 minors behind the cluster — unsupported skew** |
| `OMNICTL_VERSION` | `infra-shell`, `kali` | `v0.45.1` | latest `v1.9.3`; server version *not in repo* | rebuild-only | major version; target must be discovered |
| `RUFLO_GIT_REF` | `ruflo-server` | `a6dd4ab` | `26c35b5` (607 commits) | rebuild-only | **1 file in the built subtree** (see §3.4) |
| `HERMES_VERSION` (PyPI `hermes-agent`) | `hermes-agent-shell` | `0.15.2` | `0.19.0` | seed venv → PVC | 4 minors |
| `HERMES_TAG` (Docker `nousresearch/hermes-agent`) | `hermes-agent-shell-ssh` | `v2026.7.7.2` | `v2026.7.20` | rebuild-only | 1 release |
| `S6_OVERLAY_VERSION` | `agent-shell-base` | `3.2.0.2` | `3.2.3.2` | rebuild-only | 3 patches (**PID 1**) |
| `SUPERCRONIC_VERSION` | `base` | `0.2.33` | `0.2.47` | rebuild-only | 14 patches |
| `HINDSIGHT_API_VERSION` | `hermes-agent-shell-hindsight` | `0.8.4` | `0.8.5` | rebuild-only | 1 patch |
| `NODE_MAJOR` | `base` | `22` | `24` available | rebuild-only | major (**base of every shell**) |
| `CODEX_VERSION` | `multi-agent-shell` | `0.136.0` | `0.145.0` | **bootstrap** | 9 minors (self-heals) |
| `OPENCODE_VERSION` | `multi-agent-shell` | `1.15.13` | `1.18.4` | **bootstrap** | 3 minors (self-heals) |
| `@anthropic-ai/claude-code` | `base` | *unpinned* | `2.1.218` | **bootstrap** | floats every build |
| `MICROMAMBA_VERSION` | hindsight | `2.8.1` | `2.8.1` | — | **current ✓** |
| `TORCH_VERSION` | hindsight | `2.13.0` | `2.13.0` | — | **current ✓** |
| `TMUX_RESURRECT_REF` | `agent-shell-base` | `v4.0.0` | `v4.0.0` | — | **current ✓** |
| `TMUX_CONTINUUM_REF` | `agent-shell-base` | `v3.1.0` | `v3.1.0` | — | **current ✓** |
| `BGE_REVISION` | hindsight | HF commit | not measured | rebuild-only | model revision — out of scope |
| `VK_FORK_SHA` | `vk-local` | own fork build | n/a | own repo | out of scope |
| `debian:bookworm-slim`, `node:24`, `kali-rolling` | various | rolling tags | n/a | floats | no pin drift |

### Image → frank app mapping

| agent-image | Consumed by (frank app) |
|---|---|
| `multi-agent-shell` | `alert-agent` (×3 containers), `cnc-base`, `n8n-01` |
| `secure-agent-kali`, `vk-local` | `secure-agent-pod` |
| `paperclip-shell` | `paperclip` |
| `ruflo-server`, `ruflo-shell` | `ruflo` |
| `hermes-agent-shell-ssh`, `hermes-agent-shell-hindsight` | `hermes-agent-shell` |
| `infra-shell` | **built but not deployed** (in `AGENT_IMAGES`, pinned nowhere) |

### Inheritance (determines blast radius)

```
base (agent-base)  ── NODE_MAJOR, SUPERCRONIC, claude-code
 └── agent-shell-base  ── S6_OVERLAY, tmux plugins
      ├── kali                    ── TALOSCTL, OMNICTL
      ├── multi-agent-shell       ── CODEX, OPENCODE
      │    ├── hermes-agent-shell-hindsight  ── MICROMAMBA, HINDSIGHT_API, TORCH, BGE
      │    └── infra-shell        ── TALOSCTL, OMNICTL
      ├── paperclip-shell
      ├── ruflo-shell
      └── hermes-agent-shell      ── HERMES_VERSION (PyPI)
vk-local            ← agent-base + vibe-kanban-build
ruflo-server        ← node:24 (standalone)  ── RUFLO_GIT_REF
hermes-agent-shell-ssh ← nousresearch/hermes-agent (standalone)  ── HERMES_TAG
```

A `base` bump rebuilds **everything**. An `agent-shell-base` bump rebuilds every shell.
`ruflo-server` and `hermes-agent-shell-ssh` are the only images outside that tree.

---

## §2 The two pin classes

The single most useful distinction for prioritising this work — discovered by reading the
Dockerfile comments rather than the pins themselves:

- **Bootstrap pins** (`claude-code`, `@openai/codex`, `opencode-ai`). The Dockerfile line is only
  a first-boot seed. The CLI self-updates in-pod and floats forward via the shell-inventory
  `harnesses:` key. `multi-agent-shell/Dockerfile` says so explicitly: *"These pins float forward
  via the inventory `harnesses:` key; the Dockerfile shim is only a bootstrap."* Bumping them
  changes what a **fresh** PVC starts from — nothing more. Near-zero risk, near-zero value,
  but free to carry along with a rebuild.
- **Rebuild-only pins** (everything else). The image rebuild is the **only** refresh path. This is
  where staleness is real, and where `talosctl` has become a correctness problem.

`agy` (antigravity CLI) is a third, degenerate case: binary-distributed by vendor script with no
version pin and no self-update, so it silently floats to whatever is current **on each rebuild**.
Nothing to bump; worth knowing it changes underneath us whenever we rebuild for other reasons.

---

## §3 Risk assessment

### §3.1 `talosctl` v1.9.5 → v1.12.6 — **correctness fix, do first**

The cluster runs **Talos v1.12.6** on all seven nodes (verified live). Talos supports a client
within **±1 minor** of the node. A v1.9.5 client against v1.12.6 nodes is three minors out —
outside support, with API drift that surfaces as confusing partial failures rather than a clean
"version mismatch" error.

**Target is the cluster version (`v1.12.6`), not latest (`v1.13.7`).** Pinning to latest would
put the client one minor *ahead* of the nodes — still supported, but it re-creates the same drift
problem the moment the pin is forgotten again, and it invites an upgrade-by-accident. Matching the
cluster is the maintainable rule.

Affects `infra-shell` (not deployed) and `kali` → `secure-agent-pod`. Blast radius is small; the
tool is used interactively, so a regression is immediately visible rather than silent.

**Residual risk:** when the cluster is next upgraded, this pin silently goes stale again. §5's
audit script is the mitigation — it should compare `talosctl` against the *cluster*, not against
GitHub's latest release.

### §3.2 `omnictl` v0.45.1 → *discovered target* — **cannot be hardcoded**

Omni is **reachable again** (`https://omni.frank.derio.net` → HTTP 200), so this is live, not
dormant. But the running server's version is **not recorded in this repo**: `omni/omni/compose.yaml`
interpolates `${OMNI_IMG_TAG}` from an `omni.env` that lives out-of-band on the Omni host
(`omni.env.template` is the only tracked artifact).

`omnictl` must track the **server**, not GitHub's latest. Upstream is at `v1.9.3` while frank's
server was last documented at `v1.5.0` — a bump to latest would very likely break against the
running server.

**Therefore the plan must include a discovery step**, not a hardcoded target: read the live
server's version (from the Omni host's `omni.env`, or from `omnictl`'s own client/server version
report) and pin to it. If discovery fails, this pin is **deferred with a written note** rather
than guessed — a wrong `omnictl` is worse than an old one, because it fails against the one
control plane that manages machine config.

### §3.3 `s6-overlay` 3.2.0.2 → 3.2.3.2 — **widest blast radius**

s6-overlay is **PID 1 in every agent shell**. A regression does not degrade a feature; it stops the
container from booting. The repo already carries hard-won s6 knowledge (non-root mode needs
`S6_KEEP_ENV=1`, `with-contenv` shebangs must be `/command/`, `/run` chowned at build, the 5-deaths-
in-60s crashloop bail) — all of which is v3-contract behaviour that a patch release should preserve.

Three patch releases within 3.2.x is a low-probability break, and `agent-images` CI has a
`smoke-test-*` job per image asserting `/init` boots under a K8s-equivalent securityContext — which
is precisely the failure this would cause. **The smoke jobs are the control that makes this
acceptable**, which is why §5's branch-build dispatch is non-negotiable for this wave.

### §3.4 `RUFLO_GIT_REF` a6dd4ab → 26c35b5 — **headline says 607 commits; the truth is one file**

This looked like the highest-risk item in the sweep and turned out to be among the lowest. The
measurement matters more than the conclusion, so it is recorded in full:

- `ruvnet/ruflo` is a **monorepo**; `agent-images` builds only the `ruflo/src/ruvocal/` subtree
  (`ruflo-server/Dockerfile` COPYs `/src/ruflo/ruflo/src/ruvocal/` into the builder and nothing else).
- A naive `gh api compare` over the range reports 607 commits — but **`.files[]` is capped at 300
  entries**, and the truncated list contains zero `ruvocal` paths. That is a **false negative**: the
  subtree tree-SHAs differ (`c95e6a06…` → `7b223792…`).
- Diffed properly, blob-by-blob: **501 blobs at both refs, no additions, no removals, exactly one
  content change** — `ruflo/src/ruvocal/mcp-bridge/index.js`.

**Both local modifications still apply cleanly**, because both targets are byte-identical across
the range:
- the `sed -i` `wasm:` allow-line in `urlSafety.ts` — anchor line still present, `wasm:` still not
  allowed upstream, so the patch is **still required**;
- `patches/rvf-gridfs-parity.patch` against `rvf.ts` — upstream carries **none** of `new Writable`,
  `Readable.from`, `next: async`, so the shim repair is **still required**. (Upstream PR
  `ruvnet/ruflo#2293` is **open, not merged** — an earlier note in this repo implying it was
  upstreamed is wrong.) Both are guarded by post-apply `grep`s that fail the build on a silent
  no-op, so a future drift is fail-loud.

**The one changed file is a security fix.** `mcp-bridge/index.js` gains ADR-166 hardening closing a
disclosed **unauthenticated RCE chain**: default-deny for `terminal_execute`-family tools
(`MCP_ENABLE_TERMINAL` opt-in), default bind moved to `127.0.0.1`, a fatal refusal to bind a public
interface without `MCP_AUTH_TOKEN`, bearer auth with `timingSafeEqual`, and a CORS allowlist
replacing the unconditional `*`.

**Net risk to frank: very low.** `mcp-bridge` is **not shipped in the runtime image** — the runtime
stage copies only `/app/build`, `/app/node_modules`, `.env`, `entrypoint.sh`, `package.json`; the
bridge is a standalone express server that is not part of the SvelteKit build output. Frank's
`ruflo` deployment references neither port 3001 nor any `MCP_*` variable. So the bump is close to a
functional no-op for the deployed artifact while removing a known-vulnerable file from the build
context.

**Residual risk (real, and not specific to this bump):** `package.json` is byte-identical across
the range, so its semver ranges resolve to whatever npm publishes **at build time**. Any rebuild —
including the ones in Wave 1 — changes transitive dependencies. This is an existing property of the
image, not something this bump introduces, but it means "no source change" ≠ "identical image", and
the ruflo smoke test (`ruvocal boots and binds port 3000`) is the thing that catches it.

### §3.5 `hermes-agent` (PyPI) 0.15.2 → 0.19.0 — **PVC-resident, so the bump may not take**

Four minor versions. The complication is not the version gap but the delivery mechanism: the venv
is built as a **relocatable seed** at `/opt/hermes-agent` and `cp -a`'d onto the `/home/agent` PVC
on first boot, **gated by a `.seed-version` marker** (frank#496). Consequences:

- A new image alone does **not** upgrade a shell with an existing PVC — the marker must change for
  the seed to re-apply, otherwise the pod happily runs 0.15.2 out of an image that ships 0.19.0.
  Verification must therefore assert `hermes --version` **inside a running pod**, not in the image.
- The seed marker is `${HERMES_VERSION}+autocontinue1` — it changes with the version, so the
  re-seed should fire; this must be **confirmed live**, not assumed.
- Frank pins Hermes behaviour out-of-band: `config.yaml` carries a provider **mapping** (model-string
  prefixes do not pin the provider) and `context_length` overrides that must equal live reality, or
  the compressor engages against a wrong boundary and poisons sessions. `config.yaml` is PVC state
  (manual-op `orch-hermes-config-provider`). A 4-minor jump may change config schema or defaults.
- Hermes hard-requires a ≥64k context window; the 64k model aliases are load-bearing.

**Risk: moderate, and the failure mode is quiet** (a working-looking shell with a degraded agent
loop). Wave 2, with live per-pod verification of `hermes --version`, provider resolution, and
context length.

### §3.6 `NODE_MAJOR` 22 → 24 — **structural; touches every image**

Node is installed in `base`, so this rebases the runtime under every shell and under the npm-global
harnesses (`claude-code`, `codex`, `opencode`) that are installed against it. Node 22 and 24 are
both supported LTS lines, so this is a *hygiene* bump with no correctness driver behind it — the
only pin in the sweep of which that is true.

Specific hazards: native modules under the shells' npm globals recompile against a new ABI; the
`shell-inventory` reconciler reinstalls npm globals at boot and has already produced one deadlock
(a stale retired dir → `ENOTEMPTY`) when its guard was wrong. A Node major change is exactly the
event that re-triggers that class of bug on live PVCs.

**Risk: moderate-to-high relative to zero benefit.** Kept in scope per the operator's selection, but
sequenced **last and alone** (Wave 3b) so it can be dropped without holding anything else back.

### §3.7 Low-risk remainder

- **`supercronic` 0.2.33 → 0.2.47** — a cron runner; 14 patch releases. Used by the alert-agent
  cred-expiry cron and the shell reconcilers. Auto-reloads on crontab change. Contained failure
  mode, visible via the existing `cred-expiry-check` heartbeat dead-man rule.
- **`hindsight-api` 0.8.4 → 0.8.5** — single patch, confined to the hindsight sidecar. Note the
  sidecar's Postgres `PGDATA` permission trap is handled image-side (boot-time `chmod 700`), so a
  rebuild must not regress it.
- **`hermes-agent` Docker `v2026.7.7.2` → `v2026.7.20`** — one upstream release, standalone image
  (`hermes-agent-shell-ssh`), smoke-tested for `sshd` binding 2222.
- **`codex` / `opencode` / `claude-code`** — bootstrap-only (§2). Carried along; not independently
  verified beyond the image building.

### §3.8 Pins deliberately **not** touched

`MICROMAMBA_VERSION`, `TORCH_VERSION`, `TMUX_RESURRECT_REF`, `TMUX_CONTINUUM_REF` are already at
upstream latest. `BGE_REVISION` is a HuggingFace **model** revision, not a software version — bumping
it changes embedding behaviour and belongs to a Hindsight-quality decision, not a version sweep.
`VK_FORK_SHA` is built from our own fork by a separate pipeline.

---

## §4 Selection and sequencing

Operator selection: **full sweep, including the ruflo re-vendor and Node 24** (§A/d1). The risk
tiering above does not change what is in scope; it changes the **order**, so that a wave that
proves intractable cannot hold back the waves that are already proven.

| Wave | Contents | Rationale |
|---|---|---|
| **0** | Version-audit script | Independent of every bump; makes the rest measurable and re-runnable |
| **1** | `talosctl`→v1.12.6, `supercronic`→0.2.47, `hindsight-api`→0.8.5, hermes Docker→v2026.7.20, `codex`→0.145.0, `opencode`→1.18.4 | The correctness fix plus contained-blast-radius patches |
| **2** | `s6-overlay`→3.2.3.2, `hermes-agent` PyPI→0.19.0 | Wide blast radius, but well covered by smoke tests + live checks |
| **3a** | `RUFLO_GIT_REF`→26c35b5 | Low measured risk (§3.4) + a security fix; independent of the base tree |
| **3b** | `NODE_MAJOR`→24 | Structural, no correctness driver; **droppable** without affecting 0–3a |
| **defer?** | `omnictl` | Target must be discovered from the live server (§3.2); deferred with a note if discovery fails |

Waves 1–3 may ship as **one agent-images PR** if the branch build is green across all of them.
If Wave 3b (Node 24) or the `omnictl` discovery stalls, ship 0–3a and carry the remainder into a
follow-up PR rather than blocking. This is an explicit allowance, not a fallback to improvise.

---

## §5 Validation strategy

### The gap that shapes everything

`agent-images`' `build.yaml` triggers on **`push` to `main` only** (with `paths-ignore: docs/**`),
`workflow_dispatch`, and `repository_dispatch` — **not on `pull_request`**. A bump PR therefore
receives **zero automatic build or smoke coverage**, and because the `push` trigger is branch-
restricted, *pushing the feature branch does not build it either*. `workflow_dispatch` is the only
way to exercise a branch. Merging on a green-looking PR would be merging blind.

**Every wave must be validated by an explicit branch build:**

```bash
gh workflow run build.yaml --ref <branch>
```

`build.yaml` carries a per-image smoke job — `/init` booting under a K8s-equivalent securityContext
for each s6 shell, `ruvocal boots and binds port 3000` for `ruflo-server`, `sshd binds 2222` for
`hermes-agent-shell-ssh`, the entrypoint wrapper for `vk-local`. These are the controls that make
§3.3 and §3.4 acceptable risks; a wave is not validated until its images' smoke jobs are green.

### The audit script (Wave 0)

A script in `agent-images` that parses every version-bearing `ARG`/`FROM` out of the Dockerfiles and
reports current-vs-upstream. On demand only — **no scheduled workflow, no drift PRs** (§A/d3).

Requirements learned from building the table by hand:
- Resolve per source type: npm registry, PyPI, GitHub releases **and tags** (tmux plugins publish
  tags, not releases — a releases-only lookup 404s), Docker Hub tags.
- **`talosctl` compares against the live cluster version, not GitHub latest** (§3.1). `omnictl`
  compares against the live Omni server (§3.2). Encoding "latest is not the target" for these two is
  the script's main non-obvious value.
- Classify each pin **bootstrap vs rebuild-only** (§2) so the report ranks by what actually matters.
- Exit non-zero only on request; the default is a report, not a gate.

### Propagation to frank

Frank needs no manual pin edit: `agent-images` `repository_dispatch`es on main push and frank's
`.github/workflows/agent-images-bump.yml` opens the bump PR, rewriting every
`ghcr.io/derio-net/<img>:<sha>` under `apps/` and failing loudly on any image missing from
`AGENT_IMAGES`. That path is already proven — frank is currently at `a59f499`, exactly
`agent-images` main HEAD.

---

## §6 Frank-side work

Small by design; the bump arrives automatically.

1. **Verify the auto-bump PR** covers every rebuilt image (the coverage step should pass; a failure
   means an image is missing from `AGENT_IMAGES`).
2. **Live per-shell verification** after merge — the Test Plan below.
3. **Docs**: a one-line gotcha per durable lesson in `agents/rules/frank-gotchas.md` with prose in
   `docs/runbooks/frank-gotchas/agent-shells.md` — specifically the talosctl/cluster-skew rule, the
   `pull_request`-blind CI, and the hermes `.seed-version` "image ships N, pod runs N-1" trap.
   Correct the stale claim that the ruflo GridFS fix was upstreamed (§3.4).

---

## §7 Named gaps and open risks

- **The `omnictl` target is unknown until discovered live** (§3.2). This is the one selected item
  that may not ship, by design rather than by failure.
- **`package.json` drift is invisible to a git-ref pin** (§3.4). Any rebuild moves transitive
  dependencies; no pin in this repo controls that.
- **Node 24 (§3.6) has no correctness driver.** It is in scope because it was selected, and it is
  sequenced last so that saying "not now" costs nothing.
- **`infra-shell` is built and bumped but deployed nowhere.** CI does carry a `smoke-test-infra-shell`
  job, so the image is proven to boot — but its `talosctl`/`omnictl` bumps are unverifiable
  *in-cluster*. Live verification for those pins runs through `kali` (`secure-agent-pod`).
- **The audit script itself becomes a pin to maintain.** It hardcodes how to reach four registry
  APIs; those change. It is on-demand precisely so a break is discovered when someone runs it, not
  as a red CI light nobody reads.
- **Three things float on every rebuild, untracked** — `agy` (vendor script, no pin, no self-update),
  `kubectl` (`infra-shell`/`kali` fetch `dl.k8s.io/release/stable.txt`, i.e. always latest), and
  `@anthropic-ai/claude-code` (unpinned `npm i -g`). This sweep rebuilds every image, so all three
  change as a side effect, unverified. Out of scope, but they are real uncontrolled variables — and
  note `kubectl`-from-`stable.txt` has exactly the skew exposure §3.1 describes for `talosctl`, just
  with a wider support window (±1 minor against the cluster's v1.35.3).
- **The images are amd64-only** (`build.yaml` sets no `platforms:`, and `agent-shell-base` hardcodes
  the `s6-overlay-x86_64` tarball). Consistent today, but it means the s6 bump needs no arch
  handling — and that these shells cannot schedule on the arm64 Pi nodes.

---

## Test Plan

*Post-merge — operator-driven. Claims here are the acceptance rows.*

**Pre-merge (agent-images, per wave):**
1. `gh workflow run build.yaml --ref <branch>` — dispatch the branch build (CI does **not** run on
   `pull_request`).
2. All per-image smoke jobs green for every image the wave rebuilds.

**Post-merge (frank, after the auto-bump PR lands):**
3. **talosctl skew closed** — in `secure-agent-pod` (kali): `talosctl version` reports client
   `v1.12.6` and contacts the cluster without a version-skew warning.
4. **supercronic live** — a shell running the reconciler cron shows the new version and the
   `cred-expiry-check` heartbeat still lands (its Grafana dead-man rule stays quiet).
5. **s6 boots everywhere** — every rebuilt shell pod reaches `Running` with all containers ready;
   no s6 crashloop-bail in logs. Covers `alert-agent` (3 containers), `cnc-base`, `n8n-01`,
   `secure-agent-pod`, `paperclip`, `ruflo`, `hermes-agent-shell`.
6. **hermes actually upgraded in-pod** — `hermes --version` **inside the running pod** reports
   `0.19.0` (not just in the image), confirming the `.seed-version` re-seed fired; provider
   resolution and `context_length` still match live reality per `config.yaml`.
7. **hindsight sidecar healthy** — Postgres starts (no `PGDATA` permission regression) and the
   Hindsight API answers.
8. **ruflo serves** — `ruvocal` responds on `/api/v2/feature-flags` and the UI loads via its
   IngressRoute; file upload/download still works (proves the GridFS patch survived the re-vendor).
9. **vk-local / secure-agent-pod** — SSH in on `192.168.55.215`, `vk` UI reachable on `:8081`.
10. **Audit script runs clean** — re-running it reports every bumped pin as current, and correctly
    reports `talosctl` against the cluster rather than against GitHub latest.

---

## §A Decisions

Rendered from the spec journal (`fr journal render --scope spec --section decisions`):

- **d1 — Selection scope: full sweep including ruflo re-vendor + Node 24.** Operator chose the most
  aggressive option with both risks stated in the option text. Sequenced into waves so a stuck wave
  does not hold the others hostage.
- **d2 — `talosctl` targets the cluster version (v1.12.6), not latest (v1.13.7).** Matching the
  cluster is the maintainable rule; chasing latest re-creates skew in the other direction.
- **d3 — Leave behind an on-demand version-audit script; no scheduled watcher.** Avoids CI noise and
  an auto-merge path.
- **d4 — Test Plan: dispatch a branch build, then live per-shell verification.** Forced by
  `build.yaml` triggering on `push`, not `pull_request`.
- **d5 — All fr model tiers bound to `claude-opus-4-8`.** Judgment-heavy work; tier differentiation
  buys little.
