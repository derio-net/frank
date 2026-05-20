---
paper: 05-gpu-scheduling
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: NVIDIA GPU Operator
  positioning: "NVIDIA — vendor-owned operator that bundles driver, container toolkit, device plugin, GFD node labelling, and DCGM exporter; the primary path for discrete NVIDIA cards on Kubernetes."
  primary_url: "https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/overview.html"
- name: Intel GPU Resource Driver (DRA)
  positioning: "Intel — Dynamic Resource Allocation driver for Intel iGPUs and dGPUs; the DRA-native replacement for the legacy Intel device plugin, supporting per-pod GPU partition requests and quota via KEP-4381 structured parameters."
  primary_url: "https://github.com/intel/intel-resource-drivers-for-kubernetes"
- name: AMD ROCm (k8s-device-plugin)
  positioning: "AMD — ROCm-stack device plugin exposing AMD Instinct and consumer Radeon GPUs to Kubernetes via the legacy device-plugin API."
  primary_url: "https://github.com/ROCm/k8s-device-plugin"
- name: NVIDIA MIG / MPS (partitioning)
  positioning: "NVIDIA — Multi-Instance GPU (hardware partition) and Multi-Process Service (software time-slice / spatial share) for partitioning a single physical GPU across multiple workloads with isolated compute and memory."
  primary_url: "https://docs.nvidia.com/datacenter/tesla/mig-user-guide/"
- name: Run.AI
  positioning: "NVIDIA (acquired 2024) — commercial GPU scheduler with fractional GPU allocation, quota trees, and gang scheduling on top of Kubernetes; positioned at multi-tenant AI platforms."
  primary_url: "https://docs.run.ai/"
- name: Volcano scheduler
  positioning: "CNCF Incubating — batch-aware Kubernetes scheduler with gang scheduling, queue-based quota, and GPU-aware placement; the OSS answer to Run.AI's shape."
  primary_url: "https://volcano.sh/en/docs/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "NVIDIA GPU Operator — Overview"
  type: vendor-docs
  url: "https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/overview.html"
  quoted_passages:
    - "The NVIDIA GPU Operator uses the operator framework within Kubernetes to automate the management of all NVIDIA software components needed to provision GPU."
    - "These components include the NVIDIA drivers (to enable CUDA), Kubernetes device plugin for GPUs, the NVIDIA Container Toolkit, automatic node labeling using GFD, DCGM based monitoring and others."
  relevance: "Vendor's authoritative description of what the Operator does — five lifecycle components bundled into a single operator. Grounds the §3 NVIDIA architecture diagram and underwrites the §5 description of Frank's driver.enabled false Talos workaround (driver is the one component the Operator does NOT manage on Frank, because Talos system extensions already provide it)."

- title: "Kubernetes — Dynamic Resource Allocation"
  type: vendor-docs
  url: "https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/"
  quoted_passages:
    - "DRA is a Kubernetes feature that lets you request and share resources among Pods. These resources are often attached devices like hardware accelerators."
    - "These benefits provide significant improvements in the device allocation workflow when compared to device plugins, which require per-container device requests, dont support device sharing, and dont support expression-based device filtering."
  relevance: "Upstream Kubernetes definition of DRA and the explicit contrast with the legacy device-plugin model. Anchors the §2 axis device plugin (legacy) ↔ DRA (KEP-4381) and the §7 roadmap claim that DRA is eating the device-plugin API."

- title: "NVIDIA Multi-Instance GPU (MIG) User Guide"
  type: vendor-docs
  url: "https://docs.nvidia.com/datacenter/tesla/mig-user-guide/"
  quoted_passages:
    - "The Multi-Instance GPU (MIG) User Guide explains how to partition supported NVIDIA GPUs into multiple isolated instances, each with dedicated compute and memory resources."
    - "MIG enables efficient GPU utilization across multiple users or workloads with guaranteed performance."
  relevance: "Vendor's authoritative description of MIG — hardware-level partitioning of a single physical GPU into isolated instances. Source for the §3 MIG/MPS architecture diagram, the §4 fragmentation-cost discussion, and the §6 decision-tree leaf multi-tenant on a single big card."

