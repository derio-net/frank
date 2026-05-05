# Terminal #3 — synthetic traffic driver (real canary, PR #210)

## What changed since the rehearsal

The rehearsal canaries (#215 / #218) were synthetic: same image both
sides, same model_list, env-var-only trigger. PR #210 is the real
thing — three coupled changes in a single rollout:

1. LiteLLM image bump: `main-v1.82.3-stable` → `main-v1.83.14-stable`
2. Full model_list rename: `qwen3.5`/`mistral-small`/`omnicoder`/
   `qwen3-coder`/`gemma-27b`/`llama-70b`/`step-flash` → 11 new aliases
   (default chat: `mistral-small-24b`; multimodal: `gemma-12b`,
   `qwen-vl-7b`, `nemotron-vl-12b`; coding: `qwen-coder-14b`,
   `qwen-coder-480b`; reasoning: `qwen-think-14b`, `qwen-next-80b`;
   omni: `nemotron-omni-30b`; large: `gemma-31b`, `hermes-405b`)
3. Ollama PVC expansion: 30Gi → 200Gi (Longhorn `allowVolumeExpansion`)

Only `hermes-405b` survives the rename, and it's been broken at
upstream OpenRouter `:free` since the rehearsal day.

## Why dual-probe this time, not single-model

The rewritten runbook's explicit warning:

> **Single-model probing has a blind spot.** A traffic loop hitting
> only one alias can mask a per-route degradation in another.

For a canary that renames every alias, the high-value strategy is
**dual-probe**: alternate one alias from each side of the rename and
read the 4xx pattern as a routing-split signal.

| Phase | qwen3.5 (OLD) | mistral-small-24b (NEW) |
|---|---|---|
| Pre-canary (stable=OLD) | 200 | 400 (alias absent) |
| Canary 20% | 80% 200 / 20% 4xx | 80% 4xx / 20% 200 |
| Canary 50% | 50/50 | 50/50 |
| Canary 100% (post-promote) | 100% 4xx | 100% 200 |

So **4xx is expected** for this canary (the runbook calls this out
too) — T3's alarm is narrowed to 5xx + curl-ERR (server errors,
timeouts, cold-pull misses). 4xx becomes routing-split *signal*.

## Critical pre-canary action — pre-pull new local tags

```bash
# AFTER PR #210 syncs and the Ollama PVC shows 200Gi capacity,
# BEFORE the canary's first request:
for tag in mistral-small3.2:24b gemma3:12b qwen2.5vl:7b-q8_0 \
           qwen2.5-coder:14b-instruct-q6_K qwen3:14b; do
  kubectl exec -n ollama deploy/ollama -- ollama pull "$tag"
done
```

This will NOT run autonomously — it's a ~51GB shared-state
modification, requires explicit operator go-ahead.

**Why pre-pull is critical for this canary:**

- Canary pod's first request for a new alias triggers Ollama's cold
  pull (~30-120s for a 14GB tag).
- Cold pull exceeds LiteLLM's upstream timeout → 5xx response.
- T3 can't distinguish that 5xx from a real regression — it would
  shout an alarm that's actually a missed pre-pull.
- Pre-pull eliminates the race.

**Sequencing constraint:** PVC expansion has to complete *before*
pre-pull. Current PVC is 30Gi capacity, 15GB free; `mistral-small3.2:24b`
alone is ~14GB. Once Longhorn reports 200Gi, the pulls can run in
parallel with the migration PreSync hook (~4-8 min on raspi-1) and
the canary image pull (~7 min per node — FIRST canary on the new
LiteLLM image, so no cluster-wide cache).

## Other timing expectations for #210 specifically

- **PreSync migration**: ~4-8 min as before (raspi-1 ARM cold pull
  if image not cached; ~3-4 min if cached from rehearsal).
- **Canary image pull**: NEW `main-v1.83.14-stable` tag uncached on
  every node. Per-node pull ~5-7 min. Across the cycle (1 → 3 → 5
  canary pods, each on a different node) that's ~15-20 min of
  sequential cold-pull time on top of the rehearsal's ~10-min cycle.
  Don't read a long ContainerCreating as a stall.
- **Total observation time**: budget 30-40 min from PR merge to
  Healthy, dominated by image pulls.

## Operator-side checklist (the order I'd suggest)

1. Merge PR #210.
2. Watch ArgoCD for the PVC expansion to land (`kubectl get pvc -n ollama`
   showing CAPACITY=200Gi).
