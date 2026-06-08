# health-bridge — blindness ≠ death

## Why this plan exists

A power outage on 2026-06-08 took the whole cluster down. On recovery Grafana's
datasource was briefly unreachable, so it fired its built-in `DatasourceError`
alert. Because the affected alert rules carry `github_issue` labels, the
`DatasourceError` instances inherited them across ~10 layers. health-bridge did
exactly what it was told: it marked those layers `dead`/`degraded` on the Derio
Ops board and opened 5 bug issues, all titled `[Bug] DatasourceError is dead`,
every summary reading `[no value]` — because the alert templates couldn't read
their own data through the broken datasource.

Then Grafana was rescheduled onto a fresh pod. A new Grafana process has no
memory of the `DatasourceError` instances the old pod fired, so the `resolved`
that would have healed everything never came. The board stayed red; the bugs
stranded. A second defect made it worse: auto-close matches bugs by *alertname*,
so even the real per-rule resolves that *did* arrive (e.g. `Layer 18 …`) could
never close a `DatasourceError`-titled bug.

The incident was cleaned up by hand with a synthetic-resolve replay. This plan
makes sure it never strands again.

## The fix, in one sentence

Stop treating "monitoring went blind" as "the layer died," and make recovery
close bugs by *which layer they belong to* rather than *which alert named them*.

- **Source fix:** `DatasourceError`/`NoData` firing ⇒ cap at `degraded`, create
  no bug. Blindness is degraded visibility, not death.
- **Safety net:** when a tracker returns to `healthy`, close any open bug for
  that tracker (matched on the body feature ref alone, alertname-agnostic) — so
  a future alertname mismatch can't strand a bug either.

Creation still dedups on alertname, so two genuinely different real alerts on
one tracker still each get their own bug.

## Shape

Four phases, linear. Code + tests + PR in the `derio-net/health-bridge` repo
(TDD, tests first); then tag/release `v0.4.0` (verifying the tag tree carries
the new symbols before trusting the build — the v0.3.0 stale-tag lesson); then
the frank-side image bump + retroactive Layer 23/16 blog updates + a gotcha;
then deploy verification with an end-to-end cross-alertname heal smoke test,
because a layer isn't "Deployed" until its workflow has actually been observed.

Full design, root-cause analysis, and test matrix live in the spec:
`docs/superpowers/specs/2026-06-08--obs--health-bridge-blind-state-design.md`.
