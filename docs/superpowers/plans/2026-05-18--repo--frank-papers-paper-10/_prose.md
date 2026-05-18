# The Frank Papers — Paper 10: Self-Hosted Inference & the LLM Gateway Pattern

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Pending — Paper 10 is the first capability paper after the Paper 00 prologue (publish order 2 of the Phase 1 series).

**Prerequisite:** Paper 00 (`2026-05-16--repo--frank-papers-paper-00`) complete —
the Papers section landing, the per-paper cover template, and the dossier gate
have all been exercised end-to-end against a real publication.

Paper 10 is the first true capability paper in the series. The capability is
"running LLM inference inside the cluster", and the question is the now-familiar
build/buy split: which engine runs the model, and does anything sit *in front
of* the engine?

The landscape spans six vendors across two layers. At the engine tier:
**Ollama** (single-binary local server, Modelfile abstraction), **vLLM**
(PagedAttention, throughput-optimised, the engine many SaaS providers run),
**llama.cpp / llama-server** (CPU-first, GGUF, runs on a Pi), and
**HuggingFace TGI** (production-grade serving). At the gateway tier:
**LiteLLM** (OSS proxy with virtual keys, cost tracking, OpenAI-compatible
routing — Frank's choice) and **OpenRouter** (managed gateway-as-a-service —
the build-vs-buy comparison).

Frank's stack is Ollama on `gpu-1` (RTX 5070 Ti, 16GB GDDR7) behind LiteLLM
at `192.168.55.206`. The paper is honest about what this combination costs:
the RTX 5070 Ti's VRAM ceiling forced qwen-vl-7b from `q8_0` to `Q4_K_M`,
LiteLLM's OSS image emits no `litellm_*` Prometheus metrics (enterprise-only,
two weeks of empty Grafana panels before we noticed), and the
`OLLAMA_KEEP_ALIVE` page cache pinned the container cgroup RAM near
`resources.limits.memory` so "system memory" errors looked like a VRAM problem
when they were a cgroup problem. Three real scars, all dated, all cited.

## Phase 1: Dossier construction

Research the engine + gateway landscape independently. Source material spans
≥3 distinct types: the vLLM PagedAttention paper (Kwon et al. 2023), Ollama
and LiteLLM vendor docs, a vLLM-vs-TGI throughput benchmark, and a named
practitioner postmortem (Simon Willison / Hamel Husain / equivalent) on
running OSS LLMs at small scale. Frank artefacts include the LiteLLM
`values.yaml` plus model-list ConfigMap (yaml), the `main-v1.83.14-stable.patch.1`
bump and the Prometheus-enterprise discovery (commit + incident), an inference
Grafana screenshot, the OLLAMA_KEEP_ALIVE cgroup-RAM incident, and the
Argo Rollouts canary-tuning gotchas around LiteLLM.

Parallel subagents are appropriate: one per vendor mini-dossier (Ollama, vLLM,
llama.cpp, TGI, LiteLLM, OpenRouter), a merger consolidates, and a reviewer
audits the gap rules and counter-argument. The key counter-argument to nail is
"just use the OpenAI API — why doesn't that win?", answered with the
data-locality / latency-floor / learning-depth triple.

## Phase 2: Gate validation

Run `scripts/validate-dossier.py` and fix any failures. Human gate: author
reviews the named gaps (the "no small-scale benchmark at ≤2 concurrent users"
gap is the load-bearing one) and confirms the counter-argument is framed
honestly. When satisfied, set dossier `status: ready` and commit.

## Phase 3: Scaffold + draft

Run the scaffold script if it has not already been invoked. Then fill all
sections in the canonical order, leaving TL;DR for last:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + 1 `flowchart LR`
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` +
  `{{< papers/capability-matrix data="vendors" >}}`
- §3 How each option handles the hard part (800–1400 words) + 1 `flowchart TD`
  per vendor, shared visual language
- §4 What scale changes (300–600 words) + ≥1 benchmark chart OR ≥2 citations
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}`
  callouts
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart
  with ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)

Author the `data/vendors.yaml` page-bundle data file as part of §2's
capability matrix step. Feature rows cover OpenAI-compat API, GGUF quantisation,
PagedAttention, multi-user throughput, gateway features, Prometheus metrics
(OSS tier), and CPU-only support — the LiteLLM Prometheus row carries `no`,
not `partial`, because that gap is the load-bearing honesty marker for §5.

## Phase 4: Media fill

Per-paper cover image: Frank examining a glowing token-stream LLM with a
curious/weighing expression, wearing his thin black tie and round reading
glasses. Add the prompt to `blog/prompt_for_images.yaml` under the
`# --- Papers Series Covers ---` section established by Paper 00, then
generate with `scripts/generate-all-images.py --only paper-10-cover`. Up to
three regeneration attempts if the visual signature is missing.

Six Mermaid diagrams in total (one §1 flowchart, one §6 decision tree, four §3
architecture diagrams with shared shapes — Ollama, vLLM, llama.cpp / TGI
combined, LiteLLM / OpenRouter combined). Verify the production build runs
error-free, and copy the inference Grafana screenshot from the dossier
directory into the page bundle so it ships with Hugo.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — every scar carries a real date and a
real incident). Write the TL;DR (≤150 words) last, with one paragraph per
big idea: the build/buy split, Frank's actual stack, and the §6 generalisation
limit. Confirm the `papers/dossier-link` does not double-render (the
`single.html` partial auto-injects the chip in the footer — pick auto OR inline,
not both). Flip `draft: false` and `status: published`, run the production
Hugo build, then commit and push.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper. Paper 10 publishes on the existing
public blog at `blog.derio.net/frank` — no new IngressRoute, no homepage tile.
The `papers-backlink.html` partial auto-renders cross-series chips on the
existing Building 10-local-inference and Operating 07-inference posts; both
edits to those posts are *zero* — the chip appears on the next Hugo build
because Paper 10's frontmatter declares the relationship. No new Building or
Operating post is written. No `manual-operation` blocks in this plan, so the
runbook sync is a no-op. README is unchanged unless something user-visible
shipped alongside the paper. Set plan status to Complete and log the publish
date in the spec's plan ledger.

## Phase summary

| # | Phase | Tag | Depends on |
|---|-------|-----|-----------|
| 1 | Dossier construction | agentic | — |
| 2 | Gate validation | manual | 1 |
| 3 | Scaffold + draft | agentic | 2 |
| 4 | Media fill | agentic | 3 |
| 5 | Review + publish | manual | 4 |
| 6 | Post-deploy checklist | manual | 5 |
