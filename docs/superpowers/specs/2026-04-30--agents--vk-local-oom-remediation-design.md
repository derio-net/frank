# vk-local OOMKill Remediation — Design

**Spec:** `docs/superpowers/specs/2026-04-30--agents--vk-local-oom-remediation-design.md`
**Layer:** `agents`
**Type:** Fix/extension of the `agents` layer (extends [`2026-04-15--agents--agent-images-and-vk-local-sidecar-design`](2026-04-15--agents--agent-images-and-vk-local-sidecar-design.md))
**Status:** Draft
**Tracking issue:** [derio-net/frank#140](https://github.com/derio-net/frank/issues/140)

---

## Goal

Stop `vk-local` (the VibeKanban server inside `secure-agent-pod`) from being OOMKilled under normal usage, and put the cluster in a position to monitor — and ratchet down — the memory limit later as configurable safeguards land. Specifically:

1. Confirm the immediate fix (Option A — limit raised 2 Gi → 8 Gi in PR #142) holds under real workload and is observable in metrics.
2. Restore continuous container-memory time-series for `gpu-1` (and the four other nodes affected by the same scrape gap) so future memory work has data instead of guesses.
3. Cut the long-tail working-set sources that bloat `vk-local`'s saturated-idle baseline (npm cache, leftover worktrees) — a pure housekeeping change in the agent-images fork that recovers ~900 MiB.
4. Add a `max_concurrent_executions` cap (Option B1) to the vibe-kanban binary, surfaced as a Frank-side env var, so spawn fanout becomes an explicit policy decision rather than implicit-unbounded.
5. Park Option B2 (delegate child processes to the `kali` cgroup) and Option B3 (per-task Kubernetes Jobs) as tracking issues, deferred until the A + housekeeping + B1 stack has been measured in production.

The success criterion is no `vk-local` OOMKill events for **30 days** of normal usage with the cap enforced and housekeeping running, and either continued comfort at 8 Gi *or* a documented dial-back to a smaller limit backed by cadvisor data.

## Motivation

`vk-local` was OOMKilled **27 times in ~18 hours** on 2026-04-28 at the 2 Gi limit (boot → OOM in ~4 s at startup). The Phase 3 memprofile findings ([`agent-images:kali/docs/findings/2026-04-22-vk-local-memory-profile.md`](https://github.com/derio-net/agent-images/blob/main/kali/docs/findings/2026-04-22-vk-local-memory-profile.md)) ruled out a leak (idle drift ≈ 1.5 MiB/h, far below the 10 MiB/h leak threshold) and traced the pressure to three compounding sources inside the cgroup:

| Source | Magnitude | Freed when? |
|---|---|---|
| Active session children (`claude` + `npm` + `node`) | **~480 MiB / session** | on session exit |
| Retained npm file-cache (12 GiB on PVC, no pruning) | **~900 MiB** post-session | not until memory pressure |
| vibe-kanban worktree heap | **~17 MiB / live worktree** | accumulates across sessions |

Saturated-idle (worktrees + retained file cache, zero active sessions) sits at **~1,157 MiB**. With the previous 2 Gi limit, even a second concurrent session pushed past 2 GiB and triggered the killer. PR #142 raised the limit to 8 Gi as the immediate unblock; this spec's job is to make the fix durable, observable, and dial-back-able.

Two facts from the findings shape the rest of the design:

- **Phase 2 retake on image `dc414b4` showed 20 kills / 17.4 h vs. Phase 1's 6 kills / 48 h** — a 9× escalation under similar workload. The cause is unconfirmed (workload variance vs. binary regression vs. measurement window). This is non-blocking for the remediation but is filed as a tracking issue so it doesn't get lost.
- **vibe-kanban exposes no `/metrics` endpoint.** Any B1 telemetry (queue depth, active session count, queue waits) must be added alongside the cap. The cadvisor data gap, separately, is the only source for cgroup-level RSS — fixing it is a precondition for measuring whether B1 lets us shrink the 8 Gi limit safely.

## Constraints

1. **No upstream `vibe-kanban` patches outside our fork.** B1 lives in [`derio-net/agent-images`](https://github.com/derio-net/agent-images) on top of the existing fork, with the config schema bumped from `v8` to `v9`. The Frank side surfaces the knob as an env var on the `vk-local` container in `apps/secure-agent-pod/manifests/deployment.yaml`.
2. **Single-driver-process discipline preserved.** vibe-kanban remains the only direct K8s-supervised process in `vk-local`; child processes stay forked under it. (B2 would change this and is explicitly parked.)
3. **No new alerting infrastructure in this plan.** Existing `Layer 18 Persistent Agent Heartbeat Stale` covers the user-visible failure mode; adding cgroup-RSS alerts is deferred until the cadvisor gap is fixed and a baseline is collected.
4. **Cadvisor gap fix must not change scrape semantics for nodes that already work.** `raspi-1` and `raspi-2` currently produce data; whatever the fix is must not break them.
5. **Housekeeping must not delete user data.** `git worktree prune` only removes administrative metadata for already-deleted worktrees; npm cache prune must target only stale entries (`npm cache verify` / age-bounded). No PV `rm -rf`.

## Approach

The plan is structured as six execution phases plus a post-deploy checklist. The ordering deviates from the issue's suggested A → B1 → cadvisor order in two ways:

- **A is already shipped** (PR #142, merged). It collapses to a verification/observation step.
- **Cadvisor gap is moved before B1** because B1's value proposition — "lets us dial back the 8 Gi limit" — is unverifiable without time-series RSS data. Fixing the metric pipeline first means B1 ships into a cluster that can actually measure its effect.

Housekeeping (H) is inserted between the cadvisor fix and B1 because it is the highest-leverage change after A: pure agent-images cron work, no API surface, recovers nearly twice the memory of a single concurrent session.

### Phase ordering

```
Phase 1 (A-verify)  →  Phase 2 (cadvisor)  →  Phase 3 (housekeeping)  →  Phase 4 (B1)  →  Phase 5 (soak + dial-back assessment)  →  Phase 6 (track B2/B3/regression)
```

### Phase 1 — Verify Option A in production

Pure observational. PR #142 raised the limit; this phase confirms the live deployment carries the new value, that no OOMKill has occurred since, and that the 30-day clock for the success criterion has started.

- Inspect the live pod spec on `gpu-1` to confirm `vk-local` shows `limits.memory: 8Gi`.
- Read the container restart count and the kubelet event log for `OOMKilled` reasons over the last 7 days.
- Capture a baseline of working-set RSS via `kubectl top pod` (until cadvisor is fixed in Phase 2, this is the only reading we have).

This phase produces no manifest change. It exists so the verification is on the record before deeper changes ship.

### Phase 2 — Fix cadvisor data gap (5 of 7 nodes)

The investigation that informed this spec found that the cadvisor scrape **targets** for all 7 nodes report healthy in vmagent, but `container_memory_working_set_bytes` series only exist for `raspi-1` and `raspi-2`. The same is true of `scrape_samples_scraped` filtered to `metrics_path=/metrics/cadvisor` — only the two raspi nodes are persisted. So the gap is wider than the issue framed it (which said only `gpu-1`); it is **5 of 7 nodes** (`mini-1`, `mini-2`, `mini-3`, `gpu-1`, `pc-1`).

Probable root causes, in decreasing likelihood:

1. **A relabel rule drops series for amd64 nodes.** The `VMNodeScrape` for cadvisor (in `apps/victoria-metrics/`) has a `metricRelabelConfigs` block that drops several labels including `(id|name)`. If the cadvisor metric `__name__` matches that regex (e.g., for `container_name`/`pod_name` legacy mirrors), it could nuke all the per-container series. This is testable by removing the regex temporarily on a single node.
2. **Streaming parse + cardinality limits.** `vmagent` is started with `-promscrape.streamParse=true` and `-remoteWrite.maxDiskUsagePerURL=1073741824`. If a per-target cardinality cap kicked in for the noisier amd64 cadvisor endpoints, vmagent would log discards. The two raspi nodes have far fewer pods (low-power tier) so they slip under any cardinality limit.
3. **vmsingle ingestion limits.** `vmsingle` retention is 1 month with 20 GiB Longhorn backing. If we tripped a samples-per-second limit, only the smaller-footprint nodes would survive.

Phase 2 investigates these in order, fixes whichever applies, and verifies via `count(container_memory_working_set_bytes) by (node)` that all 7 nodes return non-zero. The fix is whatever is minimum-invasive: a relabel-rule edit, a vmagent flag bump, or a vmsingle retention/limit tweak — committed via the existing `apps/victoria-metrics/values.yaml` Helm overlay.

The phase ends with a 24h observation window confirming the metric stays populated and a saved Grafana panel for `vk-local`'s working-set RSS pinned to the secure-agent-pod operating dashboard.

### Phase 3 — Housekeeping (npm cache prune + worktree prune)

Pure agent-images change. Two pieces:

- **npm cache prune cron** inside `vk-local` (or `kali`, whichever has supercronic available — see open question below). Run weekly: `npm cache verify` to remove tarballs older than ~7 days. The Phase 2 metrics will show the effect within hours.
- **Worktree prune cron** inside `vk-local`. Run weekly: `git -C <each-tracked-repo> worktree prune` to clear administrative metadata for already-removed working directories. Combined with vibe-kanban's existing worktree lifecycle (delete on task completion), this drops the residual ~17 MiB/worktree heap.

Effects, predicted from the findings:
- Saturated-idle drops from ~1,157 MiB to ~220 MiB.
- After 24 h with crons running: cadvisor working-set median for `vk-local` should sit closer to 200 MiB than 1.1 GiB.

This is shipped via a PR against [`derio-net/agent-images`](https://github.com/derio-net/agent-images), then picked up by Frank's existing image-bumper workflow. No frank-side change is required for this phase.

### Phase 4 — Option B1: `max_concurrent_executions`

Cross-repo. The cap and queue logic live in the vibe-kanban fork; the surface is a Frank env var.

**Agent-images side** (vibe-kanban Rust fork):
- Bump config schema `v8` → `v9` with a new optional field, `max_concurrent_executions: Option<usize>` (default `None` = current unbounded behavior).
- Read the value from `VK_MAX_CONCURRENT_EXECUTIONS` env at process start as a fallback (so we don't need a config-file mount on Frank).
- Wrap the executor's spawn path in a counting semaphore. When the cap is reached, *queue* (block the caller's task in Tokio) — do **not** reject. Queued executions log a structured event `{event: "execution_queued", waiting: N, max: M}` so the cap is observable in fluent-bit logs even before a `/metrics` endpoint exists.
- Add a minimal `/metrics` endpoint exposing three gauges: `vibekanban_active_executions`, `vibekanban_queued_executions`, `vibekanban_max_executions`. The endpoint is the smallest reasonable telemetry surface; full Prometheus instrumentation is out of scope here.

**Frank side**:
- Add `VK_MAX_CONCURRENT_EXECUTIONS=4` to the `vk-local` container env in `apps/secure-agent-pod/manifests/deployment.yaml`.
- Add a `VMServiceScrape` for the new `/metrics` endpoint (or `VMPodScrape` if no Service exposes 8081 internally — needs verification).
- The cap value `4` is chosen so the worst-case live cgroup at saturated-idle + capped sessions is ~220 + 4×480 = **2,140 MiB** — fits in 3 Gi with margin, leaves the 8 Gi A-limit massively over-provisioned (which is the explicit goal: A becomes the safety net while B1 is the policy).

The choice of `4` (vs `6` or `8`) is conservative; the operator can raise it via env-var edit + ArgoCD sync without touching the binary.

### Phase 5 — Soak + dial-back assessment (manual)

After Phases 1–4 are deployed, run a 14-day soak under the operator's normal workload, then inspect:

- `container_memory_working_set_bytes` for `vk-local` — p99 should track close to `220 + (active × 480) MiB`, not the legacy 1.1 GiB saturated-idle.
- `vibekanban_queued_executions` — non-zero spikes prove the cap is active. If always zero, the cap is set higher than the operator ever uses; consider lowering. If p99 > 1 sustained, the cap is too low; raise it.
- vibe-kanban container restart count — must remain at zero (no OOMKills).

The output is a short follow-up PR proposing one of:
- (a) Keep the 8 Gi limit, no change. Document the soak result.
- (b) Dial the limit back to **3 Gi** (covers cap=4 + housekeeping with 40% margin). Lowest sustainable footprint.
- (c) Raise the cap (e.g., to 6) and keep the 8 Gi limit if the operator's workload has grown.

This is a manual decision phase, not a precommitted code change.

### Phase 6 — Track B2/B3 + regression cross-check

File three tracking issues (no implementation in this plan):

- **B2** — `agents`: delegate `claude`/`npm`/`node` spawn to the `kali` sibling container. Triggers when B1 + housekeeping prove insufficient at the operator's growth trajectory, or when per-session OS-level isolation becomes necessary for security work. Acceptance criterion gates: cap=4 still drives 2+ OOMKills/month, *or* explicit isolation requirement.
- **B3** — `agents`: per-task Kubernetes Jobs. Triggers at ≥10 sustained concurrent sessions or when per-task GPU/network policy becomes desirable. Acceptance criterion: B1 cap pushed to 8 and queue p99 > 1 sustained for 7 days.
- **R** — `agents`: investigate the 9× OOM-rate escalation observed on image `dc414b4` (Phase 2 retake) vs. `d3bbcd70…` (Phase 1). Compare the two binaries' working-set behavior under identical synthetic workload. Important because if it is a vibe-kanban regression, B1 is treating a symptom of an unrelated bug.

These are filed in `derio-net/frank` (not agent-images) so they land in the Derio Ops board with the cluster-side context. R may be reassigned to agent-images during triage.

## Components

```
┌─────────────────────────────────┐  ┌──────────────────────────────────┐
│  derio-net/agent-images         │  │  derio-net/frank                 │
├─────────────────────────────────┤  ├──────────────────────────────────┤
│  vibe-kanban fork (Phase 4)     │  │  apps/secure-agent-pod/          │
│   • config schema v8 → v9       │  │   manifests/deployment.yaml      │
│   • semaphore + queue           │  │   ├ memory.limits: 8Gi (PR #142) │
│   • /metrics endpoint           │  │   ├ VK_MAX_CONCURRENT_EXECUTIONS │
│   • structured logs             │  │   └ (Phase 5) optional dial-back │
│                                 │  │                                  │
│  vk-local image (Phase 3)       │  │  apps/victoria-metrics/          │
│   • npm cache prune cron        │  │   values.yaml (Phase 2)          │
│   • git worktree prune cron     │  │   └ relabel/limit fix            │
│                                 │  │                                  │
│  cross-repo: bumper PR moves    │  │  apps/secure-agent-pod/          │
│  the new image SHA into Frank   │  │   manifests/vmpodscrape.yaml     │
│                                 │  │   (Phase 4 — new file)           │
└─────────────────────────────────┘  └──────────────────────────────────┘
```

## Risks and trade-offs

- **Cap=4 may surprise operators who run >4 sessions.** Queueing (vs. rejecting) keeps the UX intact — sessions just take longer to start under load. The structured log makes it diagnosable.
- **Schema bump v8 → v9 must be backwards-compatible.** Existing config files without the new field default to `None` (unbounded). Verified by treating the field as `Option<usize>`.
- **Cadvisor fix is investigative.** Phase 2's three-cause hypothesis may all be wrong; the phase budget includes a fallback to file a tracking issue if the root cause cannot be isolated within ~1 day of investigation. The plan does not block on it — Phases 3 and 4 can proceed without metrics, just with reduced verifiability.
- **Housekeeping cron failure is silent today.** No alerting on cron success. The operator-side mitigation is to inspect `last-modified` of the npm cache periodically; long-term this should fold into a future "agent-pod health" dashboard, out of scope here.
- **No `/metrics` endpoint until Phase 4 ships.** Until then, B1 efficacy must be inferred from cadvisor RSS + structured logs.

## Open questions

These should be resolved during plan writing or first-task execution; they do not block design approval.

1. Where does the housekeeping cron live — inside `vk-local` (own image, no supercronic today), inside `kali` (has supercronic, but PVC-shared filesystem makes mutation safe across containers), or as a `CronJob` in Kubernetes (most observable, but adds a third pod to the agent surface)? Default: inside `kali` via supercronic, since it already runs scheduled work and shares the PVC.
2. What is the canonical place for the new `/metrics` endpoint route in vibe-kanban — alongside `/api/health` (port 8081) or on a separate diagnostic port? Default: `/metrics` on 8081, scraped via `VMPodScrape` with `path: /metrics`.
3. Should the B1 cap default to `None` (no cap) or `4` in the binary? Default: `None`, so existing uses outside Frank are unchanged. Frank pins it to `4` via env var.

## Cross-references

- [`agent-images:docs/superpowers/plans/2026-04-22-vk-local-memory-profile.md`](https://github.com/derio-net/agent-images/blob/main/docs/superpowers/plans/2026-04-22-vk-local-memory-profile.md) — original profiling investigation
- [`agent-images:kali/docs/findings/2026-04-22-vk-local-memory-profile.md`](https://github.com/derio-net/agent-images/blob/main/kali/docs/findings/2026-04-22-vk-local-memory-profile.md) — measured numbers and recommendations (cited throughout this spec)
- [`derio-net/agent-images#21`](https://github.com/derio-net/agent-images/pull/21) — profiling work merged
- [`derio-net/frank#142`](https://github.com/derio-net/frank/pull/142) — Option A landed (2 Gi → 8 Gi limit bump)
- [`derio-net/frank#140`](https://github.com/derio-net/frank/issues/140) — this brainstorm tracking issue
- [`2026-04-15--agents--agent-images-and-vk-local-sidecar-design`](2026-04-15--agents--agent-images-and-vk-local-sidecar-design.md) — sidecar architecture this plan extends

## Implementation Plans

| Plan | Repo | File | Status | Depends on |
|------|------|------|--------|------------|
| vk-local OOMKill Remediation — Implementation Plan |  | `docs/superpowers/plans/2026-04-30--agents--vk-local-oom-remediation.md` | In Progress | — |
