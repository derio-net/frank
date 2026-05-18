---
paper: 00-why-homelab-in-2026
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Cloud-native (fully managed)
  positioning: "Let someone else run the metal — focus on code, not ops."
  primary_url: "https://cloud.google.com/kubernetes-engine"
- name: Managed homelab-as-code (k3s / Talos + cloud control-plane)
  positioning: "Own your hardware, outsource cluster lifecycle to a SaaS control plane."
  primary_url: "https://www.siderolabs.com/omni/"
- name: DIY homelab (self-hosted everything)
  positioning: "Own the hardware, the OS, the cluster, and the failure modes."
  primary_url: "https://talos.dev"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Leaving the Cloud — 37signals Cloud Exit case study"
  type: benchmark
  url: "https://basecamp.com/cloud-exit"
  quoted_passages:
    - "37signals pulled Basecamp, HEY, and five other heritage apps out of AWS and onto their own hardware — without adding any new staff. By 2022, their cloud bills had grown to over $3.2 million annually."
    - "Performance improved dramatically, with database queries running 3-5x faster and page load times improving 30-50%."
    - "Total projected savings from the combined cloud exit are well over $10 million over five years. The hardware cost was approximately $600,000 for a one-time purchase."
  relevance: "Canonical real-world cost benchmark of cloud-vs-self-hosted for a stable, predictable workload at small-org scale. Provides hard numbers other practitioners cite. Most directly supports §2 of Paper 00 (real costs of the three approaches)."

- title: "Simon Willison — LLM pricing notes"
  type: postmortem
  url: "https://simonwillison.net/tags/llm-pricing/"
  quoted_passages:
    - "One of the most notable trends from 2024 was the total collapse in terms of LLM pricing — the API models are absurdly inexpensive now."
    - "Generating captions for 68,000 photos using Gemini 1.5 Flash 8B costs $1.68."
  relevance: "Running practitioner log of frontier LLM API price collapse. Critical counterweight to the assumption that 'self-host because cloud inference is expensive' — at most scales the API is now cheaper by an order of magnitude. Supports the counter-argument in §3."

- title: "Do you need Omni? — Sidero Labs"
  type: vendor-docs
  url: "https://www.siderolabs.com/blog/do-you-need-omni"
  quoted_passages:
    - "Omni handles the lifecycle of Talos Linux machines, provides unified access to the Talos and Kubernetes API tied to the identity provider of your choice, and provides a UI for cluster management and operations."
    - "From initial machine registration through cluster creation, day-to-day operations, and rolling upgrades, everything is handled through a single interface."
  relevance: "Vendor's own articulation of where the managed homelab-as-code seam sits. Defines what 'managed control-plane on owned hardware' actually means in practice and what it costs in operational autonomy."

- title: "Kubernetes 101 — Jeff Geerling video series"
  type: talk
  url: "https://kube101.jeffgeerling.com/"
  quoted_passages:
    - "A YouTube streaming series on Kubernetes and container-based infrastructure by Jeff Geerling."
    - "Everything on his site is being served from a Drupal site, which used to run on a Kubernetes cluster of Raspberry Pis in Jeff Geerling's basement."
  relevance: "Highest-visibility practitioner positioning of the DIY-homelab-for-learning thesis. Anchors the framing that real-world clusters built from cheap hardware teach skills that paid courses don't."

- title: "AKS vs EKS vs GKE: What you get with managed Kubernetes-as-a-Service — Fairwinds"
  type: talk
  url: "https://www.fairwinds.com/blog/aks-eks-gke-managed-kubernetes-as-a-service"
  quoted_passages:
    - "Managed Kubernetes services take the complexities of managing Kubernetes clusters and relieve organizations of the underlying infrastructure management tasks. These services automatically handle the installation, configuration, and maintenance of Kubernetes."
    - "When you run Kubernetes yourself, you have to manage everything such as servers, networking, upgrades, and security, which adds significant operational overhead."
  relevance: "Counter-position arguing for cloud defaults. The strongest case for 'why not just use a managed cluster?' that Paper 00 must engage with honestly rather than dismiss."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/root/templates/argocd.yaml"
  date: 2026-03-02
  demonstrates: "The GitOps-everything thesis on Frank: ArgoCD itself is declared via a templated Application CR under the root App-of-Apps chart. Even the cluster's own deployment mechanism lives in the same git repo it manages."

- kind: commit
  path_or_url: "https://github.com/derio-net/frank/commits/main/agents/rules/frank-infrastructure.md"
  date: 2026-02-15
  demonstrates: "The heterogeneous node table — 3× Intel NUC (control-plane), 1× i9+RTX 5070 worker, 1× legacy desktop, 2× Raspberry Pi 4 — encoded as canonical configuration, not legacy free-text. Shows that 'mixed hardware on purpose' is the design point."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-05-18
  demonstrates: "100+ one-line incident summaries from running Frank — each linking to a detailed runbook under docs/runbooks/frank-gotchas/. Concrete operational scar tissue that doesn't exist on a managed cluster: 'manual sync doesn't inherit syncPolicy.syncOptions', 'agents-shell s6-overlay v3 incompatible with shareProcessNamespace: true', 'gpu-1 port-forward flakes with CNI-netns errors'. The kind of knowledge that compounds with operating one's own metal."

## Diagrams planned
- landscape:
    x_axis: "fully managed ↔ self-managed"
    y_axis: "production-oriented ↔ learning-oriented"
    vendors_plotted: ["Cloud-native (GKE/EKS)", "Managed homelab (Omni)", "DIY homelab (Frank)"]
- decision_tree:
    leaves: 4
    description: "Question: should I run a homelab in 2026? Branches on production-vs-learning intent and on team size, terminating in: Cloud, Managed homelab, DIY homelab, or 'don't — the question was wrong'."

## Named gaps (≥1)
- "No standardized TCO methodology for homelab vs cloud at ≤10 concurrent users / ≤$500/mo equivalent spend. All cost comparisons in the literature assume production scale or oversimplify power and hardware amortization. Frank's own cost numbers are anecdotal at best — they cover hardware purchase and electricity but not the operator's time, which is the dominant cost at homelab scale."

## Counter-arguments considered (≥1)
- "Cloud gives instant scale, managed SLAs, and zero capital expenditure — for most teams it is strictly better than a homelab. Why doesn't this win for Frank? Answer: Frank is a learning platform, not a production alternative. The question 'should I run a homelab in 2026?' is meaningless without 'for what purpose?' Cloud wins for production; homelab wins for learning failure modes at depth. Paper 00's job is to make this distinction sharp enough that a reader can tell which question they're actually asking."
