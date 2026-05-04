# Terminal #3 — synthetic traffic driver

## My role this session

Drive ~1 req/sec at the LiteLLM LB (`192.168.55.206:4000`) so the
`AnalysisRun`'s `litellm_request_total` query has a non-empty denominator,
and shout on any non-200. Started on `mistral-small` (broke immediately,
upstream 404/429 flap), then per coordinator's swap suggestion went to
`qwen3.5` (local, all-200 baseline). Total samples this session: ~600+,
distributed across one false-start and one real-but-aborted canary.

## What I observed (timestamps in cluster local)

1. **17:05 — first "Go" was premature.** Terminal #1 called "canary
   fired" but the live cluster was at `Status: Healthy, Step 6/6,
   SetWeight 100`, all 5 pods on the OLD stable RS, no in-progress
   canary. My loop ran for 90s producing 0/114 success on `mistral-small`
   — but those 4xx didn't matter to anything because there was no
   AnalysisRun in flight to consume them. We discovered two real-but-
   *unrelated* problems in the noise: (a) the OpenRouter `:free`-tier
   route for `mistralai/mistral-small-3.1-24b-instruct` is currently
   100% non-200 from upstream, and (b) `nousresearch/hermes-3-llama-3.1-
   405b:free` has the same flap. Both are user-facing degradations
   independent of any canary work.

2. **17:18 — second "Go" was real.** Rollout transitioned to revision 2
   (`litellm-67b4ccbdb4`), Step 1/6 paused at SetWeight 20, 4 stable +
   1 canary, both ReplicaSets on the same image (PR #215's synthetic
   env-var trigger — image rehearsal without an image change, very nice
   pattern). Loop ran clean: 600+ requests on `qwen3.5`, 100% 200s
   through the entire 20% pause window.

3. **~17:25 — promote → AnalysisRun → abort.** The AnalysisRun errored
   5× consecutively with `reflect: slice index out of range`, hitting
   `consecutiveErrorLimit (4)` and aborting the rollout. Diagnosis:
   PR #216's new query `litellm_request_total{status!~"2..|3.."}`
   correctly returns empty when the canary is healthy (which my qwen3.5
   loop guaranteed by producing only 200s), and Argo's `result[0]` indexer
   panics on empty vectors. The fix that closed the silent-4xx-pass risk
   accidentally opened a "panic when everything is fine" hole.

## What I'd raise for collective consideration

- **Single-model probing has a blind spot.** My loop hits one alias.
  The current AnalysisRun sums *all* requests across *all* pods — so if
  `mistral-small` were 100% broken (it is right now, upstream-side) but
  `qwen3.5` were 100% green (it was), my loop's all-200 traffic would
  *dilute* real consumer 4xx traffic in the union metric and could
  green-light a canary that's actually broken for half the user base.
  Suggestion for the next rehearsal: run a small fleet of Terminal #3
  instances, one per important model class (default chat, multimodal,
  coding, reasoning), and accept the ~5 req/sec aggregate load. Or fix
  the deeper issue — see next bullet.

- **Per-RS metric labels would solve multiple problems at once.** The
  current AnalysisTemplate aggregates across the union of stable+canary
  pods because `litellm_request_total` doesn't carry a per-ReplicaSet
  label. That forces (a) the "good enough for the homelab" arithmetic
  in PR #213's comment (a 100%-broken canary at 20% weight only shows
  as 20% union error, exactly at the 5% threshold's noise floor for
  marginal regressions), (b) the empty-vector trap in PR #216 (because
  with no real consumer traffic, the *union* numerator can be empty
  even when both sides exist), and (c) the dependency on Terminal #3
  running at all to keep the denominator non-zero. If the LiteLLM Helm
  chart can be coaxed into emitting `pod` or `replicaset` as a metric
  label, the AnalysisRun query can target only the canary, sidestepping
  all three failure modes.

- **PR #215's synthetic-trigger pattern needs a counter, not a date.**
  The env var `CANARY_REHEARSAL_2026_05_04: "1"` was clever — it
  produced a pod-template diff so the Rollout fired without a real
  image change. But future rehearsals on the same day, or rehearsals
  the day after, will get either no-op (same value → no diff) or a
  collision risk. Recommend `CANARY_REHEARSAL_NONCE: "<short-uuid>"`
  or `CANARY_REHEARSAL_COUNT: "<integer>"` that increments per use,
  with the value selected at PR-creation time.

## Two open questions for colleagues

- **For Terminal #1**: what state were you reading at 17:05 when you
  called "canary fired" the first time? Understanding whether that was
  a tooling issue (e.g. ArgoCD UI lag) vs a misread will tell us
  whether the orchestration needs a tighter contract — e.g. "Go means
  `kubectl argo rollouts get` shows `Status: Paused && SetWeight > 0`,
  not just `ArgoCD Synced`."

- **For whoever drafted #216**: how did the empty-vector failure mode
  escape pre-merge sanity? Is there a `promtool` or `vmselect` style
  smoke test we could add — query the live VictoriaMetrics with the
  proposed query against a healthy time window and assert it returns
  a numeric result, not an empty vector? Could live in a Tekton task
  triggered on changes to `apps/litellm/manifests/analysis-template.yaml`.

## Postscript on prompt-caching for the AI agents

(For whichever colleague is curious, since this session re-loaded the
full ~600-line CLAUDE.md ruleset on every cache miss past 5 min:) the
heartbeat-only quiet periods between 17:21 and 17:30 were probably the
most expensive part of this session in tokens, because each ~75s gap
between user messages straddled the 5-min cache TTL on average. Future
synthetic-traffic-driver loops might benefit from being a Tekton task
or a one-shot script with no LLM in the loop at all, freeing the agent
slot for more value-adding work like cluster observation or live
diagnosis. The "watch for ALERT" duty doesn't need a model — `awk` and
a Telegram webhook to `FRANK_C2_TELEGRAM_*` would suffice, and the
existing `notify-telegram.sh` infrastructure already covers it.

---

## 2026-05-04 ~17:35 — Reading T1 + T2, updating my picture

Read both. Several things to correct in my own write-up above and a few
direct answers owed.

### Correction to my diagnosis (acknowledging T1's bug-zero finding)

My write-up frames PR #216 as the bug ("the new query returns empty
when the canary is healthy → `result[0]` panic"). T1's deeper finding
makes that wrong by one level: the metric `litellm_request_total`
**does not exist on this cluster at all**. The OSS LiteLLM image
doesn't emit it; it's a paid Enterprise feature. The query was empty
because there is no series, not because the canary was healthy.

Net: PR #216's query change was beside the point. Both the OLD query
(`status=~"5.."`) and the NEW query (`status!~"2..|3.."`) would have
produced empty vectors against this VictoriaMetrics. PR #216 closed
the silent-4xx-pass risk in *theory* — and we should keep its strictness
once we have a real metric source — but on this cluster, with no series
emitted, both queries are equally broken.

So my "single-model probing has a blind spot" argument is conceptually
still true but moot for the failure we just hit: *no* number of synthetic
traffic generators on *any* model would have moved the needle, because
nothing was being scraped to begin with.

### Direct answers to T2's questions

1. **Yes, the loop was running** through the entire 17:23:51 → 17:24:31
   AnalysisRun window. Specifically: I logged `#0240` at 17:23:12,
   `#0300` at 17:24:28 — straddles the AR start and end. Loop has been
   continuous since 17:18:08.
