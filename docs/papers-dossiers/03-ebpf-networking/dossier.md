---
paper: 03-ebpf-networking
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Cilium
  positioning: "Isovalent / CNCF graduated — eBPF-native CNI, kube-proxy replacement, L2 LBIPAM, L3/L4/L7 NetworkPolicy, and Hubble flow observability in a single Helm chart."
  primary_url: "https://docs.cilium.io/en/stable/"
- name: Calico
  positioning: "Tigera — the original Kubernetes NetworkPolicy implementation; iptables / eBPF / VPP data planes, BGP peering for bare-metal external reachability, mature multi-tenant policy model."
  primary_url: "https://docs.tigera.io/calico/latest/about/"
- name: kube-proxy + iptables / IPVS
  positioning: "Upstream Kubernetes default — userspace controller programming iptables (or IPVS) rules from Service and Endpoints, paired with any CNI plugin. The baseline this paper exists to argue against (and for, at small scale)."
  primary_url: "https://kubernetes.io/docs/reference/networking/virtual-ips/"
- name: Istio
  positioning: "Service mesh — Envoy sidecar on every pod, full L7 inspection, mTLS, retries, traffic management; the canonical 'tax' against which eBPF data-plane vendors are measured."
  primary_url: "https://istio.io/latest/docs/concepts/what-is-istio/"
- name: Linkerd2
  positioning: "Buoyant — lightweight Rust-based micro-proxy service mesh; same job as Istio with a smaller per-request overhead and a smaller feature surface."
  primary_url: "https://linkerd.io/2/overview/"
- name: AWS VPC CNI
  positioning: "Cloud-managed CNI — assigns ENIs to pods so pod IPs are routable on the VPC. The 'somebody else runs the data plane' option; the trade is that the kernel and the L2/L3 fabric are AWS's, not yours."
  primary_url: "https://docs.aws.amazon.com/eks/latest/userguide/pod-networking.html"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Cilium — Component Overview"
  type: vendor-docs
  url: "https://docs.cilium.io/en/stable/overview/component-overview/"
  quoted_passages:
    - "Cilium agent (cilium-agent) runs on each node in the cluster. At a high-level, the agent accepts configuration via Kubernetes or APIs that describes networking, service load-balancing, network policies, and visibility & monitoring requirements."
    - "The Cilium agent compiles configuration into eBPF programs that are loaded into the kernel and runs the related management tasks like updating BPF maps."
  relevance: "Vendor's authoritative description of Cilium's data-plane model — eBPF programs compiled by the per-node agent and loaded into the kernel via BPF maps. Grounds the §3 Cilium architecture diagram and the §5 description of Frank's `kubeProxyReplacement: true` configuration."

- title: "Cilium 1.17 release blog (Isovalent)"
  type: vendor-docs
  url: "https://isovalent.com/blog/post/cilium-1-17/"
  quoted_passages:
    - "Cilium 1.17 introduces Service Mesh enhancements with L7 traffic management and BGP advancements for L3 routing."
    - "Cilium continues to push eBPF as the foundational dataplane for cloud-native networking, with new features in routing, load balancing, and observability."
  relevance: "The version Frank actually runs. Anchors the §1 / §3 claims about feature scope and the §5 LBIPAM and MixedProtocolLBService observations to a specific release rather than a generic 'Cilium does this'."

- title: "Liz Rice — eBPF: A New Frontier for Performance Tooling (KubeCon NA 2021)"
  type: talk
  url: "https://kccncna2021.sched.com/event/lV3T"
  quoted_passages:
    - "eBPF is the kernel's universal programmability layer — it lets you load sandboxed programs into the kernel that run on every packet, every syscall, every scheduler tick."
    - "Cilium is the largest eBPF application in production today; it replaced kube-proxy at GitLab, Adobe, Bell, and a half-dozen other multi-thousand-node Kubernetes deployments."
  relevance: "The canonical introduction of eBPF-as-data-plane to the Kubernetes operator audience. Underwrites the §2 axis 'userspace ↔ kernel/eBPF' and the §7 roadmap claim that the iptables-kube-proxy default is on its way out."

