# The Frank Papers — Paper 06: GitOps at Small Scale

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Drafting (2026-05-19) — Paper 06 is the sixth Paper to publish in the series.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 10, 04,
11, 14 published — series Phase 1 is open, and this is the sixth Paper to
publish (publish order: `00 → 10 → 04 → 11 → 14 → 06 → ...`).

Paper 06 is the GitOps capability paper. 2400–4200 words, the standard
capability skeleton (§1 capability → §2 landscape → §3 architecture per
vendor → §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap),
and exercises every shortcode and diagram type at production size.

The capability question is: *if your cluster's source of truth lives in Git,
who watches Git and reconciles the cluster — and how do you trust the answer
when the reconciler disagrees with the cluster?* The vendor space splits along
two axes: pull-mode (the reconciler runs inside the cluster and pulls from
Git) vs push-mode (a CI pipeline pushes manifests at the cluster), and
opinionated all-in-one (Jenkins X, cloud-managed) vs unbundled component
(ArgoCD, Flux). Six candidates make the landscape, with **ArgoCD** as
Frank's case study — the App-of-Apps pattern, declarative-everything down
to LED colors, and a handful of scars that turned out to be load-bearing
for the series voice.

The scars are the point. The out-of-bounds symlink that locked the entire
GitOps loop into `ComparisonError`. Manual `kubectl patch` operations that
don't inherit `spec.syncPolicy.syncOptions` and blow the 256KB
last-applied-config annotation. Root App-of-Apps re-templating leaf
Application specs on every sync, reverting live patches inside the sync
window. These aren't decorations on the §5 narrative — they're why the §6
decision tree has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on multi-cluster fan-out cost at homelab
scale, and the counter-argument that "just bash + kubectl in CI" is fine
until it isn't. Parallel subagents per vendor are appropriate — one each
for ArgoCD, Flux v2, Jenkins X, cloud-managed GitOps, Spinnaker, and
just-bash — with a merger pass to consolidate.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and the
counter-argument. The counter to nail: *"GitOps is a fashion — just run
your CI's `kubectl apply` step and move on. Why is the reconciler worth
the complexity tax?"* Same shape as Paper 00's answer (Frank is a learning
platform), but applied to the GitOps capability specifically: the
reconciler exists to catch drift, and drift only matters when somebody
edits the cluster outside Git — which is a discipline you cannot learn
without a reconciler watching.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (sync latency, App-of-Apps depth, multi-cluster fan-out cost)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (symlink ComparisonError, live-spec-revert, syncOptions inheritance)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a Git repository whose branches feed root-
like fibres downward into a cluster, calm-approving expression, thin black
tie, round reading glasses. Mermaid diagrams: §1 stack position, §2
landscape (quadrantChart) + capability matrix, §3 four-to-six architecture
flowcharts, §6 decision tree. At least one ArgoCD UI screenshot from
`192.168.55.200` showing the App-of-Apps tree healthy.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic
injection — not both). Set `draft: false`, `status: published`. CI deploys
via the existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 05-gitops and Operating
03-gitops, update README if relevant, set plan status to Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
