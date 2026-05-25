# Design: Blog Traffic Surge Detector — False-Positive Fix

**Date:** 2026-05-25
**Layer:** `obs` (fix/extension of the edge-observability layer — `ai-alert-helper`)
**Status:** Draft
**App(s):** `apps/ai-alert-helper`, `apps/blackbox-exporter`

## Problem

On 2026-05-25 the `ai-alert-helper` `surge-check` CronJob fired an **URGENT**
"Blog traffic surge" Telegram alert. GoatCounter (`counter.cluster.derio.net`)
showed no human activity. Investigation (read-only) established that *both
signals were correct* — they measure different things — and that the URGENT
was a false positive produced by two compounding bugs plus a missing safeguard.

### Evidence

The firing `surge-check` pod computed `current: 370, baseline: 1,
ratio: 370.0, tier: Major`. Breaking the 16:00–17:00 UTC edge window down by
source (VictoriaLogs, Caddy access logs, `request.host:"blog.derio.net"`):

| Requests | Source | Notes |
|---|---|---|
| 360 | `77.12.102.149` · `Blackbox Exporter/0.25.0` | Frank's **own** uptime probe (`GET /` → 301 → `/frank/`, ~every 10s) |
| 8 | `CensysInspect/1.1` | Internet-wide scanner (background noise) |
| 2 | `TelegramBot` | Link-preview fetch |

All requests were `GET`; there was no human browser traffic. GoatCounter only
counts JS-beacon pageviews from real browsers, so it correctly showed nothing.

The hour-of-day baseline samples for 16:00–17:00 over the prior 7 days were
`[373, 0, 0, 0, 0, 0, 0]` (the probe only began reaching the blog edge ~05-24).

### Root causes

1. **Baseline forced to `1`.** `surge.py:35` does
   `baseline = int(median(historical)) or 1`. The median of the samples above
   is `0`, forced to `1` to avoid divide-by-zero, so `ratio = 370 / 1 = 370×`.
   On a low-traffic blog whose hour-of-day median is 0, the "10× baseline" rule
   degenerates into "≥10 absolute requests in an hour".

2. **Frank's own uptime probe counts as blog traffic.** Neither
   `surge._hour_count` nor `facts.build_for_digest` excludes the Blackbox probe,
   so a `360 req/hour` internal monitoring probe (`apps/blackbox-exporter`,
   target `https://blog.derio.net`) reads as external blog traffic.

3. **The documented GoatCounter cross-check was never implemented.**
   `surge.py`'s docstring and `test_compute_returns_major_when_10x_baseline`
   ("*caller will then validate visitor side*") both state that a Major tier
   must be confirmed against GoatCounter before sending an URGENT message.
   `api.py:/surge-check` sends `urgent=(s["tier"] == "Major")` and never calls
   GoatCounter; `facts.build_for_surge` does not query it. The gate that was
   meant to suppress exactly this "bots spiked the edge, no humans came" case
   does not exist in the code path.

Because the CronJob runs every 15 minutes against the same baseline, the URGENT
re-fires ~4×/hour until the trailing-7-day hour-of-day median absorbs the probe
(~3 days) — i.e. a sustained false-page storm.

## Goals

- Frank must not page on its own uptime probe.
- An URGENT page must require visitor-side confirmation (real humans), with a
  safe behaviour when GoatCounter is unreachable.
- A baseline forced to `1` must not be able to manufacture a high ratio from a
  trickle of requests.
- "Blog traffic" must mean the same thing in the surge alert and the daily
  digest.

## Non-goals (YAGNI)

- **No alert de-duplication / cooldown layer.** The 15-min repeat storm is
  eliminated at the source (probe excluded → `current` near 0 → no tier), so a
  cooldown is unnecessary now. Noted as a possible future enhancement only.
- **No new app and no metrics-based rearchitecture.** The fix stays in the
  existing `obs` apps and the working LogsQL path. (Rejected alternatives:
  dropping probe logs at ingestion — destroys logs we want and mutates a shared
  pipeline; re-basing surge detection on VictoriaMetrics — a rearchitecture when
  the real human signal is GoatCounter anyway.)