3. Pre-pull new tags (command above) — runs ~10-15 min in parallel
   with everything else. T3 will not start the loop until this is
   complete (or operator confirms it's safe to skip).
4. Watch the Rollout: PreSync → revision:N spawn → canary pod cold
   pull → Step 1/4 paused at SetWeight 20.
5. Signal "canary fired" — T3 launches the dual-probe loop.
6. Promote × 2 with operator-judged pauses (per runbook).
7. Healthy → T3 stops the loop, captures the per-model:per-code
   histogram for the postmortem.

## What's staged on T3's side

- Script `/tmp/litellm-canary-traffic.sh` updated for dual-probe,
  4xx-tolerant, 5xx-strict (red ALERT only on 5xx / curl-ERR /
  unexpected codes).
- Script tracks per-model:per-code counts in a bash assoc array; the
  `INT/TERM` trap prints the full histogram on Ctrl-C, which is the
  artifact the postmortem will want to cite for "did the model_list
  rename land cleanly?"
- Monitor command will be re-armed at launch with the same
  first-occurrence-per-code + 1min-heartbeat filter as the rehearsal,
  with one tweak: ALERT becomes 5xx-only (the rehearsal's "any
  non-200" rule would spam during expected 4xx phases of this canary).

Standing by for the operator's PR-merge signal.

---

## ~19:18 — Read T1 + T2

### To T1 — your "don't mix lineups" concern

You said: "the canary is going to put roughly 20% of requests on the
new image where the OLD alias names won't resolve. Mid-canary 4xx
from 'model not found' would be confusing noise."

I want to push back on the framing — and propose a synthesis. Two
points:

**1. Single-model probing produces the same 4xx noise, just less
measured.** If T3 drives `qwen3.5` only, ~20% of requests during
canary-at-20%-weight will still land on canary pods that have the
NEW lineup which doesn't include `qwen3.5` → still 4xx. The only way
to get clean 200s during the canary is to pick an alias that's in
*both* lineups, and the only overlap is `hermes-405b`, which has been
upstream-broken since this morning. So "stick to current-stable
aliases pre-promote" doesn't actually avoid the noise once the canary
is taking traffic — it just hides the routing-split structure of the
4xx behind ambiguity.

**2. The 4xx isn't "confusing noise" from the consumer perspective —
it's real impact.** Real consumers calling `qwen3.5` during this
canary's pause windows WILL see 20% / 50% / 100% 4xx response rates
(depending on weight). That's the cost of a model_list rename
without alias-aliases-to-old-names. If the goal of T3's loop is
"bake-test the canary by watching consumer-facing behavior live" (the
runbook's words), then *not* surfacing this is hiding the truth.

**Synthesis:** dual-probe (`qwen3.5` ⇄ `mistral-small-24b`) with a
4xx-tolerant / 5xx-strict alarm policy. The script already
distinguishes them: 4xx prints a neutral status line, only 5xx /
curl-ERR / unexpected codes print the red ALERT. The operator's
vigilance budget is preserved because the only red lines are real
errors. The per-model:per-code histogram printed on Ctrl-C gives
the postmortem the routing-split evidence T2 captured manually with
per-pod request counts last cycle — same data, lower-overhead
collection.

I'll go with dual-probe unless you or the operator vetoes.

### To T2 — pre-pull list correction

Your post lists 5 local tags + 6 "larger ones" (`gemma-31b`,
`nemotron-vl-12b`, `nemotron-omni-30b`, `qwen-next-80b`,
`qwen-coder-480b`, `hermes-405b`) and suggests pre-pulling those too.

Those 6 are **NOT local — they're cloud aliases** (OpenRouter or
similar). They map to API providers in `model_list`, not to
`ollama/...`. Cross-checking the feature branch's `apps/litellm/values.yaml`:
only 5 entries have `model: ollama/...`:

| Alias | Ollama tag |
|---|---|
| mistral-small-24b | `ollama/mistral-small3.2:24b` |
| gemma-12b | `ollama/gemma3:12b` |
| qwen-vl-7b | `ollama/qwen2.5vl:7b-q8_0` |
| qwen-coder-14b | `ollama/qwen2.5-coder:14b-instruct-q6_K` |
| qwen-think-14b | `ollama/qwen3:14b` |

Those 5, totalling ~51GB, are the entire pre-pull surface. The other
6 are upstream-routed and don't touch the Ollama PVC. So the runbook's
pre-pull command (which is also the 5-tag list above) is complete —
no need to add the cloud aliases.

This also means the PVC expansion (30Gi → 200Gi) is sized for the
~51GB local set with comfortable headroom for future additions, not
for pulling all 11 aliases. Confirms the chart's bump is right-sized.

### Operational alignment

T2 independently flagged the pre-pull issue and proposed running it
in parallel with the canary firing. We're aligned. The only
sequencing point I want to nail: **wait for the PVC to actually
expand before kicking off the pulls**, otherwise the first ~14GB
pull (mistral-small3.2:24b) overflows the current 30Gi capacity.
Longhorn `allowVolumeExpansion` is fast (seconds) but it does take a
moment to propagate; `kubectl get pvc -n ollama -o
jsonpath='{.items[0].status.capacity.storage}'` should show `200Gi`
before pulling.

---

## ~06:24 — Canary Healthy, T3 stood down, **and a real correction**

PR #210 + #220 (arm64 patch follow-up) completed end-to-end Healthy
at ~06:21. Both promotes clean. Five new canary pods on
`main-v1.83.14-stable.patch.1` with the new 11-alias model_list, old
RS scaled to 0.

### Final tally

```
Single-model qwen3.5 loop:      856 samples
  200 (stable RS):              430
  400 (canary RS):              426
  5xx/ERR alarms (single-model phase):  0
```

The 4xx pattern alone documented the routing-split through the entire
rollout. Distribution by phase (sampled live, not estimated):

| Step | SetWeight | Loop ratio (200 / 400) |
|---|---|---|
| 1/4 paused @ 20% | 20 | ~80 / ~20 |
| 2/4 mid-promote (canary cold-pulling patch.1) | 50 (Actual=25) | ~80 / ~20 (still 1 canary ready) |
| 3/4 paused @ 50% | 50 | ~50 / ~50 (3 canary ready, 6 pods total) |
| 4/4 Healthy @ 100% | 100 | 0 / 100 |

Zero ERRs through both promote transitions — better than the
rehearsal cycle #1 (1 ERR at 50→100). Better even than rehearsal
cycle #2 (also 0 ERRs but caught the 6-pod transient state). This
real canary captured the 6-pod state cleanly *and* zero churn ERRs,
on the hardest path (real image change, not just env-var nudge).

### **Correction: my dual-probe was wrong, T1 was right (for a different reason)**

Before launching, I argued in this channel for a dual-probe loop
(`qwen3.5` ⇄ `mistral-small-24b`), pushing back on T1's "don't mix
lineups" advice. The dual-probe failed catastrophically in the first
30 seconds of running:

```
#0028  mistral-small-24b  ERR
#0031  qwen3.5            ERR
#0032  mistral-small-24b  ERR
#0033  qwen3.5            ERR
#0037  qwen3.5            ERR
#0039  qwen3.5            ERR
... 12 ERRs total before I stopped it
```

**Root cause: Ollama's `OLLAMA_MAX_LOADED_MODELS=1` configuration on
the 16GB RTX 5070 Ti.** Each alternation between two local models
(`qwen3.5:9b` and `mistral-small3.2:24b`) forced Ollama to swap the
loaded model in/out of VRAM. ~10-30s per swap, well past curl's 8s
timeout. **My probe was the failure mode.** Pre-pull staged the
models on disk; it didn't ensure they could coexist in VRAM.

T1's earlier "don't mix lineups" advice was right, even if their
articulated reason ("4xx from model-not-found is confusing noise")
wasn't quite the actual hazard. The real hazard is that probing two
local models on a `MAX_LOADED_MODELS=1` Ollama is probe-induced load
that breaks the system you're probing. I missed this. T2's earlier
note about Ollama's "lazy-load model means they live on disk and get
loaded on demand" was the technical fact that should have triggered
the realization, but it landed as a footnote and I didn't connect it
to my probe shape.

### What ended up working

Single-model `qwen3.5` produced clean per-second routing-split
signal:
- Stable RS: serves `qwen3.5` from VRAM (already loaded since cycle
  start) → 200
- Canary RS: rejects `qwen3.5` at LiteLLM-gateway level (alias not in
  new lineup) → 400 *without ever calling Ollama*

So the 400-path doesn't touch the GPU at all. Zero VRAM pressure
from canary-routed requests. The ratio of 200/400 IS the routing-
split, exactly. T1 had the right shape for entirely the wrong stated
reason.

### Lesson for the operating runbook

For any future canary on this gateway:

> Synthetic traffic loops MUST probe a single local model whose
> rejection path is gateway-level (i.e. the model is absent from one
> side's `model_list`), so the rejection doesn't trigger Ollama
> activity. Multi-model rotation across local models is unsafe with
> `OLLAMA_MAX_LOADED_MODELS=1` — the probe causes thrashing.

I'll fold this into the runbook's Terminal #3 section as a footnote
unless T1 wants to handle it from the postmortem write-up perspective.

### Stood down

Loop and monitor stopped (`b0y8flula`, `bc5lhdo6g`). Available for
post-canary alias verification (the 11-model verify loop from the
runbook) if the operator wants T3 to drive it.
