# OVMS pool watchdog — measure activity, not CPU; and never restart in a loop

**Date:** 2026-09-19
**Layer:** `infer` (11) — Local Inference
**Status:** Designed
**Prompted by:** `derio-net/frank` issue #813, a follow-on to #805 (the watchdog) and #793 (the batch guard)
**Repos:** `derio-net/frank` only

`ovms-pool-watchdog` replaced the `ovms-retrieval` pod five times in sixteen
minutes during a downstream batch-index run and killed the job at batch 7 of 40.
The issue attributes this to Rule 1, the OOM-safety rule, and proposes three
ways to soften its cost model.

**The logs say Rule 1 never fired.** This spec is therefore mostly a correction,
and the fix it describes is smaller and more mechanical than the one #813 asks
for.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-09-19--infer--ovms-pool-watchdog-activity-signal | `derio-net/frank` | `2026-09-19--infer--ovms-pool-watchdog-activity-signal` | — |

## What actually happened

Every `pool-watchdog result:` line is in VictoriaLogs. Queried over the incident
window (`kubernetes.namespace_name:retrieval AND _msg:"pool-watchdog result"`,
2026-09-19 18:50Z–21:40Z), the decisions were:

```
18:52:12 action=none    reason=busy                     shmem=2958548992 millicores=398
18:54:12 action=none    reason=busy                     shmem=3423854592 millicores=559
18:56:12 action=none    reason=idle-too-recent          shmem=6641278976 idle_for=120
   ... 14 ticks, shmem byte-identical, idle_for climbing exactly 120/tick ...
19:24:12 action=none    reason=idle-too-recent          shmem=6641278976 idle_for=1799
19:26:12 action=restart reason=idle-with-elevated-pool  shmem=6641278976 millicores=4
19:28:12 action=none    reason=pool-at-baseline         shmem=1836507136
   ... pool refills ...
19:36:12 action=restart reason=idle-with-elevated-pool  shmem=5104066560 millicores=5
19:38:12 action=restart reason=idle-with-elevated-pool  shmem=7238967296 millicores=29
19:40:12 action=restart reason=idle-with-elevated-pool  shmem=8313102336 millicores=41
19:42:12 action=restart reason=idle-with-elevated-pool  shmem=4089765888 millicores=5
19:44:12 action=none    reason=pool-at-baseline         shmem=1842733056
```

Five restarts, **all of them `idle-with-elevated-pool` — Rule 2, the hygiene
rule.** `critical-pool` does not appear anywhere in the window. The highest
reading Rule 1 ever saw was 8313102336 bytes, 48.4% of the 16Gi limit, against
a 50% trigger. It came within 1.6 percentage points and did not fire.

So the three directions in #813 — a suppression lease, a busy-aware Rule 1, a
resumable client — all address a rule that was not involved.

### Root cause A — `busy` measures the CPU; the work is on the GPU

`busy` is derived from a 10-second `cpu.stat` delta against
`BUSY_MILLICORES=50`. During the batch index the same ticks that restarted the
pod read **5, 29, 41 and 5 millicores**. The server was demonstrably working —
`shmem` climbed 5.10 → 7.24 → 8.31 GiB across those very ticks — while the CPU
sampler called it idle.

That is not a threshold that needs tuning. OpenVINO offloads inference to the
iGPU, so a GPU-bound server's container CPU is near zero by construction, and
**no value of `BUSY_MILLICORES` separates "indexing" from "asleep"**. The two
readings of 398 and 559 millicores at 18:52/18:54 came from short high-rate
benchmark traffic, which is tokenizer-heavy on the CPU — so the signal works for
exactly the workload that was used to validate it, and fails for the one that
matters here.

### Root cause B — the idle clock survives the restart, so one miss becomes a loop

`pool-watchdog-last-busy` lives on the **Deployment**, and `rollout restart`
does not touch it. It advances only on a positive `busy` sample. Once Root
Cause A pinned `busy=no`, the clock froze at its 18:54 value and every
subsequent tick computed `idle_for` well past `IDLE_SECONDS=1800`.

The result is a machine with no rate limit: restart → pool refills within one or
two ticks → `shmem > ELEVATED_BYTES` → clock still stale → restart. Four
restarts in six minutes, one per tick, until the client gave up and the traffic
stopped.

**Root cause A is why it started. Root cause B is why it did not stop**, and B
is the more dangerous of the two, because it converts *any* future regression in
the activity signal into a restart loop rather than a single unnecessary restart.

### The "68% with no watchdog action" is a third, separate defect

#813 records the pool at 68% with no action and files it as unexplained. It is
explained, and not by a missed tick.