2. **Zero 5xx, zero 4xx, all 200** through that window and through the
   entire run as of this writing (#720 at 17:33:27). Confirms — combined
   with T1's `vmsingle` probe returning `data: []` — that the failure was
   "metric never existed," not "metric exists but had zero data."
3. (n/a — was running)
4. T1 already ran the equivalent of your suggested check via VM directly,
   confirmed `data: []` for the `series?match[]=litellm_request_total`
   query. Closed.

### Direct answer to T1's question about the proper *positive* metric source

I'm closer to consumer-shape traffic than gateway internals, but here's
what I'd watch *if I had a metric pipeline*:

- **Cilium Hubble L7 stats** is my preferred answer.
  `hubble_http_responses_total{destination_workload="litellm", source_app=...}`
  exists on this cluster *today* (no app-side changes), is naturally
  per-pod (so you can filter by `destination_pod` to get
  per-ReplicaSet bucketing for free), and covers the full request
  shape — code, latency, method — without depending on LiteLLM
  exposing anything. It also catches things app-side metrics can't:
  connection-level RST, 502 from a proxy in front, kube-proxy mis-
  routing.
- **As a fallback, AR `web` provider hitting `/v1/models`** with a
  per-pod URL (via Service IP + headless service hack, or directly
  via the canary Service). Coarser — only catches the "pod is up
  and the proxy responds" axis, doesn't catch model-routing
  regressions — but cheap to implement and immediate.
- The signal *I'd* look at if I were a human watching this canary
  manually, after this session: **per-alias 4xx rate** with the
  alias as a label. The OpenRouter `:free`-tier flap on
  `mistral-small` and `hermes-405b` proves that "gateway-wide 4xx
  rate" hides per-route degradation. But this requires app-side
  emission, which we just established we don't have on the OSS
  image. So Hubble can't deliver this granularity by itself —
  unless we route per-model traffic through distinct backend
  Services, which would be a substantial re-architecture.

### Vote on T1's options (A/B/C)

Lean **A now, B-spec later**. Specifically:

- A: drop the AR steps from the canary, replace with `pause: { duration: ... }`
  to complete the rehearsal end-to-end. Honest scope. Captures a clean
  successful canary so the postmortem narrative isn't "five bugs and a
  failed rehearsal."
- Then, separately, brainstorm a `litellm-canary-via-hubble` design
  spec with Hubble L7 + per-pod labels as the anchor. That's not 1–2
  hours of plumbing — it's a real design call (per-pod metric
  cardinality, retention vs scrape resolution, what threshold makes
  sense at homelab scale, whether to switch to ArgoCD's
  `experimentTemplates` for richer comparison). It deserves its own
  brainstorm session, not a fix-up PR.
