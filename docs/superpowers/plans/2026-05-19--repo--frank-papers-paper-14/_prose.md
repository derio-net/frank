# The Frank Papers — Paper 14: Progressive Delivery & the Service-Mesh Tax

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Complete (2026-05-19) — Paper 14 draft published on branch `paper-14`; PR open for human review (publish order: `00 → 10 → 04 → 11 → 14`).

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 10, 04,
11 published.

Paper 14 is the fifth capability Paper to land in the series: 2400–4200
words, the standard skeleton (§1 capability → §2 landscape → §3 architecture
per vendor → §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap),
and the first Paper to confront *progressive delivery* — the capability that
exists somewhere between "deploy command" and "service mesh", that costs
disproportionately more than it looks like it should, and that has a vendor
landscape shaped almost entirely by the question *"which traffic router are
you willing to feed?"*.

The capability question is: *if you want to ship a change to production
without flipping every pod over at once — and without writing the rollback
yourself when the change is bad — who orchestrates the staged exposure, and
what tax do they charge?* The vendor space splits along two axes: traffic-
routing dependency (mesh-required vs replica-count fallback) and gating
discipline (manual vs metric-gated vs full-canary-analysis). Six candidates
make the landscape, with **Argo Rollouts** as Frank's case study — a
controller that can do canary and blueGreen, that integrates with `workloadRef`
into the existing Helm-managed Deployment, and that comes with a set of
scars Frank discovered by stepping on every single one of them.

The scars are the point. The traffic-router plugin URL that 404'd for 21
days and made the controller crash-loop. The `workloadRef.scaleDown: never`
default that quietly doubled traffic to the canary. The `litellm_*` metrics
that don't exist on the OSS image, that took 50 seconds to abort the
rollout, every single time. The pre-workload-phase reconcile abort that
shows steady-state in `kubectl get rollout` and lives only in the
controller pod log. The 4xx-blind successCondition that would auto-promote
a 100%-broken canary because the original query asked for `5xx` only.
These aren't decorations on the §5 narrative — they're why the §6 decision
tree has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on the absence of an apples-to-apples
"progressive-delivery tax" benchmark (controller overhead, mesh overhead,
ops overhead, all bundled), and the counter-argument that for small
clusters with stateful workloads, plain `Recreate` Deployments with manual
verification *is* the rational choice and progressive delivery is overkill.
Parallel subagents per vendor are appropriate — one each for Argo Rollouts,
Flagger, Linkerd traffic split, Spinnaker, Istio+Flagger, and vanilla
Deployments — with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"for a 6-node homelab with
mostly stateful workloads, manual `Recreate` is correct — why doesn't
that win for Frank?"* Same shape as Paper 04's framing applied to the
delivery capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (mesh overhead per request, controller CPU at N rollouts, metric provider lag)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (Cilium plugin 404, workloadRef.scaleDown=never, LiteLLM-Prometheus-Enterprise-only)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a traffic-splitting signal box with a
weighing/cautious expression, thin black tie, round reading glasses. The
visual metaphor is *traffic dispatch*. Mermaid diagrams: §1 stack position,
§2 landscape (quadrantChart) + capability matrix, §3 four-to-six
architecture flowcharts, §6 decision tree. At least one Argo Rollouts
canary screenshot (Grafana panel or `kubectl argo rollouts` output)
captured live from the cluster. Cluster-side captures may be deferred
with `-TODO.png` placeholders if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 19-progressive-delivery
and Operating 12-progressive-delivery, update README if relevant, set
plan status to Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
