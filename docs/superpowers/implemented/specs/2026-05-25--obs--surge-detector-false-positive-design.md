# Design: Blog Traffic Surge Detector — False-Positive Fix

**Date:** 2026-05-25
**Layer:** `obs` (fix/extension of the edge-observability layer — `ai-alert-helper`)
**Status:** Deployed
**App(s):** `apps/ai-alert-helper`, `apps/blackbox-exporter`

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-05-25--obs--surge-detector-fix | `derio-net/frank` | `docs/superpowers/plans/2026-05-25--obs--surge-detector-fix/` | — |
| 2026-05-25--obs--surge-detector-fix-rework-1 | `derio-net/frank` | `docs/superpowers/plans/2026-05-25--obs--surge-detector-fix-rework-1/` | 2026-05-25--obs--surge-detector-fix |

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

- **No alert de-duplication / cooldown layer.** The `surge-check` endpoint is
  stateless and re-evaluates every 15 minutes, so *any* sustained condition
  re-notifies while it persists — a confirmed human surge (URGENT) and a
  downgraded no-visitor bot surge (Notable) alike. This fix eliminates the
  **specific** storm that was reported (Frank's own probe → `current` near 0 →
  no tier), but it does not add general repeat-suppression. Genuine sustained
  surges re-notifying every 15 min is accepted for now; a cooldown/state layer
  is deferred and tracked as a follow-up (see Risks).
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

The edge query is currently built in **three** places with no probe exclusion
and *two different node/namespace selectors* — `surge._hour_count`
(`surge.py:18-21`, scoped `kubernetes.namespace_name:caddy-system`),
`facts.build_for_digest` (`facts.py:155`, scoped `kubernetes.host:hop-1`), and
`facts.build_for_surge` (`facts.py:180-181`, scoped
`kubernetes.namespace_name:caddy-system`, **no host filter at all**).
Introduce one helper as the single source of truth so the surge alert, the
surge narrative, and the digest can never silently disagree about what "blog
traffic" is, and canonicalize on **one** selector: `kubernetes.host:hop-1`
(the documented convention in `docs/runbooks/frank-gotchas/networking.md`).

```python
# facts.py
PROBE_UA_TOKEN = "Frank-Blackbox-Probe"   # MUST match the User-Agent set in
                                          # apps/blackbox-exporter/manifests/configmap.yaml
                                          # (cross-system coupling — see Risks)

def edge_filter(host: str | None = None, *, exclude_probes: bool = True) -> str:
    # Backtick-quote the dotted/hyphenated field names (verified live against
    # VictoriaLogs; phrase-matches the array-valued UA field correctly).
    f = 'kubernetes.host:hop-1 AND _msg:"handled request"'
    if host:
        f += f' AND `request.host`:"{host}"'
    if exclude_probes:
        f += f' AND -`request.headers.User-Agent`:"{PROBE_UA_TOKEN}"'
    return f
```

**All three** call sites are migrated to `edge_filter(...)`:
`surge._hour_count(host="blog.derio.net")`,
`build_for_surge` (`total_requests` → `edge_filter(host="blog.derio.net")`),
and `build_for_digest` (grouped/total edge queries → `edge_filter()` with no
host, i.e. all vhosts, probe-excluded). This also fixes `build_for_surge`
currently feeding the AI narrative an unfiltered, probe-polluted count.

**LogsQL syntax — verified live, not hand-waved.** Against VictoriaLogs for the
incident window (total 370, probe 360): every negation form
(`-request.headers.User-Agent:"..."`, backtick-quoted, and `NOT`) correctly
returned 10. The 422 seen during investigation was a missing `| stats` pipe,
not the field name. The future token `Frank-Blackbox-Probe` correctly excludes
nothing until the probe's live UA changes (confirming the deployment ordering
below). A `respx`-mocked unit test can only pin the *generated string*, so the
real query is also exercised by a **live** LogsQL check in the deployment
verification (not a substitute — an addition).

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
probe no longer contributes to it. **Boundary:** the comparison is
`current < ABS_FLOOR → tier None`, i.e. exactly `ABS_FLOOR` requests *does*
qualify (≥50 fires). The operating-post tuning section documents this.

### Component 4 — GoatCounter cross-check (`api.py` `/surge-check`, `facts.py`)

Implement the missing visitor-side gate.

**4a. Distinguish unreachable from genuinely-zero — WITHOUT breaking the
digest.** `_goatcounter` currently returns `{}` on both error and empty result,
and its only callers (`_digest_blog_facts`, `facts.py:91-96`) immediately
`.get(...)` the result. Changing `_goatcounter` to return `None` on error would
throw `AttributeError` and **crash the daily `/digest`** (unwrapped at
`api.py:29`). So the contract change is additive, not in-place:

- Introduce `_goatcounter_raw(path, params) -> dict | None` — `None` on
  transport/HTTP error, dict (possibly empty) on success.
- `_goatcounter` becomes `return _goatcounter_raw(...) or {}` — **digest
  behaviour and all existing call sites are unchanged.**
- New `facts.surge_visitor_pageviews(window_start, window_end) -> int | None`
  uses `_goatcounter_raw` against `/api/v0/stats/total`; returns the human
  pageview count, or `None` when GoatCounter is unreachable.

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

**GoatCounter window granularity — resolved.** GoatCounter's OpenAPI spec
(`/api.json`) defines `start`/`end` on the stats endpoints as `format:
date-time` ("*should be rounded to the hour*"), so the cross-check passes the
**exact 1-hour surge window** as RFC3339 timestamps — no day-granularity
fallback is needed (the earlier concern about midnight under-count / late-day
over-confirm does not arise). `_digest_blog_facts` keeps its existing whole-day
range for the daily digest; only the surge path uses the hour window.

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

Both set in the **Deployment**'s `env:` block
(`apps/ai-alert-helper/manifests/deployment.yaml`) — **not** the CronJobs. The
`surge-check` and `digest` CronJobs are pure `curlimages/curl` triggers that
`POST` to the Service; the Python (`surge.compute()`, `/surge-check`) runs only
in the Deployment pod, so that is the only place `os.environ.get(...)` reads.
Env on the CronJob would be silently ignored. Both have safe code defaults
(50 / 10) so unset is non-breaking.

## Testing

- `edge_filter`: probe exclusion present/absent, host scoping, and the exact
  backtick-quoted negation string the helper generates (string-shape guard).
  Note: this is a *generated-string* assertion only — it cannot validate the
  query against VictoriaLogs; that is covered by the live check in Deployment.
- `PROBE_UA_TOKEN`: a test pinning the exact token string the filter expects.
  This pins only the **Python side**; the blackbox configmap must carry an
  inline comment cross-referencing `facts.PROBE_UA_TOKEN` (a configmap edit
  can still silently desync — the only runtime signal would be a re-fired false
  page, so the cross-ref comment is the guard).
- `surge.compute`: floor suppresses tier when `current < ABS_FLOOR`; existing
  ratio/tier tests updated for the floor. **Split** the current
  `test_compute_handles_empty_baseline_without_divide_by_zero`
  (`test_surge.py:74-85`) into two tests — one for crash-safety on an empty
  baseline, one for the floor boundary (49 → None, 50 → fires) — so the two
  concerns aren't entangled at the boundary.
- `/surge-check` decision matrix: each row of the Component-4b table
  (mock GoatCounter ≥floor, <floor, and unreachable/`None`).
- `_goatcounter_raw` / `surge_visitor_pageviews`: error → `None`,
  success-empty → `0`, success → integer.
- **Digest regression (ties to C1):** `build_for_digest` must survive an
  unreachable GoatCounter — assert it returns a sheet (probe-excluded edge
  facts + zeroed blog facts) and does **not** raise, with `_goatcounter_raw`
  mocked to `None`.

## Deployment & verification (ordering matters)

1. Deploy the blackbox UA change (`apps/blackbox-exporter`). ArgoCD sync +
   blackbox config reload.
2. **Verify in live Caddy logs** (VictoriaLogs) that probe requests to
   `blog.derio.net` now carry `Frank-Blackbox-Probe`, then run the **exact
   `edge_filter` negation query live** and assert it (a) returns HTTP 200 (not
   422) and (b) excludes the probe count (blog total drops by ~probe volume).
   This is the integration check the mocked unit test cannot perform. The
   exclusion filter is only trustworthy once both pass — flipping the filter
   before the probe's live UA changes would silently re-introduce the false
   page (empirically confirmed: the `Frank-Blackbox-Probe` token excludes 0
   rows while the probe still sends the stock `Blackbox Exporter` UA).
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
  a Python-side pinning test, a cross-referencing comment in the blackbox
  configmap, and the live-log + live-query verification step. The remaining
  exposure is a configmap edit that desyncs without touching `facts.py` — its
  only runtime signal is a re-fired false page.
- **Floor too high** masks a genuinely small surge: mitigated by env-tunability
  and the GoatCounter gate (a real surge with humans still pages once it clears
  the floor).
- **Repeat notifications for sustained surges** (deferred follow-up): the
  stateless 15-min cadence re-notifies for any persistent surge — confirmed
  human (URGENT) or downgraded bot (Notable). This fix removes the *probe*
  storm but not this general property; a cooldown/state layer is out of scope
  (see Non-goals) and should be tracked as a future enhancement if sustained
  non-probe surges prove noisy in practice.