Rule 1 compares `memory.stat`'s `shmem` against `memory.max`. The kernel's OOM
killer compares **`memory.current`** against `memory.max`. Those are different
numbers: measured live on an idle pod at the time of writing,

```
shmem           1836507136   (1.71 GiB)
memory.current  2296066048   (2.14 GiB)
memory.peak     2376773632   (2.21 GiB)
```

`memory.current` is ~25% above `shmem` at baseline, because it also carries the
anonymous allocation (~0.55 GiB, recorded in the deployment comment). **Rule 1
under-measures its own trigger.** A consumer reading working-set or
`memory.current` and a watchdog reading `shmem` will disagree by roughly that
margin plus any live transient, which is comfortably the distance between the
watchdog's 48.4% and the reported 68%.

## What this changes

Three code changes and one alert. **Rule 1's cost model, thresholds and
comments are not touched** — it behaved correctly throughout and #813's premise
about it does not survive the logs.

### 1. Activity is measured from OVMS, not from the cgroup's CPU

OVMS has exposed its own metrics since #793/#809 (`--metrics_enable`). Which
series to use is **not** the obvious one, and getting it wrong fails silently in
the opposite direction, so it was measured rather than read off the docs.

Method: snapshot `/metrics`, do nothing for one probe interval, snapshot again
(control); then snapshot, fire one `/v3/embeddings` and one `/v3/rerank`,
snapshot again (treatment). Diff per series.

**Control — 12 seconds, no inference. Exactly one series moved:**

```
ovms_requests_success{api="KServe",interface="REST",method="ModelReady",name="bge-reranker-v2-m3"} 42 -> 44
```

**Treatment — one embeddings call and one rerank call, both HTTP 200:**

```
ovms_requests_accepted{api="V3",interface="REST",method="Unary",name="bge-m3"}              1 -> 2
ovms_requests_accepted{api="V3",interface="REST",method="Unary",name="bge-reranker-v2-m3"}  0 -> 1
ovms_responses{api="V3",interface="REST",method="Unary",name="bge-m3"}                      1 -> 2
ovms_responses{api="V3",interface="REST",method="Unary",name="bge-reranker-v2-m3"}          0 -> 1
ovms_graph_processing_time_us_count{method="Unary",name="bge-m3"}                           1 -> 2
ovms_requests_success{api="KServe",interface="REST",method="ModelReady",...}               45 -> 46   <- probe again
```

So, flatly:

