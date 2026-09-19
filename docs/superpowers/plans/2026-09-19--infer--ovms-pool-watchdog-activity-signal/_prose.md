The downstream consumer reported that `ovms-pool-watchdog` replaced the
`ovms-retrieval` pod six times in 22 minutes and killed a batch-index job, and
attributed it to Rule 1 — the OOM-safety rule, whose cost model is the most
heavily commented thing in the manifest.

**The logs say Rule 1 never fired.** All five restarts in the window were
`reason=idle-with-elevated-pool`, which is Rule 2, the hygiene rule. Rule 1's
highest reading was 48.4% against a 50% trigger. The well-documented rule
attracted the blame; the quiet one did it.

So this plan is smaller than the issue asks for, and aimed elsewhere.

## What it fixes

**Root cause A — `busy` measures the CPU, and the work is on the GPU.** The
ticks that restarted the pod read 5, 29, 41 and 5 millicores against a 50
millicore threshold, while `shmem` climbed 5.10 → 7.24 → 8.31 GiB across those
very ticks. No value of `BUSY_MILLICORES` separates "indexing" from "asleep" on
a GPU-offloaded server. It is replaced by OVMS's own metrics.

**Root cause B — the idle clock survives the restart it triggers.**
`pool-watchdog-last-busy` lives on the Deployment, `rollout restart` does not
touch it, and it advances only on a positive `busy` sample. Once A pinned
`busy=no`, every subsequent tick computed a stale `idle_for` and restarted
again: four restarts in six minutes. A restart now stamps the clock, which
bounds hygiene restarts to one per `IDLE_SECONDS` no matter how wrong the
activity signal is.

**A third defect, found while measuring.** Rule 1 compares `shmem` against
`memory.max`; the kernel compares `memory.current`. Measured live at baseline
those differ by ~25%, which is comfortably the distance between the watchdog's
48.4% and the "68% with no action" the issue files as unexplained.

## The near-miss that shaped the plan

The first draft of the spec chose `ovms_requests_success` as the activity
counter, on the strength of this repo's own gotchas file recommending it.
Measurement says that series counts the **readiness probe** — over 12 idle
seconds it was the only series that moved — while real `/v3` traffic reports
through `ovms_requests_accepted` and `ovms_responses`.

Shipping it would have made `busy` read yes on every tick forever, silently
disabling Rule 2 with no symptom until the ceiling: a failure in the opposite
direction to the one being fixed, and a quieter one. `P1.T3` exists to make that
specific mistake impossible to reintroduce, and Test Plan row 2 is its live
counterpart.

The same wrong series is what `agents/rules/frank-gotchas.md` tells a future
reader to use to answer "is the retrieval tier being used at all?", so Phase 5
corrects it in all three places it appears. That is why a documentation phase is
in a bugfix plan: the documentation asserts the thing this work just disproved.

## Shape

Phase 1 is the walking skeleton and carries most of the risk — it replaces the
signal, using fixtures captured from the live server rather than hand-written
metrics text. Phases 2 and 3 are independent hardening on top of it. Phase 4
makes a recurrence visible, because nothing paged during five restarts; the
incident was found by the consumer noticing its job had died. Phase 5 is the
documentation. Phase 6 is the operator-driven Test Plan, back-loaded — nothing
agentic depends on it.

Every behavioural test runs offline against the committed fixtures and the
extracted inline script. `.github/workflows/repo-tripwires.yml` runs
`pytest scripts/tests/ -q` on every PR and nothing in that suite may talk to a
cluster.

## Deliberately not done

No suppression lease, no busy-aware Rule 1, no client-side resumability — the
issue's three directions, all declined, because all three soften or work around
a rule that was not involved. If Rule 1 does start firing during indexes once it
measures `memory.current`, that is a real signal about the ceiling and the
moment to revisit direction 2 with the transient headroom measured. Not before.
