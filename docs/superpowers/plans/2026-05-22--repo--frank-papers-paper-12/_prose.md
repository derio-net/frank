# The Frank Papers — Paper 12: Multi-Tenancy with vCluster

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Drafting (2026-05-22) — Paper 12 plan opened on branch `paper-12`; execution to follow on the same branch.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 02, 03,
04, 05, 06, 07, 08, 09, 10, 11, 13, 14, 17 already drafted/published; Paper 12
sits at publish-order 16 in the Phase-1 sequence.

Paper 12 is the multi-tenancy Paper in the series: 2400–4200 words, the
standard skeleton (§1 capability → §2 landscape → §3 architecture per vendor
→ §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap), and the
first Paper to confront the *tenant-boundary spectrum* — the capability where
the answers are not different brands of the same thing, they are *categorically
different shapes of isolation*, and the price of each shape is a different
resource-and-operational floor.

The capability question is: *when do you need K8s tenant boundaries stronger
than namespaces but weaker than separate clusters — and what does each rung
on that ladder actually cost in steady-state RAM, CPU, control-plane upgrade
toil, and blast-radius math?* The vendor space splits along three axes:
**control-plane shape** (one shared API server, one virtual API server per
tenant inside the host cluster, or one real cluster per tenant), **policy
surface** (network/quota policy bolted onto namespaces vs. complete API
isolation), and **operational floor** (a 50-MiB RoleBinding vs. a 300-MiB
StatefulSet vs. a whole control plane). Five-to-six candidates make the
landscape, with **vCluster (OSS, embedded SQLite, Longhorn-backed) running
under ArgoCD's App-of-Apps as `apps/vclusters/<name>`** as Frank's case
study — a per-tenant virtual control plane that gives the tenant API
isolation, lets them install CRDs and break things, and costs Frank one
StatefulSet plus a 5-GiB PV per tenant.

The scars are the point — and the most surprising scar in this Paper is
the *near-absence of in-flight scars*. The vCluster app sits in `apps/vclusters/`
with `experiments/values.yaml` as its only live instance; the gotcha file
records no vCluster-specific entries; the cluster's own pivot away from
vClusters was a structural choice (the `2026-03-20 multi-cluster-restructure`
plan introduced the **Hop** cluster as a *real* separate cluster for the
public-edge workload, not a vCluster). That absence is itself the finding:
at homelab scale, vCluster's worst failure mode is not a runtime incident,
it's a *category mismatch* — when "I need a second cluster" really means
"I need a second cluster, not a virtual one inside the first." Frank chose
both. The Paper has to say so.

## Phase 1: Dossier construction

Five-to-six vendors (plain namespaces + RBAC + Cilium NetworkPolicies as
the null hypothesis; vCluster as Frank's pick; Kamaji as the control-plane-
as-pod alternative; Capsule as the policy-based namespace-tenancy strawman;
Cluster API as the per-tenant-real-cluster heavyweight; optional: HyperShift
for the enterprise reference point), ≥5 primary sources across ≥3 type values
(vendor architecture docs for vCluster / Kamaji / Capsule; the K8s SIG-Auth
or SIG-Multitenancy position paper or talk; one real-world postmortem of a
vCluster + storage or vCluster + CRD integration; Frank's own tenant spec
at `docs/superpowers/specs/2026-03-07--tenant--vcluster-design.md`), ≥3
Frank artefacts across ≥2 kinds (the template values, the per-instance
values, the multi-cluster-restructure plan as `commit`-kind evidence of
the "vCluster is not the answer to this question" pivot), one named gap
(no public benchmark of per-vCluster steady-state RAM/CPU floor across
realistic workload mixes at homelab scale), and one counter-argument
(for a 3-person team running 5 services, plain namespaces + RBAC is fine
— why doesn't that win?). Parallel subagents per vendor are appropriate.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"for a 3-person team running
5 services, plain namespaces + RBAC is fine — why doesn't that win?"* The
honest answer has to acknowledge that for many teams, plain namespaces
WIN — and explain what Frank is buying with vCluster that the namespace-
only answer doesn't deliver (CRD installation, cluster-scoped resource
isolation, kubeconfig handoff to an external user with zero host
visibility).

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed (see the spec's
§ Per-paper anatomy table). Topic-specific callouts:

- **§1 stack-position diagram** — show where tenant boundaries sit between
  the kernel (Linux cgroups + namespaces) and the application (K8s
  Namespace + RBAC + NetworkPolicy). The point is that "multi-tenancy"
  spans five layers and the vendor space picks different layers to
  enforce at.
- **§3 architecture-per-vendor flowcharts** — same visual language as
  Paper 09: squares = controllers/servers; rounded rectangles = K8s
  resources; cylinders = backing stores; diamonds = auth gates. One
  diagram for each tenancy *shape*: shared control plane (Capsule),
  virtual control plane (vCluster, Kamaji), real cluster per tenant
  (Cluster API). The diagrams' job is to make the cost difference
  visible at a glance — count the boxes per tenant.
- **§4 scale callouts** — three axes: per-tenant RAM/CPU floor (the
  "how many tenants can a 64-GiB mini run" question); control-plane
  upgrade story (when the host K8s upgrades from 1.34 to 1.35, what
  happens to each tenancy shape); blast radius (a misbehaving tenant
  pod, a malicious tenant CRD, a runaway tenant Job). Cite ≥2 primary
  sources from the dossier.
- **§5 scars** — and the finding that vCluster has *no* in-flight scars
  in Frank's gotcha registry. Treat that as a result, not a gap: it
  means the OSS-embedded-SQLite + Longhorn-PV path is genuinely calm
  at homelab scale. Where the scars DO show up is the structural
  decision: the `multi-cluster-restructure` plan stood up Hop (a real
  Hetzner Talos cluster) for the public-edge workload rather than
  trying to make a vCluster do that job. That's the Paper's most
  honest moment: *Frank's pick is vCluster for sandboxes and a second
  real cluster for edge — same repo, different answer per question.*
- **§6 decision tree** — ≤4 leaves: namespace + RBAC + NetworkPolicy
  (one team, low CRD churn); Capsule (multi-team SaaS-style platform
  with policy-as-code culture); vCluster (sandbox / experiment / per-
  user kubeconfig); separate cluster (production isolation, regulated
  workload, blast-radius math that doesn't survive a shared control
  plane).

## Phase 4: Media fill

Per-paper cover: Frank drawing concentric boundary rings around groups
of pods on a whiteboard with a focused, weighing expression — the kind
of person who is sizing up *which* boundary to draw, not picking a brand.
Thin black tie, round reading glasses. The visual metaphor is *concentric
boundaries*. Mermaid diagrams: §1 stack position, §2 landscape
(quadrantChart) + capability matrix, §3 four architecture flowcharts (one
per tenancy shape), §6 decision tree. At least one cluster-side capture
(either `kubectl -n vcluster-experiments get pods,statefulset,pvc` output
or the result of `vcluster connect experiments -n vcluster-experiments`
showing the virtual cluster's namespace list). Cluster-side captures may
be deferred with `-TODO.png` placeholders if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster). TL;DR ≤150 words written last.
Dossier-link rendering check (use either inline shortcode OR rely on
automatic injection — not both). Set `draft: false`, `status: published`.
CI deploys via the existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md` if a manual
list is maintained (auto-rendered by `papers-roadmap` shortcode in most
cases — skip if so), verify the auto-rendered cross-link chips appear on
Building 14-multi-tenancy and Operating 09-multi-tenancy, update README
only if a stack row changes (Papers are content, not stack — usually
skip), update the spec's Implementation Plans table row, set plan status
to Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