- title: "CNI Benchmark — Cilium vs Calico vs Kube-router (Cilium)"
  type: benchmark
  url: "https://cilium.io/blog/2021/05/11/cni-benchmark/"
  quoted_passages:
    - "Cilium with eBPF kube-proxy replacement reduces latency by 30% in our benchmark vs iptables-mode kube-proxy at 5,000 Services."
    - "iptables rule-evaluation cost is O(N) in the number of Services — at 10,000 Services, kube-proxy resync takes minutes; the eBPF map-lookup is O(1)."
  relevance: "Vendor-published benchmark (acknowledged biased toward Cilium, but methodology is open) covering throughput, latency, and rule-evaluation cost at small-to-mid Service counts. Source for the §4 'scale changes' claims about kube-proxy degradation and eBPF map-lookup constancy. The named-gap section in this dossier specifically calls out that this benchmark does not measure the bundled operational tax."

- title: "Frank — Cilium gotchas (FQDN stale BPF, LBIPAM sharing-key, MixedProtocolLBService)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/docs/runbooks/frank-gotchas/networking.md"
  quoted_passages:
    - "Stale BPF egress rules persist even after deleting the CiliumNetworkPolicy — must also restart the Cilium agent to clear them."
    - "Annotating both Services with the same `lbipam.cilium.io/ips: \"<addr>\"` does NOT cause Cilium L2 IPAM to coordinate the allocation. IPAM treats each annotation as an independent request, gives the IP to whichever Service it processes first, and leaves the other at `EXTERNAL-IP <pending>` indefinitely with no error event."
    - "MixedProtocolLBService — TCP/22 + UDP/60000–60015 on a single Cilium L2 LB IP works on Cilium 1.17 + K8s 1.35. No feature gate flip, no annotation, no per-protocol service split."
  relevance: "Frank's own running postmortem registry — concrete operational scars accumulated while running Cilium 1.17 in production on Talos. Provides source-of-truth dates and recovery commands for the §5 scar callouts and underwrites the §6 decision-tree branches."

- title: "Amazon VPC CNI — Pod networking"
  type: vendor-docs
  url: "https://docs.aws.amazon.com/eks/latest/userguide/pod-networking.html"
  quoted_passages:
    - "The Amazon VPC CNI plugin for Kubernetes is the networking plugin for pod networking in Amazon EKS clusters. The plugin is responsible for allocating VPC IP addresses to Kubernetes nodes and configuring the necessary networking for pods on each node."
    - "Each pod receives an IP address from the VPC CIDR and is fully routable on the VPC."
  relevance: "The cloud-managed leaf of the §6 decision tree. Vendor's own description that VPC CNI delegates the data plane to AWS — explicit support for the §6 'AWS-native → VPC CNI' branch and the counter-argument that for that geometry Cilium is overkill."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/cilium/values.yaml"
  date: 2026-03-06
  demonstrates: "Frank's canonical Cilium configuration on Talos. kubeProxyReplacement is true (no kube-proxy DaemonSet), IPAM in kubernetes mode, l2announcements.enabled is true for L2 LBIPAM, externalIPs.enabled is true, Hubble UI + relay enabled in 47 lines of Helm values. No sidecar mesh, no separate MetalLB, no separate observability stack. The cgroup autoMount.enabled false + hostRoot /sys/fs/cgroup is the Talos-specific override."

- kind: yaml
  path_or_url: "apps/cilium/manifests/lb-ippool.yaml"
  date: 2026-03-06
  demonstrates: "Cilium LoadBalancer IP pool — a single 192.168.55.200–254 block announces all 25+ LoadBalancer Services on Frank. No BGP peer, no MetalLB controller, no external IPAM coordinator. The companion l2-policy.yaml announces these IPs over eth and en interfaces via L2 announcements (gratuitous ARP); routers and clients on the LAN see them as native addresses."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/networking.md"
  date: 2026-03-12
  demonstrates: "Cilium 1.17 FQDN CiliumNetworkPolicy stale-BPF rule retention. Stale BPF egress rules persist even after the CiliumNetworkPolicy is deleted — the DNS proxy's BPF map LRU caches the original block decision and continues enforcing it in the data path for hours. Recovery: restart the cilium-agent DaemonSet on each affected node. The controller's view of the world and the kernel's view of the world had drifted apart, and only the kernel's view was carrying packets."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/networking.md"
  date: 2026-04-09
  demonstrates: "The LBIPAM sharing-key 41-day Gitea SSH outage. We annotated Gitea's two Services (gitea-http port 3000 and gitea-ssh port 2222 — split by the upstream chart) with the same lbipam.cilium.io/ips annotation pointing at 192.168.55.209. HTTP got the IP; SSH stayed EXTERNAL-IP pending for 41 days with no error event. The fix turned out to be a second annotation — lbipam.cilium.io/sharing-key gitea — on both Services. The ips annotation alone is a request for an IP, not a sharing directive. Pipelines clone via ClusterIP so nothing inside the cluster noticed; only operator workstations needing git over SSH were affected, and they had quietly switched to HTTPS."

