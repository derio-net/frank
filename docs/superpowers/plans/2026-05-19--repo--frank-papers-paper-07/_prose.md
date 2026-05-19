# The Frank Papers — Paper 07: The Observability Stack, Honestly

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Complete (2026-05-19) — Paper 07 published; series Phase 1 continues.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 10, 04,
11 already published; Papers 14 and 06 are landing in parallel. This is Paper
07 (publish order 7) — the observability capability paper.

The capability question for Paper 07 is: *if you want a single screen that
tells you whether the cluster is healthy, who do you trust to render it — and
what does each option charge you in operational tax, $/GB, and proprietary
lock-in?* The vendor space splits along two axes: stack-shape (unified-SaaS vs
assembled-OSS) and storage-shape (logs-first vs metrics-first). Six candidates
cover the landscape, with **Grafana + Prometheus + Loki + VictoriaMetrics**
as Frank's case study — the LGTM-without-the-T pattern, with VM swapped in
for the Prometheus long-term storage tier and Tempo deferred until tracing is
actually load-bearing.

The scars are the point. File-provisioned alerts that look editable in the UI
but silently revert on pod restart. Grafana 12.x's server-side-expression
engine that rejected half of Frank's alert rules with `sse.parseError` on a
minor-version bump. `ALERTS{}` that does not exist in VictoriaMetrics for
Grafana-managed alerts and requires the `alertlist` panel as a workaround.
These aren't decorations on the §5 narrative — they're why the §6 decision
tree has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on small-scale tracing TCO at homelab scale,
and the counter-argument that commercial all-in-one stacks (Datadog, New
Relic) erase the assembly tax. Single-agent dossier construction is
appropriate — the six vendors are well-documented and overlap in conventions
(Prometheus-compat is the unifying API across most of the OSS field).

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and the
counter-argument. The counter to nail: *"commercial all-in-one observability
(Datadog, New Relic) is two orders of magnitude faster to stand up and
erases the alert-engine bug surface — why doesn't that win for Frank?"* Same
shape as Paper 00's answer (Frank is a learning platform), applied to the
observability capability specifically.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (cardinality, log-volume cost, tracing sample-rate trade)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (file-provisioned-alerts read-only in UI, Grafana 12.x SSE alert format break, ALERTS{} doesn't exist in VM)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a wall of glowing dashboards with a
skeptical / weighing expression, thin black tie, round reading glasses. One
chart in the wall shows a clear scar / spike — honest data, not hero
metrics. Mermaid diagrams: §1 stack position, §2 landscape (quadrantChart)
+ capability matrix, §3 four-to-six architecture flowcharts, §6 decision
tree. At least one Grafana UI screenshot from `192.168.55.203` showing a
real dashboard / alert list — replace with TODO placeholder if cluster
access is unavailable from the worktree.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-person
cluster, not academic). TL;DR ≤150 words written last. Dossier-link rendering
check (use either inline shortcode OR rely on automatic injection — not both).
Set `draft: false`, `status: published`. CI deploys via the existing blog
pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 07-observability and
Operating 05-observability, update README if relevant, set plan status to
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