- title: "Volcano — A Cloud Native Batch System"
  type: paper
  url: "https://volcano.sh/en/docs/"
  quoted_passages:
    - "Volcano is a cloud native system for high-performance workloads, which has been accepted by Cloud Native Computing Foundation (CNCF) as its first and only official container batch scheduling project."
    - "Ensure all tasks of a job start simultaneously, suitable for distributed training and big data scenarios"
  relevance: "CNCF Incubating projects own positioning statement and the gang-scheduling definition. Source for the §3 Volcano architecture diagram and the §6 decision-tree branch multi-tenant batch workloads. Counters the assumption that gang scheduling requires Run.AIs commercial product."

- title: "Intel Resource Drivers for Kubernetes"
  type: vendor-docs
  url: "https://github.com/intel/intel-resource-drivers-for-kubernetes"
  quoted_passages:
    - "Intel resource drivers for Kubernetes is an alternative for Intel device plugins, facilitating workload offloading by providing accelerator access on Kubernetes cluster worker nodes."
    - "The resource drivers are based on Dynamic Resource Allocation (DRA) framework in Kubernetes"
  relevance: "Vendors authoritative positioning of the DRA replacement path for Intel hardware. Underwrites the §3 architecture diagram for the Intel iGPUs on Franks mini-1/2/3 and the §5 case-study claim that DRA is the path Intel has taken first."

- title: "Frank — gpu-1 specifics gotchas (Talos extension dance, NVIDIA taint re-assertion, OLLAMA_KEEP_ALIVE cgroup-RAM, port-forward CNI-netns flakes)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "Pin GPU workloads with nodeSelector kubernetes.io/hostname gpu-1 plus defensive nvidia.com/gpu NoSchedule toleration (insurance against driver re-validation re-asserting the taint)."
    - "Ollama system memory errors mean container cgroup RAM (not VRAM) — OLLAMA_KEEP_ALIVE page cache pins the cgroup near resources.limits.memory."
    - "kubectl port-forward flakes regularly with CNI-netns errors on gpu-1 pods only — use kubectl get application -n argocd -o wide for argocd-cli replacements; use kubectl exec ... wget -qO- for in-pod metrics."
  relevance: "Franks own running postmortem registry — concrete operational scars accumulated while running the NVIDIA GPU Operator + Intel GPU Resource Driver pair in production for this learning platform. Provides source-of-truth dates and recovery commands for the §5 scar callouts and underwrites the §6 decision-tree branches."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "patches/phase04-gpu/gpu-operator-values.yaml"
  date: 2026-03-02
  demonstrates: "The minimal NVIDIA GPU Operator Helm values that work on Talos: driver.enabled false, toolkit.enabled false, hostPaths.driverInstallDir /usr/local, cdi.enabled false. Four overrides that let the upstream Operator chart find Taloss NVIDIA bits at the non-standard /usr/local/glibc/usr/lib64 path. Without them the device plugin cant locate libcuda.so and the GPU never advertises."

- kind: yaml
  path_or_url: "patches/phase04-gpu/04-gpu-nvidia-modules.yaml"
  date: 2026-03-02
  demonstrates: "Talos config patch that loads the nvidia, nvidia_uvm, nvidia_drm, and nvidia_modeset kernel modules on gpu-1 at boot. Required because Taloss immutable kernel-module space cannot be populated by NVIDIAs stock installer; modules must be declared in the machine config and loaded by the kernel at boot."

- kind: yaml
  path_or_url: "patches/phase04-gpu/402-gpu1-nvidia-extensions.yaml"
  date: 2026-03-02
  demonstrates: "Per-machine Omni ExtensionsConfiguration that adds nvidia-container-toolkit and nvidia-open-gpu-kernel-modules as Talos system extensions on gpu-1, alongside the cluster-wide iscsi-tools. Required because per-machine extension configs OVERRIDE the cluster-wide list rather than merge — dropping iscsi-tools here would break Longhorn on gpu-1."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-03-02
  demonstrates: "The NVIDIA driver re-validation re-asserts nvidia.com/gpu NoSchedule after a node restart. Workloads without a defensive toleration silently fail to schedule with Insufficient nvidia.com/gpu. Discovered on the first power-cycle after Phase 4 went live; every GPU workload on Frank now ships the toleration as insurance."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-04-23
  demonstrates: "Ollama reported system memory errors on gpu-1. Not VRAM — the containers cgroup RAM ceiling. OLLAMA_KEEP_ALIVE had pinned the page cache near resources.limits.memory, and the cgroup OOM-killer found it before the model did. Cross-references Paper 10s inference-stack scars; lives at the GPU-scheduling layer because it is a scheduling-tax bug (cgroup limits set by the scheduler interact with the GPU runtimes caching strategy in non-obvious ways)."

