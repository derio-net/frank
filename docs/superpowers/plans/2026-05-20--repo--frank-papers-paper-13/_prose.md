# The Frank Papers — Paper 13: Self-Hosted CI/CD on a Homelab

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Draft (2026-05-20) — Paper 13 in progress on branch `paper-13`; PR open for human review.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 10, 04,
11, 14, 06, 07, 02 published.

Paper 13 is a capability Paper in The Frank Papers series: 2400–4200
words, the standard skeleton (§1 capability → §2 landscape → §3 architecture
per vendor → §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap),
mapping the *self-hosted CI/CD* vendor space — the capability that sits
between "I committed code" and "an image was pushed to a registry",
that has the most lopsided cost curve in the whole stack (free at small
scale on GitHub Actions, expensive almost immediately on the self-hosted
side), and that has a vendor landscape shaped by a single architectural
question: *do you want one tool or three?*

The capability question is: *if you do not want your CI minutes billed
by a SaaS vendor — for cost, sovereignty, or air-gap reasons — who runs
your builds, who stores your images, and what is the tax for running
them yourself?* The vendor space splits along two axes: integration
shape (all-in-one platform vs three composable services — git host,
pipeline engine, OCI registry) and Kubernetes-nativity (pods-as-build-
steps vs build-agents-as-VMs). Six candidates fill the landscape, with
**Gitea + Tekton + Zot** as Frank's case study — a three-tool stack
where every layer is a CRD or a manifest in Git, where the pipelines
are declarative YAML, and where the scars came in the seams between
the three services.

The scars are the point. The Tekton v1 Task that silently failed
because we used `resources` instead of `computeResources` — the schema
migration from v1beta1 to v1 ate the field with no error. The Gitea
EventListener that refused to fire because the `github` interceptor
filters on `X-GitHub-Event` and Gitea sends `X-Gitea-Event`. The Zot
chart pinned at v0.1.0 because it was the first GA, with no TLS, no
auth, and no persistence story until v0.1.60+. The Gitea
`webhook.ALLOWED_HOST_LIST` that blocked in-cluster webhook delivery
to `svc.cluster.local`. The Tekton `runAsUser: 65534` (nobody) pods
that died on `HOME=/` being read-only. These aren't decorations on the
§5 narrative — they're the load-bearing evidence behind §6's leaves.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank
artefacts across ≥2 kinds, the named gap on the absence of a real
"self-hosted CI/CD tax" benchmark at homelab scale, and the
counter-argument that for a solo developer with an open-source repo,
GitHub Actions is the rational answer and self-hosting is overkill.
Parallel subagents per vendor are appropriate — one each for the
Gitea+Tekton+Zot stack, GitLab CE, Forgejo+Woodpecker, Drone CI,
Jenkins, and GitHub Actions — with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap
and the counter-argument. The counter to nail: *"for a solo developer
with an open-source repo, GitHub Actions is free and zero-ops — why
doesn't that win for Frank?"* Same shape as Papers 04 and 14 applied
to the CI/CD capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (concurrent build counts, registry storage growth, webhook latency)
- §5 Frank's choice, and what happened (300–600 words) + 2–3 `{{< papers/scar >}}` callouts (Tekton v1 `resources` field, Gitea `X-Gitea-Event` header, Zot v0.1.0 missing TLS/auth)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a three-stage pipeline of glowing
rectangles labelled `git → test → push` mounted to a rack panel,
weighing-but-approving expression, thin black tie, round reading
glasses. The visual metaphor is *a pipeline of three lit stages*.
Mermaid diagrams: §1 stack position, §2 landscape (quadrantChart) +
capability matrix, §3 four-to-six architecture flowcharts, §6
decision tree. At least one Tekton pipeline screenshot (Tekton
Dashboard view of a PipelineRun, or `kubectl get pipelinerun`
output) captured live from the cluster. Cluster-side captures may
be deferred with `-TODO.png` placeholders if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or
third-person cluster, not academic). TL;DR ≤150 words written last.
Dossier-link rendering check (use either inline shortcode OR rely on
automatic injection — not both). Set `draft: false`, `status: published`.
CI deploys via the existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: verify the auto-rendered
cross-link chips appear on Building 27-cicd-platform and Operating
22-cicd-platform, update README if relevant, set plan status to
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
