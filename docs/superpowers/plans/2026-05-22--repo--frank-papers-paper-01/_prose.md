# The Frank Papers — Paper 01: Heterogeneous Hardware as a Design Choice

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Drafting — plan created 2026-05-22 on branch `paper-01`; PR open for human review of plan structure.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 02, 03,
04, 05, 06, 07, 08, 09, 10, 11, 13, 14, 17 published or in review.

Paper 01 is the hardware Paper in the series: 2400–4200 words, the standard
skeleton (§1 capability → §2 landscape → §3 architecture per vendor → §4
scale → §5 Frank's choice → §6 generalization → §7 roadmap), and the first
Paper to confront the *homogeneous-fleet orthodoxy* — the advice every
production SRE absorbs by year two, that mixing CPU architectures, GPU
generations, and node-class lifecycles is the wrong default.

The capability question is: *what do you put in the rack?* — and, more
sharply, *do you buy seven of the same box or seven different boxes?* The
vendor space here is not a list of products but a list of fleet-shape
patterns: all-RPi homelab (PiCluster, k3s on Pis), all-NUC mini-fleet
(Intel-shop standard), heterogeneous bare metal (Frank's choice), edge+core
split (DCs + ROBO), single-beefy-server-with-VMs (Proxmox + LXC, the
default homelab pattern), and full-cloud node-pool-per-shape (EKS Karpenter,
GKE node pools). Six fleet shapes make the landscape, with **deliberate
heterogeneous bare metal — 3× Intel Ultra 5 minis + 1× i9/RTX 5070 Ti +
1× Z77/i5-3570K + 2× RPi 4** — as Frank's case study. The point is the
delta: an ARM Pi schedules workloads differently than an x86 mini, an iGPU
needs DRA wiring that a discrete GPU does not, a 2013 Z77 board reboots
in ways a 2025 NUC15 does not, and that delta is what teaches you what
your scheduler actually does.

The scars are the point. The pc-1 spontaneous-reboot saga (Z77/i5-3570K,
2013 BIOS, 7 reboots in 33 days, PSU-swap-fixed) that consumed a 245-line
investigation to land on "the 12-year-old PSU was browning out under
transient load — retire pc-1 or accept the noise." The gpu-1
`kubectl port-forward` flake — only on gpu-1 — that forced rewriting every
metric-scraping script to use `kubectl exec ... wget -qO-` instead. The
Intel iGPU DRA wiring on mini-1/2/3 that needs K8s 1.35 alpha DRA patches
the upstream `intel-resource-driver-operator` chart doesn't ship. The ARM
vs x86 image-divergence tax on every Helm chart that doesn't publish a
multi-arch manifest. The defensive `nvidia.com/gpu:NoSchedule` toleration
that every gpu-1 pod carries, "in case the operator re-asserts the taint
during driver re-validation" — insurance against a failure mode you only
discover by living through it.

The counter-argument to confront in §5/§6: *every production SRE will tell
you to homogenize the fleet.* They are not wrong. For a fleet running one
workload at scale, identical hardware is cheaper to operate, cheaper to
debug, and cheaper to plan for. Frank's argument is not that they are
wrong; Frank's argument is that *paying the heterogeneity tax is the point
of a learning cluster.* A team that has lived through pc-1's PSU brown-out
will know what node-level health signal to alert on; a team that has only
ever run identical NUCs will not. The decision tree in §6 honours the
production-SRE answer for production-SRE jobs, and Frank's answer for
learning jobs — and a third leaf for "single beefy server + VMs" for the
homelab that doesn't want a real cluster, and a fourth for "just buy AWS"
for the team that wants to skip the hardware question entirely.

## Phase 1: Dossier construction

Six fleet-shape vendors, ≥5 primary sources across ≥3 type values, ≥3
Frank artefacts across ≥2 kinds, the named gap on the absence of any
operator-overhead-per-node-class benchmark at small scale, and the
counter-argument that homogeneous-fleet advice is the right default for
every team whose primary job is to ship a product rather than to learn
infrastructure. Parallel subagents per fleet-shape are appropriate — one
each for all-RPi, all-NUC, heterogeneous bare metal, edge+core split,
single-beefy-server-with-VMs, and full-cloud — with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"the production-SRE answer
is right — homogenize. Why doesn't that win for Frank?"* Same shape as
Paper 04/09's framing applied to the hardware capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram showing where node-class heterogeneity sits between physical hardware and the scheduler
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per fleet-shape with shared visual language (how each shape lays out its node pools: Karpenter NodePool/NodeClass CRDs, Cluster API MachineDeployments, plain kubeadm tags+taints, vCluster sharing one host fleet, all-RPi single-class trivial case)
- §4 What scale changes (300–600 words) + per-node-class operator cost callouts (firmware variance, BIOS variance, driver matrix, image multi-arch tax, what breaks first at 5/50/500 nodes)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (pc-1 PSU brown-out + 245-line investigation, gpu-1 port-forward CNI flake, Intel iGPU DRA wiring)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves (heterogeneous-learning, homogeneous-production, single-beefy-with-VMs, just-buy-AWS)
- §7 Roadmap & where this space is going (200–400 words) — ARM-on-server normalization, Karpenter NodePool taxonomy, DRA stabilization, the "one big box for homelab" counter-trend
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a workbench scattered with mismatched
hardware — a Raspberry Pi next to a discrete RTX 5070 Ti, a Mac mini
stacked on a beige Z77-vintage tower, an Intel NUC perched on a stack of
SODIMMs — with a curious-decision-maker expression. Thin black tie, round
reading glasses. The visual metaphor is *deliberate mismatch as design*.
Mermaid diagrams: §1 stack position, §2 landscape (quadrantChart) +
capability matrix, §3 four-to-six fleet-shape flowcharts, §6 decision
tree. At least one cluster-side capture (the `kubectl get nodes -o wide`
output showing the seven-node fleet with `KERNEL-VERSION`, `OS-IMAGE`,
`CONTAINER-RUNTIME`, `ARCHITECTURE` columns spanning the full
heterogeneity, OR a Grafana node-overview panel showing per-node CPU
families) captured live. Cluster-side captures may be deferred with
`-TODO.png` placeholders if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 01-introduction and
Operating 01-cluster-nodes, update README if relevant, set plan status
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