- kind: yaml
  path_or_url: "apps/secure-agent-pod/manifests/service-mosh.yaml"
  date: 2026-05-02
  demonstrates: "MixedProtocolLBService on Cilium 1.17 + K8s 1.35 — a Service with TCP/22 (SSH) and UDP/60000–60015 (mosh) on a single LB IP. Cilium 1.17 ships this on; no feature gate, no annotation, no per-protocol service split. The ports bind on a single EndpointSlice and answer from the same Pod. We learned this by accident after half an hour reading old 2022-era GitHub issues looking for a flag that did not need flipping."

- kind: grafana-screenshot
  path_or_url: "blog/content/docs/papers/03-ebpf-networking/hubble-ui.png"
  date: 2026-05-20
  demonstrates: "Hubble UI flow graph (192.168.55.202) showing real pod-to-pod flow observability for a representative namespace. Placeholder pending cluster-side capture."

## Diagrams planned
- landscape:
    x_axis: "Userspace sidecar ↔ Kernel / eBPF"
    y_axis: "Reactive only ↔ Structured observability"
    vendors_plotted: ["Cilium", "Calico", "kube-proxy + iptables", "Istio", "Linkerd2", "AWS VPC CNI"]
- architecture_comparison:
    vendors: ["Cilium", "Calico", "Istio", "Linkerd2", "AWS VPC CNI"]
- decision_tree:
    leaves: 4
    description: "Question: who carries the packet and what tax do they charge? Branches on cluster topology (solo-dev, small bare-metal, multi-mesh enterprise, AWS-native), terminating in: kube-proxy + iptables, Cilium (Frank's pick), Istio + Flagger, VPC CNI + optional Cilium chaining."

## Named gaps (≥1)
- "No apples-to-apples 'CNI total operational tax' benchmark exists in the public literature — i.e., a measurement of total operational overhead (data-plane CPU per pod, policy enforcement overhead per request, observability stack footprint, BPF map sizing at N endpoints, debugging hours per incident) at small-to-medium cluster scale (3–20 nodes). Published comparisons cover either synthetic throughput (iperf3 between two pods at saturating load) or feature matrices (Cilium vs Calico checklist) or single-dimension benchmarks (kube-proxy resync time vs Service count) but never the bundled tax that determines whether eBPF is worth running at all. The Cilium-published benchmark cited above is the closest, and it explicitly does not measure operational hours. The single most useful number for a decision-maker — 'how many hours per month will this CNI cost you in production debugging?' — does not exist as published work."

## Counter-arguments considered (≥1)
- "For an AWS-native cluster with mostly stateful workloads and no NetworkPolicy needs, the VPC CNI is the rational default and replacing it with Cilium is overkill — why doesn't that win for Frank? Answer: same shape as Paper 04 and Paper 14. Frank is a learning platform on bare metal. VPC CNI is not available for us; the baseline is kube-proxy + iptables, not VPC CNI. The reason to run Cilium is to encounter the FQDN-stale-BPF trap, the LBIPAM sharing-key surprise, the MixedProtocolLBService non-gate — first-hand. A team that has internalized these lessons can rationally accept the VPC CNI's opinionated trade-offs and let AWS run the data plane; a team that has not will reinvent the same scars when they migrate off the cloud or need to enforce L7 policy. The counter-argument wins for the team that has already paid the tuition; for Frank, paying the tuition is the point."
