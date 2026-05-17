---
paper: 00-why-homelab-in-2026
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Cloud-native (fully managed Kubernetes)
  positioning: "Let someone else run the metal — focus on code, not ops."
  primary_url: "https://cloud.google.com/kubernetes-engine"
- name: Managed homelab-as-code (Talos + Omni cloud control-plane)
  positioning: "Own your hardware, outsource cluster lifecycle to a SaaS control plane."
  primary_url: "https://www.siderolabs.com/omni"
- name: DIY homelab (self-hosted everything, no managed control plane)
  positioning: "Own the hardware, the OS, the cluster, and the failure modes."
  primary_url: "https://www.talos.dev"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Kubernetes Total Cost of Ownership: Self-Managed vs. Managed Provider"
  type: benchmark
  url: "https://gcore.com/learning/kubernetes-tco-comparison"
  quoted_passages:
    - "The total cost of ownership of self-managed Kubernetes is about three times higher than that of managed Kubernetes."
    - "Self-hosted: $335,238/yr (infrastructure $13,737 + 3 engineers); Managed: $113,325/yr (infrastructure $6,157 + 1 engineer)"
  relevance: "Primary TCO benchmark comparing cloud-managed vs self-hosted Kubernetes, establishing the cost multiplier for the 'cloud is cheaper' argument."

- title: "IT orgs face tricky cost calculus for self-hosted AI inference"
  type: postmortem
  url: "https://www.techtarget.com/searchitoperations/news/366642991/IT-orgs-face-tricky-cost-calculus-for-self-hosted-AI-inference"
  quoted_passages:
    - "It is difficult to evaluate consistently all the costs."
    - "Nearly 50% of 400 respondents use open-source AI models, with on-premises deployment cited by 18% as a cost-reduction strategy."
  relevance: "Real-world enterprise evidence (BNP Paribas at 1.5B tokens/day, Northrop Grumman) that self-hosted AI inference cost calculations remain contested and scale-dependent — supports the 'no clean answer' thesis of Paper 00."

- title: "Talos Linux — The Kubernetes Operating System"
  type: vendor-docs
  url: "https://www.talos.dev"
  quoted_passages:
    - "API-Driven Management: Use one convenient set of APIs to get automatic updates, add nodes to your Kubernetes clusters, and change configuration."
    - "Create, upgrade, or redeploy an entire cluster in minutes."
  relevance: "Canonical vendor positioning for the DIY homelab-as-code approach (Talos). Demonstrates the immutable, API-driven philosophy that Frank is built on."

- title: "Bare-metal Kubernetes with K3s"
  type: talk
  url: "https://blog.alexellis.io/bare-metal-kubernetes-with-k3s/"
  quoted_passages:
    - "Working through network configuration, BGP routing, and high-availability setup teaches infrastructure fundamentals applicable across environments."
    - "A Raspberry Pi homelab has been a valuable learning playground for CNCF technology."
  relevance: "Alex Ellis (founder of OpenFaaS, widely read in the Kubernetes practitioner community) makes the canonical argument for bare-metal homelab as learning infrastructure — the 'who actually does this and why' reference."

- title: "Kubernetes: Self-Hosted or Managed? The Real Math"
  type: benchmark
  url: "https://hidora.io/en/blog/kubernetes-self-hosted-vs-managed"
  quoted_passages:
    - "The single biggest hidden cost of self-hosted Kubernetes is people."
    - "For most organizations with fewer than 5 Kubernetes clusters, managed wins financially."
  relevance: "Counter-position with supporting data: managed Kubernetes wins on cost for small organizations. Used directly in the 'when Frank's answer doesn't generalize' section — the decision flowchart leaves."

- title: "Omni — Kubernetes Multi-Cluster Management by Sidero Labs"
  type: vendor-docs
  url: "https://www.siderolabs.com/omni"
  quoted_passages:
    - "Omni is the best way to run Talos securely and at scale. Fully API driven and with a modern UI with single sign-on, auditing, and more."
    - "A foundational system for centrally managing multiple Kubernetes clusters running on Talos Linux."
  relevance: "Vendor positioning for the 'managed homelab-as-code' middle option — own the hardware but use a SaaS control plane. Directly relevant to Frank's own architecture (Frank uses self-hosted Omni on Hetzner)."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/root/templates/argocd.yaml"
  date: 2026-03-02
  demonstrates: "GitOps-everything approach: the ArgoCD Application CR for ArgoCD itself, showing multi-source Helm (upstream chart + $values ref), self-heal, ServerSideApply, and ignoreDifferences on the Secret — the pattern applied to every app in the cluster."

- kind: yaml
  path_or_url: "patches/phase01-node-config/03-labels-gpu-1.yaml"
  date: 2026-03-02
  demonstrates: "Heterogeneous hardware declared as code via Omni ConfigPatch: zone=ai-compute, accelerator=nvidia, model-server=true. Contrasts with 03-labels-raspi-{1,2}.yaml (zone=edge, no accelerator) — same API, radically different hardware profiles."

- kind: commit
  path_or_url: "https://github.com/derio-net/frank/commit/26d7d08f44f63f4d3bab4dde21c3ff5976eef089"
  date: 2026-03-02
  demonstrates: "Initial cluster scaffold commit: all 7 nodes (mini-1/2/3 control-plane, gpu-1 AI compute, pc-1 general, raspi-1/2 edge) with per-node Omni ConfigPatches for labels, GPU Nvidia kernel module patch, and full runbook. The moment the cluster became 'Frank' rather than a spec."

## Diagrams planned
- landscape:
    x_axis: "operational complexity (low ↔ high)"
    y_axis: "capital expenditure (none ↔ high)"
    vendors_plotted:
      - "Cloud-native (GKE/EKS/AKS)"
      - "Managed homelab-as-code (Talos + Omni)"
      - "DIY homelab (Talos self-hosted)"
- decision_tree:
    leaves: 4
    description: "Should you run a homelab in 2026? Branches on: learning-vs-production intent, team size, existing cloud spend, hardware ownership preference."

## Named gaps (≥1)
- "No standardized TCO methodology for homelab vs cloud at ≤10 concurrent users / ≤$500/mo equivalent spend. All cost comparisons in the literature assume production scale (tens of engineers, thousands of nodes) or oversimplify power and hardware amortization. A rigorous per-experiment TCO at Frank's scale (7 nodes, 1 operator, €120/mo power) does not exist in the primary literature."

## Counter-arguments considered (≥1)
- "Cloud gives instant scale, managed SLAs, and zero capital expenditure — for most teams it is strictly better than a homelab. The TCO data bears this out: 3× more expensive, 3× more engineers. Why doesn't this win for Frank? Answer: Frank is a learning platform, not a production alternative. The question 'should I run a homelab in 2026?' is meaningless without 'for what purpose?' Cloud wins for production; homelab wins for learning failure modes at depth. The same hardware that makes cloud cheaper (abstraction, automation, SLAs) is exactly what prevents the operator from encountering the failure modes worth understanding."
