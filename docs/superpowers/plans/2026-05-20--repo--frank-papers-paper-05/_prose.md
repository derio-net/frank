# The Frank Papers — Paper 05: GPU Scheduling for Mixed Workloads

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** In progress — Paper 05 draft on branch `paper-05`; PR open for
human review (publish order: 9).

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 02, 04,
06, 07, 10, 11, 14 published.

Paper 05 is the next capability Paper to land in the series: 2400–4200
words, the standard skeleton (§1 capability → §2 landscape → §3
architecture per vendor → §4 scale → §5 Frank's choice → §6 generalization
→ §7 roadmap), and the first Paper to confront *GPU scheduling for mixed
workloads* — the capability that sits between "Kubernetes scheduler" and
"vendor driver", that costs disproportionately more than it looks like it
should, and that has a vendor landscape shaped almost entirely by the
question *"whose silicon do you have, and are you willing to partition
it?"*.

The capability question is: *if you want to run heterogeneous accelerator
workloads — discrete NVIDIA GPUs, Intel iGPUs, maybe AMD ROCm, maybe
partitioned MIG instances — on a single Kubernetes cluster, who tells the
scheduler which pod gets which silicon, and what tax do they charge for
that decision?* The vendor space splits along two axes: device-model
generation (legacy device plugin vs Dynamic Resource Allocation) and
ownership model (single-tenant raw access vs partitioned multi-tenant
quota). Six candidates make the landscape, with **NVIDIA GPU Operator +
Intel GPU Resource Driver** as Frank's case study — a pair of controllers
that together expose one RTX 5070 Ti on gpu-1 and three Intel iGPUs on
mini-1/2/3 to Kubernetes, both routed through the in-house gpu-switcher
service that brokers exclusive use among competing inference workloads.

The scars are the point. The Talos extension dance that refused to validate
NVIDIA's stock driver installer because the immutable OS sandboxes
mutable-kernel-module space. The `nvidia.com/gpu:NoSchedule` taint that the
driver re-validation re-asserts on restart, silently disrupting every GPU
workload that doesn't ship a defensive toleration. The Ollama `system
memory` errors that turned out to be cgroup RAM ceiling, not VRAM, because
`OLLAMA_KEEP_ALIVE` had pinned the page cache near `resources.limits.memory`.
The `kubectl port-forward` flakes that hit *only* gpu-1, with CNI-netns
errors, that forced a switch to `kubectl exec ... wget` for every in-pod
metric capture. These aren't decorations on the §5 narrative — they're why
the §6 decision tree has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on the absence of an apples-to-apples
"GPU-scheduling tax" benchmark (operator overhead, taint-re-assertion
recovery time, fragmentation cost on partitioned workloads, ops time per
GPU node), and the counter-argument that for single-GPU homelabs with one
workload at a time, the device plugin alone is sufficient and Dynamic
Resource Allocation is overkill. Parallel subagents per vendor are
appropriate — one each for NVIDIA GPU Operator, Intel Device Plugin/DRA,
AMD ROCm, NVIDIA MIG/MPS partitioning, Run.AI, and Volcano — with a
merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"for a homelab with one
NVIDIA card and one workload, the device plugin alone covers the case —
why doesn't that win for Frank?"* Same shape as Paper 14's framing applied
to the GPU-scheduling capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (operator overhead per node, MIG-partition fragmentation cost, DRA scheduling latency)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (Talos driver validation refusal, NVIDIA taint re-assertion, OLLAMA_KEEP_ALIVE cgroup-RAM)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a single GPU card seen through his round
reading glasses, with two workload streams (a green inference batch and a
blue training batch) sharing time-slices on its surface. Frank's
expression: weighing — this is the layer where ownership decisions get
expensive. Mermaid diagrams: §1 stack position, §2 landscape (quadrantChart)
+ capability matrix, §3 four-to-six architecture flowcharts, §6 decision
tree. At least one Grafana GPU-utilisation panel captured live from the
cluster. Cluster-side captures may be deferred with `-TODO.png` placeholders
if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 04-gpu-compute and
Operating 04-gpu-compute, update README if relevant, set plan status to
Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