- **No spoof-resistant/secret probe identity.** The custom UA is for
  disambiguation, not as a security control.

## Design

### Component 1 — Probe identity (`apps/blackbox-exporter`)

Tag Frank's own uptime probes with a self-controlled User-Agent so the edge
definition can exclude *Frank's probe identity* rather than the vendor's
default UA (which would wrongly whitelist any third-party blackbox_exporter or
spoofer). Confirmed supported: blackbox_exporter's `http` module accepts a
`headers:` map and `User-Agent` is overridable (verified against upstream
`CONFIGURATION.md`; 0.25.0 supports it).

Add to the **shared** `http_2xx` (and `http_2xx_no_redirect`) module in
`apps/blackbox-exporter/manifests/configmap.yaml`:

```yaml
http:
  headers:
    User-Agent: "Frank-Blackbox-Probe/1.0 (+https://blog.derio.net)"
```

All Frank uptime probes (blog, paperclip, grafana, n8n, health-bridge) then
carry one consistent Frank identity. They are all internal/own services, so
nothing downstream depends on the previous UA. A dedicated blog-only module was
considered and rejected (more config, no benefit).

### Component 2 — Centralized probe-aware edge filter (`facts.py`)

The edge query string is currently built in two places with no probe
exclusion. Introduce one helper as the single source of truth so the surge
alert and the digest can never silently disagree about what "blog traffic" is:

```python
# facts.py
PROBE_UA_TOKEN = "Frank-Blackbox-Probe"   # MUST match the UA in
                                          # apps/blackbox-exporter/manifests/configmap.yaml

def edge_filter(host: str | None = None, *, exclude_probes: bool = True) -> str:
    f = 'kubernetes.host:hop-1 AND _msg:"handled request"'
    if host:
        f += f' AND request.host:"{host}"'
    if exclude_probes:
        f += f' AND -request.headers.User-Agent:"{PROBE_UA_TOKEN}"'
    return f
```

`surge._hour_count` and `facts.build_for_digest` both call `edge_filter(...)`.
The exact LogsQL negation syntax for the hyphenated field name
(`-request.headers.User-Agent:"..."` vs. backtick-quoting) is **pinned by a
test** before we rely on it — that field returned a 422 during investigation
when mis-quoted.

### Component 3 — Absolute floor (`surge.py`)

Add a floor so a baseline of `1` cannot produce a high ratio from a trickle.
Applies to all tiers (a sub-floor "5× of 5 requests" Notable is also noise):

```python
ABS_FLOOR = int(os.environ.get("SURGE_ABS_FLOOR", "50"))
...
if current < ABS_FLOOR:
    tier = None
elif ratio >= 10:
    tier = "Major"
elif ratio >= 3:
    tier = "Notable"
```

Default **50 req/hour**: organic surges (HN/Reddit) run into the hundreds/hour,
so 50 sits well below a real event while killing the trickle-ratio artifact.
The floor is computed on probe-free traffic (Component 2), so Frank's ~360/hr
probe no longer contributes to it.

### Component 4 — GoatCounter cross-check (`api.py` `/surge-check`, `facts.py`)

Implement the missing visitor-side gate.

**4a. Distinguish unreachable from genuinely-zero.** `_goatcounter` currently
returns `{}` on both error and empty result. Add a reachability signal (return
`None` on transport/HTTP error; a dict — possibly empty — on success) so
fail-open can be implemented correctly. Add a `facts.surge_visitor_pageviews(
window_start, window_end) -> int | None` helper returning human pageviews for
the surge window (`None` = GoatCounter unreachable).

**4b. Final-severity decision in `/surge-check`** after `surge.compute()`
returns a non-`None` tier:

| Edge tier | GoatCounter result | Action |
|---|---|---|
| Major | pageviews ≥ `VISITOR_FLOOR` (dflt 10) | **URGENT** — confirmed real surge |
| Major | unreachable (`None`) | **URGENT**, narrative annotated *"visitor data unavailable"* (fail-open) |
| Major | pageviews < `VISITOR_FLOOR` | **downgrade → Notable** (non-urgent): "edge surge, no visitor confirmation — likely automated" |
| Notable | (any) | non-urgent message as today |