- kind: yaml
  path_or_url: "apps/gpu-switcher/manifests/deployment.yaml"
  date: 2026-03-02
  demonstrates: "The in-house gpu-switcher service that brokers exclusive use of gpu-1s RTX 5070 Ti among competing inference workloads (Ollama, ComfyUI, vLLM). A 130-line Deployment + ServiceAccount + ClusterRole/Binding that exposes an HTTP API at 192.168.55.214 for runtime GPU routing — Kubernetes scheduling alone cannot express this workload temporarily owns the card, then releases it without partitioning."

- kind: grafana-screenshot
  path_or_url: "blog/content/docs/papers/05-gpu-scheduling/gpu-utilisation-TODO.png"
  date: 2026-05-20
  demonstrates: "Grafana NVIDIA dashboard panel showing GPU utilisation on gpu-1 during a real Ollama inference workload vs idle baseline. Placeholder pending cluster-side capture."

## Diagrams planned
- landscape:
    x_axis: "Single-vendor ↔ Multi-vendor"
    y_axis: "Device plugin (legacy) ↔ DRA (KEP-4381)"
    vendors_plotted: ["NVIDIA GPU Operator", "Intel GPU Resource Driver", "AMD ROCm device plugin", "NVIDIA MIG / MPS", "Run.AI", "Volcano scheduler"]
- architecture_comparison:
    vendors: ["NVIDIA GPU Operator", "Intel GPU Resource Driver (DRA)", "NVIDIA MIG / MPS", "Volcano scheduler", "Run.AI"]
- decision_tree:
    leaves: 4
    description: "Question who tells the scheduler which pod gets which silicon, and what tax do they charge? Branches on workload-count (single → device plugin alone), heterogeneous-vendor-mix (yes → Operator + Intel DRA), tenant-count (single → Operator + MIG), terminating in device plugin alone, Operator + Intel DRA (Franks pick), Operator + MIG/MPS, Volcano or Run.AI for multi-tenant batch."

## Named gaps (≥1)
- "No apples-to-apples GPU-scheduling tax benchmark exists in the public literature — i.e., a measurement of total operational overhead (Operator CPU/memory per GPU node, MIG fragmentation cost when only some slices are in use, DRA scheduling-latency overhead vs the legacy device plugin, recovery time after a driver re-validation re-asserts the NoSchedule taint, time spent re-pathing CUDA libraries across a non-standard Talos driver path) at small-to-medium cluster scale (1–10 GPU nodes). Published comparisons cover either feature matrices (device plugin vs DRA checklist) or single-dimension benchmarks (MIG isolation overhead in isolation) but never the bundled tax that determines whether GPU scheduling is worth running the full vendor operator at all. The single most useful number for a decision-maker — how many hours per month will the Operator cost you — does not exist as published work."

## Counter-arguments considered (≥1)
- "For a homelab cluster with a single discrete GPU and one workload at a time, the NVIDIA device plugin alone covers the case — why doesnt Frank just stop there? Answer same shape as Paper 14. Frank is a learning platform. Three of the four scars in §5 — the Talos driver-validation refusal, the NVIDIA taint re-assertion after restart, the OLLAMA_KEEP_ALIVE cgroup-RAM error — would also bite a device-plugin-only setup; they are platform-level scars, not Operator-level. The reason to run the full Operator + DRA pair is to encounter the heterogeneous-vendor integration surface first-hand (NVIDIA on gpu-1, Intel iGPUs on mini-1/2/3) and to be able to compose with a future partitioning controller (MIG) or batch scheduler (Volcano) without re-architecting. A team that has internalised these lessons can rationally skip the Operator and ship the device plugin alone; a team that has not will reinvent the same scars at production scale, where the cost of discovery is measured in customer SLO breaches rather than a Grafana panel turning red. The counter-argument wins for the team that has already paid the tuition; for Frank, paying the tuition is the point."