| Series | Moves on `/v3` inference | Moves on the readiness probe |
|---|---|---|
| `ovms_requests_success` | **no** | **yes**, ~1 per 10s, forever |
| `ovms_requests_accepted` | yes | no — it has no `ModelReady` series at all |
| `ovms_requests_rejected` | yes (the #793 guard's 400 path) | no |
| `ovms_responses` | yes | no |
| `ovms_current_graphs` | yes (gauge) | no |

`ovms_requests_success` is the series a first draft of this spec chose, on the
strength of the repo's own gotchas file recommending it. **It counts the
readiness probe.** Had it shipped, `busy` would have read `yes` on every tick
forever — Rule 2 silently disabled, the pool never reclaimed, and no symptom
until the ceiling. That is a bug in the opposite direction to the one being
fixed, and strictly worse: the current bug is loud.

The determination is therefore:

```
activity = sum(ovms_requests_accepted) + sum(ovms_requests_rejected)

busy = (sum(ovms_current_graphs) > 0)      # a request is in flight right now
    OR (activity > last_activity)          # a request arrived since the last tick
```

with `last_activity` stamped on the Deployment as
`retrieval.derio.net/pool-watchdog-last-activity`.

`accepted` counts requests entering the graph and `rejected` counts those the
batch guard refuses; summing both means **a client being refused still counts as
a client**, which is right — restarting the server under a caller that is
actively being told "no" is gratuitous, and the pool is not growing anyway.
Neither series carries a `ModelReady` variant, so no probe filtering is needed
and none is done: a filter is a thing that can be got wrong later.

The counter term is the important half. The gauge only sees the two instants the
watchdog samples; the counter delta covers the **entire two-minute interval
between ticks**, so a batch job with gaps between batches — the exact shape that
defeated the 10-second CPU window — cannot slip through.

Verified live that the gauge tracks in-flight work, by polling it alongside one
request:

```
t=1  graphs=1   <- request in flight
t=2  graphs=1
     http=200 t=0.61
t=3  graphs=0   <- returned
```

Both states captured as fixtures from the live server —
`scripts/tests/fixtures/ovms-retrieval/metrics-idle.txt` (both models at 0) and
`metrics-busy.txt` (`bge-m3` at 1 with a request in flight).

**The CPU sample and its `sleep 10` are removed entirely**, not kept as a
fallback. A signal proven blind to the workload under discussion is not a safety
net; retaining it would only restore the false confidence that produced this
incident. The tick also gets ~10 seconds shorter as a side effect.

**Counter resets.** A restarted pod serves `activity` from zero, which is less
than the stamped value. That is a counter reset, not idleness: the script
detects `activity < last_activity`, treats the tick as busy, and re-stamps. Standard counter-reset handling; without it, the first requests after
every restart would read as idle — reintroducing root cause A through the back
door.

**Unreadable `/metrics` fails toward busy.** If the scrape fails, the tick logs
`reason=metrics-unreadable` and takes no hygiene action. Rule 1 does not consult
`busy` and so remains fully armed; the cost of failing this way is an elevated
pool that is not reclaimed, which is strictly the lesser harm.

### 2. A restart stamps the idle clock

`restart()` stamps `pool-watchdog-last-busy = now` alongside the `rollout
restart`. Both rules' restarts do this.

The reasoning is that `IDLE_SECONDS` asks "how long since the server was last
known to be doing something", and **a restart invalidates every prior
observation** — the process it was observing no longer exists. Measuring from
the restart is what the annotation already means.

Its value is that it bounds the failure. Even with the activity signal wrong in
every possible way, hygiene restarts become **at most one per `IDLE_SECONDS`**
(30 minutes) instead of one per tick. Root cause B stops being expressible.

### 3. Rule 1 compares `memory.current`, not `shmem`

The numerator becomes `memory.current`, matching the quantity `memory.max`
actually bounds. `shmem` stays in the log line — it is the pool figure the whole
design reasons about — and `current=` joins it.

`ELEVATED_BYTES` (Rule 2) keeps using `shmem` deliberately. Rule 2 asks "is the
**GPU pool** above its post-boot baseline", which is a `shmem` question. Rule 1
asks "are we near the ceiling the kernel kills at", which is a `memory.current`
question. They are different questions and should not share a numerator.

**The percentage moves with the numerator.** `CRITICAL_PERCENT=50` was
calibrated against `shmem` readings, and `memory.current` runs a roughly
*constant* ~0.5 GiB higher (live: shmem 1.72 GiB, anon 0.50, kernel 0.01,
current 2.22 — none of it reclaimable with swap off, which is exactly why the
numerator change is right). Carrying 50 across unchanged would tighten the
trigger by ~3.1 points of the limit with nobody deciding to.

Checked against the incident: peak `shmem` 8313102336 (7.74 GiB) sat under the
8.00 GiB line, but the same moment as `memory.current` is **8.17 GiB — over it
by 174 MiB**. Rule 1 would have killed the batch index that Rule 2 killed, and
Test Plan row 5 would fail for a new reason. So `CRITICAL_PERCENT` becomes
**53** (8.48 GiB of `memory.current` ≈ 7.98 GiB of `shmem`): the measurement
becomes honest, the trigger stays where it was actually calibrated. Guarded in
both directions — a further raise is a new threshold and needs its own
measurement.

`memory.peak` was considered and rejected for now: it would catch the 0.1–2.5s
transients a two-minute tick can never sample, but peak runs ≈ settled + ~2 GiB,
so at an unchanged `CRITICAL_PERCENT=50` it would fire Rule 1 during every
normal index — turning a spec that exists to stop spurious restarts into one
that causes them. It is only viable paired with a re-measured ceiling, which
#813 correctly notes must be measured and not extrapolated.

### 4. The loop becomes visible

Nothing paged during five restarts in sixteen minutes. It was found by the
downstream consumer noticing its job had died.

A new `feature-health` rule, `ovms-pool-watchdog-restart-loop`, counts
`action=restart` lines over 30 minutes and fires above 2. After change (2) the
design bound is one hygiene restart per 30 minutes, so three is unambiguous.

Two details that are load-bearing rather than stylistic:

- **`noDataState: OK`.** The query filters; zero matches returns no rows, not a
  zero, so the rule resolves *through* NoData. `Alerting` here would make it
  unable to ever stop firing.
- **`_msg:`, not `log:`.** Frank's VictoriaLogs message field is `_msg`. Hop's
  CrowdSec rules use `log:` and copying that shape to Frank returns zero
  forever. Validated against the live endpoint while writing this spec: the
  `stats_query` above returns a populated vector.

**Routing, corrected during implementation.** An earlier draft of this section
said health-bridge only. That is not what `severity: warning` does here: the
Telegram route in `notification-policy-cm.yaml` matches severity BEFORE the
`grafana_folder="feature-health"` route and carries `continue: true`, so the
alert reaches Telegram *and* health-bridge. Health-bridge-only would require an
explicit `health_bridge_only="true"` label, which four rules in the folder
carry and this one deliberately does not — 22 of the folder's 49 rules are
warning-with-no-label, and the whole reason this rule exists is that five
restarts in sixteen minutes paged nobody.

### 5. The repo's own "is the tier being used?" query is corrected

The same measurement disproves a recommendation this repo currently makes in
three places — `agents/rules/frank-gotchas.md`,
`docs/runbooks/frank-gotchas/igpu-dra.md`, and the `--metrics_enable` comment in
`apps/ovms-retrieval/manifests/deployment.yaml`:

> ask `sum by (name) (increase(ovms_requests_success[1d]))`, do not infer from
> CPU/memory graphs

That query answers with **readiness-probe traffic**. `readinessProbe` hits
`/v2/models/bge-reranker-v2-m3/ready` every 10s, so the reranker accrues ~8,600
`ovms_requests_success` per day whether or not a single client exists; `bge-m3`'s
only entry came from the `startupProbe` and then stopped, so the embeddings
model reads ~0 **however much real traffic it serves**. The query invents usage
for one model and hides it for the other.

It is corrected to `sum by (name) (increase(ovms_requests_accepted[1d]))` in all
three places, with a line recording why the obvious series is wrong.

This is in scope because it is the same defect: both the watchdog and the
gotcha reached for `ovms_requests_success` because it is the plausibly-named
series, and neither had measured it. Leaving the documentation asserting the
thing this work just disproved would guarantee the next reader repeats it. It is
also *why* a four-day post-#793 silence was hard to interpret: the query
available to interpret it was measuring probes.

## What this deliberately does not do

- **No suppression lease** (#813 direction 1). With activity measured correctly,
  Rule 2 cannot fire during an index, and Rule 1 — which a lease would suppress
  — was never the problem. A lease is a permanent hole in the OOM protection
  bought to solve a problem that no longer exists.
- **No busy-aware Rule 1** (#813 direction 2). Same reason. Its stated cost
  model ("an OOM costs the request plus ~10s of refused connections, which is
  strictly worse than a controlled 11s restart") is still the right trade for a
  rule whose job is to prevent an OOM, and nothing in the incident tests it.
- **No client-side resumability** (#813 direction 3). That is the consumer's
  repo, and it is the right thing for the consumer to want independently — but
  it is not frank's to ship, and it should not be the price of frank's watchdog
  being correct.

If Rule 1 does begin firing during indexes once it measures `memory.current`,
that is a real signal about the ceiling and is the moment to revisit direction 2
with the transient headroom measured. Not before.

## Test Plan (post-merge, operator-driven)

| # | Check | Pass |
|---|---|---|
| 1 | `kubectl -n argocd get application ovms-retrieval` after merge | `Synced`; and the live CronJob's script contains `ovms_current_graphs` — sync status is not proof the artifact changed |
| 2 | **Probe-noise regression.** Watch three consecutive ticks on an idle server — the readiness probe is still hitting it every 10s | Every tick reads NOT busy (`pool-at-baseline` / `idle-too-recent`). A `reason=busy` here means the activity counter picked up probe traffic and Rule 2 is disabled |
| 3 | **Synthetic replay.** Drive in-bounds `/v3/embeddings` requests paced with gaps, for ≥3 ticks (≥6 min), while container CPU stays under 50 millicores | Every tick logs `reason=busy`; **zero** `action=restart`; confirm CPU really was under 50m so the test proves the new signal and not a lucky CPU spike |
| 4 | Confirm the idle clock stamps on restart | After any `action=restart`, the next tick's `idle_for` is small (< one tick) rather than inherited |
| 5 | **The consumer re-runs the real 40-batch index** | Job completes; zero `action=restart` lines in the window |
| 6 | Rule 1 numerator | A log line carries both `shmem=` and `current=`, with `current` > `shmem` |
| 7 | The alert exists and resolves | Rule present in the `feature-health` folder; with no restarts in 30 min it reads Normal, not NoData-firing |
| 8 | The corrected usage query | `sum by (name) (increase(ovms_requests_accepted[1d]))` returns ~0 for both models on a genuinely idle day, where the old `ovms_requests_success` form returns thousands for `bge-reranker-v2-m3` |

Row 5 is the acceptance proof; rows 1–4 and 6–8 can be driven without the
consumer and should run first, since a failure in any of them means row 5 would
only re-break the consumer's job. **Row 2 is the one most worth not skipping** —
it is the only check that catches the failure this design came closest to
shipping, and an always-busy watchdog looks exactly like a healthy quiet one.