- Reject C. The captures so far cover failure modes, not a successful
  end-to-end canary; without one of those, the operating runbook can't
  honestly document the happy path.

### One thing for the operator's awareness

My traffic loop is still running (`/tmp/litellm-canary-traffic.sh`,
background task `bjtgmjebk`, monitor task `b6bh5lkib`). It's a no-op
right now — no AnalysisRun consuming the data, no metric being scraped,
just 1 req/sec of `qwen3.5` chat completions getting served by the 5
stable pods. Cost is negligible (Ollama is hot, sub-300ms latency, no
GPU contention since it's already in VRAM). I'll keep it parked unless
told otherwise — it's ready for the next promote/retry without restart
warmup.

### Postscript on the prompt-caching observation in my main note

My earlier suggestion that the synthetic traffic loop should be a
no-LLM script with a Telegram webhook still stands. But seeing T2's
event log, with operator timestamps and AR phase transitions
correlated to second-level resolution, makes me think the *opposite*
is also true at a higher altitude: the role T2 is playing — long-form
data-plane observer cross-referencing controller events — *is*
high-value LLM-shaped work. The 1 req/sec emitter underneath is
not. So: split the role. Synthetic-traffic-driver becomes a Tekton
task with a Telegram alarm; T3 (the agent-shaped slot) becomes a
"narrative observer" who reads logs, correlates timestamps, and
writes the postmortem material in real time. Today T3 was both, and
the agent half was load-bearing only at the bookend transitions.

---

## 2026-05-04 ~17:43 — Read T2's update

Three things to mark.

### T2's correction to my framing — accepted

T2 caught that my "PR #216's query returns empty when canary is
healthy → panic" framing was wrong on two layers, not one:

- *Surface layer* (which I corrected after T1's bug-zero finding):
  the metric doesn't exist at all, so the empty-vector is independent
  of canary health.
- *Inner layer* (T2's catch): even if the metric *did* exist,
  `5xx_rate / total_rate` on a healthy backend would produce
  *non-empty denominator* (200s → `total`) and empty numerator.
  PromQL arithmetic on `empty / non-empty` returns no series for that
  bucket, but the result vector would still have one entry per label
  set if any series existed. The slice has zero entries because there
  are zero `litellm_request_total` series, period.

My original framing got the right "this would have panicked" answer
for the wrong reason. Good catch.

### T2's distribution measurement — strong indirect confirmation

The 152/142/127/139 split across the 4 stable pods (σ/μ ≈ 6.7%) is
*much* better evidence than my single-LB-IP loop could have produced.
T3 had no way to know which pod served any given request without
asking the gateway to echo it. T2's per-pod request-count
attribution from the data plane is the missing artifact for the
"is the replica-count canary actually splitting cleanly?" question
in the postmortem narrative.

The "snapshot canary pod logs to a PV before scale-down" idea is
worth its own follow-up — exactly the kind of "we lose the most
important artifact at exactly the moment we need it most" failure
mode that's invisible until it bites. Suggest a `lifecycle.preStop`
hook on canary pods that `tar`s `/var/log` to a known PVC mount
before the scale-down's grace period expires. Cheap and idempotent.

### Constructive angle on Bug #5 (the license/feature-tier mismatch)

T2's right that Bug #5 is structurally different — paying for
Enterprise, building an exporter, or switching signal class. One
thing I want to add: the **"build an exporter"** option is cheaper
than it sounds for *this specific gateway*. LiteLLM's OSS image
already writes structured-JSON access logs to stdout for every
chat-completion request. A sidecar exporter that tails those logs
and emits Prometheus counters keyed on `model`, `status`, and
`api_user` is ~50 lines of Python with `prometheus_client`.
Concretely:

```python
import json, sys, re
from prometheus_client import Counter, start_http_server

req = Counter("litellm_request_total", "Requests",
              ["model", "status", "api_user"])
start_http_server(9090)
for line in sys.stdin:
    try:
        e = json.loads(line)
        if e.get("event") == "request_completed":
            req.labels(e["model"], str(e["status_code"]),
                       e.get("api_user", "anon")).inc()
    except (ValueError, KeyError): pass
```

Plumbing: configure LiteLLM to log JSON, sidecar reads `kubectl logs`-
equivalent via shared `emptyDir` + log redirect, exposes `:9090/metrics`,
ServiceMonitor scrapes it. End-to-end ~1 day of work. Carries the
exact metric name our existing AnalysisTemplate references, so once
deployed the AR query needs no change. Per-pod by construction (each
sidecar emits its own pod's traffic), which closes T3's per-RS-labels
suggestion at the same time.

Recording this as a candidate for the B-track brainstorm so it has
a concrete shape next to "Hubble L7" and "AR web provider." Three
real options to compare, not one vague direction.

### To T2 specifically

The "T1 called premature Go, not T2" attribution clarification — fair,
my "Terminal #1 called 'canary fired'" line in my main note was correct
but could be misread as implicating T2 because the chain of relayed
signals is fuzzy in narrative. For the postmortem record: the
premature signal was upstream of both of us. We both reacted to it,
and both flagged it independently after the cluster state contradicted
the call. That's the noteworthy bit — the system surfaced the
contradiction within a minute, not the misread itself.

---

## 2026-05-04 ~17:50 — Option A confirmed, T3 posture for the retry

Read T1's consensus + plan note. Operator confirmed Option A is the
direction. Marking my own posture for the next two events:

- **Retry on the path-A spec** (after T1's PR drops the AR steps and
  ArgoCD syncs): loop stays running on `qwen3.5`. Won't feed an
  AnalysisRun (there isn't one), but produces:
  (a) the per-pod request-count distribution that T2's measurement
  technique needs to confirm replica-count weighting on a *successful*
  canary (not just an aborted one), and
  (b) clean 200-rate evidence for the postmortem's happy-path capture.
- **Second canary on PR 1.6** (revert of the synthetic env var, after
  the retry completes Healthy): same posture, same loop, no changes.
  If the model_list refresh from the parked feature branch
  `inference--model-refresh-2026-05` ships in PR 1.6 *as well as* the
  env-var revert, then `qwen3.5` will start returning 404 on canary-
  routed requests, which gives us the per-second routing-split probe
  I sketched in my main note. If the model_list refresh stays
  separate, the loop stays all-200. Will report whichever shape arrives.

**Acks for the corrections T1 made to my framing:**

- "single-model probing blind spot is bigger than I treated it" — yes,
  and the *lucky* part is what I want to emphasize for the postmortem:
  Terminal #3 picked `mistral-small` first by happenstance and stumbled
  into the OpenRouter `:free`-tier flap within 90 seconds. With a
  different model pick, that real consumer-facing degradation might
  have stayed invisible through the entire rehearsal. "Lucky" is not
  a property a deploy pipeline should rely on.
- The sidecar-exporter sketch landing in the B-spec is the right call.
  Happy to flesh out the YAML+Python into a runnable example if that
  helps the brainstormer; otherwise the design spec just needs the
  shape.

**Loop stays armed.** Standing by for the retry signal.

---

## 2026-05-04 ~18:22 — Both rehearsal canaries Healthy, T3 stood down

Cycle #1 (PR #215 + #217 retry): completed Healthy at 18:01.
Cycle #2 (PR #218 env-var revert): completed Healthy at 18:15.

Final session tally for T3's loop:
- **Window**: 17:18:08 → 18:22:07 (64 min continuous)
- **Total samples**: 3010
- **Successes**: 3009 (all 200 on `qwen3.5`, sub-300ms latencies)
- **Failures**: 1 ERR (curl timeout during cycle #1's 50→100% endpoint churn)
- **Success rate**: 99.967%
- **Per-cycle attribution**: cycle #1 took the single ERR; cycle #2 was a clean 0/1300+ flush

Per-promote artifact summary for the postmortem:

| Cycle | Promote | Result |
|---|---|---|
| #1 | 20→50 | clean |
| #1 | 50→100 | 1 ERR (8s curl timeout, request landed on a connection being torn down) |
| #2 | 20→50 | clean |
| #2 | 50→100 | clean — *and* caught the transient 6-pod state T2 missed in cycle #1 |

Topology note for cycle #2: revision:3's "canary" RS is the *same RS*
that was revision:1's stable before any of this started
(`litellm-79db46b9fc`). The env-var revert reverted the pod-template
hash to its pre-#215 value, which the controller recognized and reused.
Net infrastructure delta from this whole cascade: zero.

**Standing down.** Loop stopped (`bjtgmjebk`), monitor stopped
(`b6bh5lkib`). Available if T1 spins up a third canary or B-track
brainstorm wants T3 to validate a sidecar-exporter prototype.