`VISITOR_FLOOR` default 10, env `SURGE_VISITOR_FLOOR`. The surge fact sheet
(`build_for_surge`) is extended to include the visitor pageview count (and its
reachability state) so the AI narrative reflects the real situation instead of
guessing. Today's incident outcome under this design: probe excluded →
`current` near 0 → below `ABS_FLOOR` → **no message at all**.

**Open item to verify in implementation:** whether GoatCounter's
`/api/v0/stats/total` accepts hour-granularity timestamps (the existing digest
code uses day granularity only). If hour granularity is unsupported, fall back
to "today's running pageviews" as the human signal (coarser but functional);
the plan records which path was taken.

### Digest consistency

`facts.build_for_digest` switches its edge queries to `edge_filter(...)` so the
digest's `edge_requests_total` and per-vhost breakdown exclude Frank's probe,
matching the surge definition. (The probe is ~8.6k req/day, so the digest's
edge totals currently overcount substantially.)

## Configuration (env, with defaults)

| Var | Default | Meaning |
|---|---|---|
| `SURGE_ABS_FLOOR` | `50` | Minimum `current` req/hour for any tier |
| `SURGE_VISITOR_FLOOR` | `10` | Minimum GoatCounter pageviews in window to confirm a Major as a real (URGENT) surge |

Both set on the `surge-check` CronJob (and where relevant the deployment) in
`apps/ai-alert-helper/manifests/`.

## Testing

- `edge_filter`: probe exclusion present/absent, host scoping, and the exact
  LogsQL negation string (regression guard for the 422).
- `PROBE_UA_TOKEN`: a test pinning the exact token string the filter expects
  (drift between the two systems fails CI).
- `surge.compute`: floor suppresses tier when `current < ABS_FLOOR`; existing
  ratio/tier tests updated for the floor.
- `/surge-check` decision matrix: each row of the Component-4b table
  (mock GoatCounter ≥floor, <floor, and unreachable/`None`).
- `_goatcounter` / `surge_visitor_pageviews`: error → `None`, success-empty →
  `0`, success → integer.

## Deployment & verification (ordering matters)

1. Deploy the blackbox UA change (`apps/blackbox-exporter`). ArgoCD sync +
   blackbox config reload.
2. **Verify in live Caddy logs** that probe requests to `blog.derio.net` now
   carry `Frank-Blackbox-Probe` (VictoriaLogs query). The exact-match exclusion
   filter is only trustworthy once this is confirmed — flipping the filter
   before the probe's live UA changes would silently re-introduce the false
   page.
3. Deploy the `ai-alert-helper` image + manifest changes.
4. **End-to-end verification:** trigger `/surge-check` (or wait for the
   CronJob) and confirm `current` for the blog window is now probe-free and
   below `ABS_FLOOR` → no URGENT. Confirm a forced Major path (e.g. temporary
   low `SURGE_ABS_FLOOR` or synthetic load) exercises the GoatCounter gate.
   A layer is not "Deployed" until the workflow is observed end-to-end.

## Layer-fix follow-ups (per repo workflow)

- **Plan deviation note** in the obs edge-observability plan (locate exact file
  during planning) — root cause + fix summary.
- **Operating post** (`obs` / inference-adjacent operating series): add a
  "tuning the surge detector" section (env knobs, how to read a surge alert,
  this incident as a worked example). Retroactive update, not a new post.
- **Gotchas:** one-liners in `agents/rules/frank-gotchas.md` (the
  baseline-of-1 ratio artifact; Frank's own probe counting as blog traffic;
  surge URGENT requires the GoatCounter gate) + full prose in
  `docs/runbooks/frank-gotchas/obs-digest.md`.

## Risks

- **Cross-system UA coupling** (blackbox config ↔ `PROBE_UA_TOKEN`): guarded by
  a pinning test, cross-referencing comments in both files, and the live-log
  verification step.
- **Floor too high** masks a genuinely small surge: mitigated by env-tunability
  and the GoatCounter gate (a real surge with humans still pages once it clears
  the floor).
- **GoatCounter API granularity** (open item above): fallback defined.
