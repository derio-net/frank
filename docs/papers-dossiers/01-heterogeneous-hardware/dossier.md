---
paper: 01-heterogeneous-hardware
status: draft
---

## Vendors in scope (≥3, typically 4–6)
- name: All-RPi homelab (PiCluster / k3s on Pis)
  positioning: "ARM-only, identical SBC fleet — cheapest entry, demonstrates clustering as a learning artefact; production-unsuitable for anything CPU-heavy. The 'one image, one driver matrix' homogeneous-fleet shape on the lowest-cost hardware."
  primary_url: "https://github.com/geerlingguy/turing-pi-cluster"
- name: All-NUC mini-fleet (Intel-shop standard)
  positioning: "Identical x86 mini-PCs as a homogeneous fleet — single image, single driver matrix, single firmware story. The production-SRE default for small fleets where the workload is bounded."
  primary_url: "https://www.intel.com/content/www/us/en/products/details/nuc.html"
- name: Heterogeneous bare metal (Frank's choice)
  positioning: "Deliberately mixed node classes — mini-PCs as control plane, gaming PC for discrete GPU, 12-year-old Z77 box for legacy workloads, RPi for low-power edge — to surface scheduler and operator-cost deltas under one cluster."
  primary_url: "https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/"
- name: Edge+core split (DCs + ROBO)
  positioning: "Heterogeneous by topology, not by intent — beefy core fleet plus thin edge nodes (KubeEdge / OpenYurt / k3s edge agents) that connect over WAN. The shape that 'real' enterprise edge deployments converge on."
  primary_url: "https://kubeedge.io/docs/"
- name: Single beefy server + VMs (Proxmox + LXC)
  positioning: "The homelab default — one large bare-metal host, VMs/LXC as fake nodes. Skips real-hardware heterogeneity at the cost of skipping the lessons it teaches; perfectly rational if Kubernetes-as-software is the goal and Kubernetes-as-hardware-curriculum isn't."
  primary_url: "https://pve.proxmox.com/wiki/Linux_Container"
- name: Full-cloud node-pool-per-shape (EKS Karpenter / GKE node pools)
  positioning: "Heterogeneity outsourced — node shapes declared as Karpenter NodePool/NodeClass CRDs, cloud provisions on demand. Same scheduler problem, no hardware visible to the operator."
  primary_url: "https://karpenter.sh/docs/concepts/nodepools/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Kubernetes docs — Assigning Pods to Nodes (nodeSelector, taints, tolerations, affinity)"
  type: vendor-docs
  url: "https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/"
  quoted_passages:
    - "You can constrain a Pod so that it is restricted to run on particular node(s), or to prefer to run on particular nodes."
    - "Taints are the opposite — they allow a node to repel a set of pods. Tolerations are applied to pods. Tolerations allow the scheduler to schedule pods with matching taints. Tolerations allow scheduling but don't guarantee scheduling."
  relevance: "The canonical vocabulary for expressing 'these pods run on these node classes' — every heterogeneous fleet uses this surface, whether the labels come from per-node Talos patches (Frank), Karpenter NodeClaim provisioning, or Cluster API MachineDeployment template inheritance. §1 and §3 anchor on this primitive."

- title: "Karpenter docs — NodePools and NodeClasses"
  type: vendor-docs
  url: "https://karpenter.sh/docs/concepts/nodepools/"
  quoted_passages:
    - "NodePools set constraints on the nodes that can be created by Karpenter and the pods that can run on those nodes."
    - "It is recommended to create NodePools that are mutually exclusive. So no Pod should match multiple NodePools. If multiple NodePools are matched, Karpenter will use the NodePool with the highest weight."
    - "Karpenter recommends using as few NodePools as possible to keep your configuration simple and manageable."
  relevance: "Karpenter's own doc explicitly couples heterogeneity to operator cost — 'as few NodePools as possible'. That's the cloud-managed-fleet analogue of Frank's tax-on-classes argument; §4 cites this directly when characterising the per-node-class operator cost that the literature implies but does not measure."

- title: "Cluster API — Concepts (MachineDeployments, MachineSets, Machines)"
  type: vendor-docs
  url: "https://cluster-api.sigs.k8s.io/user/concepts"
  quoted_passages:
    - "A 'machine' is the declarative spec for an infrastructure component hosting a Kubernetes Node (for example, a VM)."
    - "A MachineDeployment provides declarative updates for Machines and MachineSets."
  relevance: "The other major CRD-based heterogeneity surface. Cluster API's MachineDeployment-per-class pattern is what the bare-metal world converges on as it grows past the talosctl-per-node regime. §3 contrasts it with Frank's per-node Talos patches and Karpenter's NodePool CRDs as three points on the same 'declare your node classes' axis."

- title: "Talos Linux v1.10 — Managing Kubernetes nodes via Talos machine config"
  type: vendor-docs
  url: "https://www.talos.dev/v1.10/kubernetes-guides/configuration/managing-nodes/"
  quoted_passages:
    - "Talos provides built-in support for managing Kubernetes node labels, annotations, and taints via Talos machine configuration."
    - "Node labels, annotations and taints managed via Talos take precedence over the values set on the node directly. They are reconciled to the desired state on each Talos restart."
  relevance: "The mechanism that Frank actually uses to declare its seven-node, four-hardware-class fleet — one machine-config patch per node under `patches/phase01-node-config/`. Demonstrates that the heterogeneous-bare-metal shape doesn't require Cluster API or Karpenter at small N; the OS can carry the role/zone/hardware label schema."

- title: "Raspberry Pi Cluster Episode 3 — Installing K3s Kubernetes on the Turing Pi (Geerling, 2020)"
  type: benchmark
  url: "https://www.jeffgeerling.com/blog/2020/installing-k3s-kubernetes-on-turing-pi-raspberry-pi-cluster-episode-3/"
  quoted_passages:
    - "K3s is purpose-built for low-power, small-form-factor compute clusters like the Turing Pi, since it is lighter than the full-fat K8s, requires much less in the way of resources to operate, and was easier to set up."
    - "I'm able to deploy K3s to the cluster, and it works well enough... but there are still some quirks I'd like to iron out, especially when it comes to the slower Pi 3 B+ compute modules I'm using on this Turing Pi."
  relevance: "The reference work for the all-RPi homelab fleet shape — including the candid 'works well enough … some quirks' note that anchors the §2 claim about what the all-Pi fleet teaches and what it cannot. The 'slower Pi 3 B+ … some quirks' admission is itself an argument for why even the ostensibly-homogeneous Pi fleet pays a tax on the day one Pi differs from the others."

- title: "Frank cluster gotcha registry (frank-gotchas.md)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "kubectl port-forward flakes regularly with CNI-netns errors on gpu-1 pods only — use `kubectl get application -n argocd -o wide` for argocd-cli replacements; use `kubectl exec ... wget -qO-` for in-pod metrics."
    - "Pin GPU workloads with `nodeSelector: kubernetes.io/hostname: gpu-1` + defensive `nvidia.com/gpu:NoSchedule` toleration (insurance against driver re-validation re-asserting the taint)."
  relevance: "Frank's own running ledger of per-node-class failure modes — the gpu-1-only port-forward flake, the defensive NoSchedule toleration pattern, the Ollama-cgroup-memory pitfall. Every entry is direct evidence that a heterogeneous fleet pays a per-class operator tax that a homogeneous fleet wouldn't; §3 and §5 cite this for the scar callouts."

- title: "pc-1 reboot investigation (2026-05-11) — 245-line root-cause writeup"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/docs/investigations/2026-05-11--hw--pc-1-reboot-investigation.md"
  quoted_passages:
    - "pc-1 has rebooted 7 times in the last 33 days (window: 2026-04-04 → 2026-05-07), with no kernel panic, no OOM kill, no watchdog event, and no thermal trip recorded."
    - "Verdict: hardware-class fault. Best-fit single-cause hypothesis is a deteriorating 2013-era ATX PSU (Corsair / OCZ-era unit, well past typical 7–10 year capacitor service life) browning out under transient CPU load."
  relevance: "The canonical pc-1 scar — and the structural argument for keeping it in the fleet despite the failure. A homogeneous fleet of 2025-vintage mini-PCs would never have surfaced a 'silent reset faster than printk' failure mode; the heterogeneous fleet did, and the investigation that resulted is itself a deliverable. §5's first scar callout is this incident."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "agents/rules/frank-infrastructure.md + patches/phase01-node-config/"
  date: 2026-05-11
  demonstrates: "The declarative shape of a deliberately heterogeneous fleet: a seven-node table (3× Intel Ultra 5 minis, 1× i9+RTX 5070 Ti, 1× Z77/i5-3570K, 2× RPi 4) plus the per-node Talos label patches under `patches/phase01-node-config/03-labels-{mini-1,mini-2,mini-3,gpu-1,pc-1,raspi-1,raspi-2}.yaml`. The label schema (kubernetes.io/role, frank/zone, frank/hardware) is the surface every nodeSelector keys against; the per-node-patch shape is what an at-scale fleet would express in Karpenter NodePool CRDs or Cluster API MachineDeployments."

- kind: yaml
  path_or_url: "patches/phase04-gpu/ + patches/phase05-mini-config/"
  date: 2026-04-01
  demonstrates: "Two different GPU stories, in one cluster, both declarative — and not reusable for each other. The NVIDIA stack on gpu-1 runs the operator with nvidia-container-runtime as default; the Intel iGPU stack on mini-1/2/3 runs a vendored DRA driver chart with K8s 1.35 alpha DRA patches that the upstream `intel-resource-driver-operator` chart doesn't ship. Each took its own integration pass. That's the heterogeneity tax in concrete declarative form: a single 'GPU layer' label on the fleet hides two completely separate driver matrices."

- kind: incident
  path_or_url: "docs/investigations/2026-05-11--hw--pc-1-reboot-investigation.md"
  date: 2026-05-11
  demonstrates: "A 2013 Gigabyte Z77X-UD3H with an i5-3570K and a 12-year-old PSU rebooting 7 times in 33 days. 245 lines across VictoriaMetrics history, kernel ring buffer via privileged debug pod, hardware DMI inventory, and ECC absence — to land on 'the PSU was browning out under transient load.' PSU-swapped 2026-05-07; soak clean. A homogeneous fleet of 2025 NUCs would not have surfaced this failure mode at all; a learning cluster that includes pc-1 surfaces it whether you wanted to learn it or not — and the investigation is itself the lesson."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/gpu-1.md"
  date: 2026-04-12
  demonstrates: "Only gpu-1's network namespace exhibits 'failed to execute portforward in network namespace cni-…: read: connection reset by peer'. Every metric-scraping script that worked on minis had to be rewritten as `kubectl exec ... wget -qO-` for gpu-1. A homogeneous fleet would not have this per-host class of bug — and would not have taught the engineer to write exec-based scrape scripts in the first place, a habit that pays off the day production has the same flake under a different name."

- kind: yaml
  path_or_url: "apps/* (defensive nvidia.com/gpu:NoSchedule tolerations on every gpu-1 pod — ollama, n8n, openrgb, secure-agent-pod, paperclip values.yaml)"
  date: 2026-03-15
  demonstrates: "Insurance against the GPU operator re-asserting the taint on driver re-validation — a failure mode you only know to defend against after you have lived through it once. A homogeneous fleet of identical GPU nodes would have either always-on or never-on taints (simple); a fleet with one GPU node and six non-GPU nodes has to manage the window in which the taint flips and a pod without the toleration gets evicted. The pattern is repeated across half a dozen app values.yaml files — that repetition is the visible cost of the heterogeneity."

## Diagrams planned
- stack_position:
    type: "flowchart LR"
    description: "Where node-class heterogeneity sits in the stack — between physical hardware (board / PSU / firmware) and the K8s scheduler, branching out into the five jobs fleet-shape does at once: capacity, failure isolation, workload specialization, operator-cost surface, learning surface."
- landscape:
    x_axis: "single-class ↔ multi-class"
    y_axis: "bare metal ↔ cloud-managed"
    vendors_plotted: ["All-RPi homelab", "All-NUC mini-fleet", "Heterogeneous bare metal (Frank)", "Edge+core split", "Single beefy server + VMs", "Full-cloud node-pool-per-shape"]
- capability_matrix:
    rows: ["All-RPi homelab", "All-NUC mini-fleet", "Heterogeneous bare metal (Frank)", "Edge+core split", "Single beefy server + VMs", "Full-cloud node-pool-per-shape"]
    columns: ["identical_image", "single_driver_matrix", "per_node_class_cost", "arch_diversity", "gpu_diversity", "cloud_outsourced", "real_hardware_lessons", "small_scale_fit"]
- architecture_comparison:
    vendors: ["All-RPi homelab", "All-NUC mini-fleet", "Heterogeneous bare metal (Frank)", "Edge+core split", "Full-cloud node-pool-per-shape"]
    diagram_type: "flowchart TD per shape, shared visual language (squares=physical, rounded=K8s primitives, diamonds=scheduler decisions, cylinders=fleet state, dashed=provisioning, solid=runtime)"
- decision_tree:
    leaves: 4
    description: "Question: same boxes or different boxes? Branches on (a) is the primary job shipping a product at scale or learning infrastructure, (b) do you want real-hardware failure modes in scope, (c) is cloud acceptable — terminating in: homogenize (all-NUC or full-cloud one-shape), heterogeneous bare metal (Frank), single beefy server + VMs, full-cloud node-pool-per-shape."

## Named gaps (≥1)
- "No published apples-to-apples benchmark of operator-overhead-per-node-class exists at small scale (5–20 nodes). Vendor comparisons cover per-node throughput (CPU benchmarks, network throughput, GPU TFLOPS) and single-dimension TCO models (cloud vs on-prem at fleet size N). What the literature does not cover: how many operator-hours per quarter does each additional *class* of node cost — firmware-update hour, driver-matrix hour, image multi-arch hour, per-class on-call paging hour? Karpenter's own docs acknowledge the cost implicitly ('use as few NodePools as possible') but do not measure it. The closest analogue is the SRE-book chapter on toil, applied per fleet partition; no one has done that exercise for the heterogeneous-homelab regime. Without that benchmark, the homogeneous-fleet advice is asserted, not proven — defensible as a default, but not as a derivation."

## Counter-arguments considered (≥1)
- "Every production SRE will tell you to homogenize the fleet. They are not wrong — for a fleet running one workload at scale, identical hardware is cheaper to operate, cheaper to debug, cheaper to plan capacity for, and lets a single golden image cover every machine. Why doesn't that win for Frank? Same shape as Paper 04/09. Frank is a learning platform. The reason to run a mixed ARM-and-x86, iGPU-and-dGPU, 2013-Z77-and-2025-Ultra-5 fleet under one scheduler is to encounter the pc-1 PSU brown-out, the gpu-1 port-forward CNI flake, the Intel iGPU DRA wiring, the multi-arch image divergence — first-hand. A team that has lived through these will recognize the failure-mode signal in production; a team that has only ever run identical NUCs will alert on the wrong things. The counter-argument wins for the team that has already paid the tuition (or for the team whose primary job is shipping a product, not learning infrastructure); for Frank, paying the tuition is the point. There is also a third leaf — for the homelab that doesn't want a real cluster, 'single beefy server + VMs' is the rational choice — and a fourth for 'just buy AWS', which is right for the team that wants to skip the hardware question entirely. Each is a legitimate answer to a differently-shaped question."
