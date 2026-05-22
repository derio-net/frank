---
paper: 12-multi-tenancy-vcluster
status: draft
---

## Vendors in scope (≥3, typically 4–6)
- name: Plain namespaces + RBAC + Cilium NetworkPolicies
  positioning: "The null hypothesis — one shared control plane, tenants are namespaces, isolation is RBAC + NetworkPolicy + ResourceQuota + LimitRange. Zero per-tenant runtime cost. This is what most clusters actually run."
  primary_url: "https://kubernetes.io/docs/concepts/security/multi-tenancy/"
- name: vCluster (Loft Labs)
  positioning: "Virtual K8s control plane (API server + controller manager + SQLite or etcd) per tenant, running as a StatefulSet inside a host namespace. Tenants see a full K8s API, install CRDs, manage their own RBAC; the host syncs pods to its own nodes. Frank's pick for the sandbox shape."
  primary_url: "https://www.vcluster.com/docs/vcluster"
- name: Kamaji (Clastix)
  positioning: "Control-plane-as-a-service — Kamaji runs a controller that materializes tenant control planes (kube-apiserver + controller-manager + scheduler) as Deployments in the management cluster, backed by an external datastore (kine/MySQL/etcd). Per-tenant kubeconfig handed back to the tenant."
  primary_url: "https://kamaji.clastix.io/concepts/"
- name: Capsule (Clastix / Project Capsule)
  positioning: "Policy-driven namespace tenancy on a shared control plane — a `Tenant` CR groups namespaces under a tenant owner, automatically inheriting RBAC, quotas, network policy, and PSA across the group. No per-tenant API server. The 'we don't want virtual clusters' answer."
  primary_url: "https://projectcapsule.dev/docs/overview"
- name: Cluster API + per-tenant real cluster
  positioning: "Use Cluster API (Talos, CAPA, CAPZ, CAPV, etc.) to lifecycle a real Kubernetes cluster per tenant. Hard isolation by kernel and network; operational cost is one full cluster per tenant. Frank's answer for the public-edge workload — see Hop."
  primary_url: "https://cluster-api.sigs.k8s.io/"
- name: HyperShift (Red Hat OpenShift)
  positioning: "Hosted control planes on OpenShift — control planes run as pods in a management cluster, data plane nodes can be on any infrastructure. The enterprise reference architecture for the virtual-control-plane pattern."
  primary_url: "https://hypershift-docs.netlify.app/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "vCluster — How it works"
  type: vendor-docs
  url: "https://www.vcluster.com/docs/vcluster"
  quoted_passages:
    - "vCluster provisions isolated Kubernetes tenant clusters... Each tenant gets a full Kubernetes API experience while the virtualized control plane stays completely invisible to them."
  relevance: "Establishes the virtual-control-plane shape — a real kube-apiserver per tenant, hidden syncer translating tenant intent into host workloads. The architectural baseline for the Paper's §3 vCluster diagram."
- title: "Kamaji — Concepts"
  type: vendor-docs
  url: "https://kamaji.clastix.io/concepts/"
  quoted_passages:
    - "The central cluster where Kamaji is installed hosts the control planes for all Tenant Clusters as regular Kubernetes pods."
  relevance: "The alternative virtual-control-plane shape — control plane runs as Deployments instead of vCluster's per-tenant StatefulSet, with an external datastore. Lets the Paper contrast two answers to the same shape."
- title: "Project Capsule — Overview"
  type: vendor-docs
  url: "https://projectcapsule.dev/docs/overview"
  quoted_passages:
    - "Capsule introduces the Tenant: a lightweight, cluster-scoped resource that groups one or more Kubernetes namespaces under a shared set of boundaries."
  relevance: "The shared-control-plane shape with policy enforcement on top. Defines the namespace-tenancy strawman the Paper has to beat for vCluster to be the right call."
- title: "Kubernetes documentation — Multi-tenancy"
  type: vendor-docs
  url: "https://kubernetes.io/docs/concepts/security/multi-tenancy/"
  quoted_passages:
    - "In more extreme cases, it may be easier or necessary to forgo any cluster-level sharing at all and assign each tenant their dedicated cluster, possibly even running on dedicated hardware if VMs are not considered an adequate security boundary."
  relevance: "Upstream Kubernetes position on the tenancy spectrum — names the three shapes (namespace tenancy, virtual control plane, dedicated cluster) and concedes that hard isolation eventually requires its own cluster. Anchors §1 stack-position language."
- title: "Cluster API — Introduction"
  type: vendor-docs
  url: "https://cluster-api.sigs.k8s.io/"
  quoted_passages:
    - "Cluster API is a Kubernetes sub-project focused on providing declarative APIs and tooling to simplify provisioning, upgrading, and operating multiple Kubernetes clusters."
  relevance: "Reference for the real-cluster-per-tenant shape. Frank's Hop cluster is the live instantiation of this choice (Talos-on-Hetzner instead of CAPA/CAPZ, but the architectural shape is the same)."
- title: "kubernetes-sigs/multi-tenancy — Working Group repository"
  type: paper
  url: "https://github.com/kubernetes-sigs/multi-tenancy"
  quoted_passages:
    - "run multiple virtualized cluster on a single underlying cluster, allowing for hard(er) multitenancy."
  relevance: "SIG-multi-tenancy's position paper space — names the categorization that the Paper inherits (soft tenancy → hard tenancy spectrum). Type 'paper' because the WG produces published position documents rather than vendor marketing."
- title: "vcluster #3810 — PVC syncer unconditionally mangles volumeName and storageClassName"
  type: postmortem
  url: "https://github.com/loft-sh/vcluster/issues/3810"
  quoted_passages:
    - "the PVC syncer mangling the volumeName to vcluster--x--. The storageClassName is also mangled similarly. No PV or SC with the mangled names exist on the host, so the PVC stays Pending permanently."
  relevance: "Real-world failure mode of the syncer model — the abstraction leaks when host-side PVs already exist with the wrong-shaped names. The Paper uses this to ground the §3 architecture discussion: a virtual control plane is not free, the seam between tenant intent and host execution is where bugs live."
- title: "Frank vCluster design spec (2026-03-07)"
  type: vendor-docs
  url: "https://github.com/derio-net/frank/blob/main/docs/superpowers/specs/2026-03-07--tenant--vcluster-design.md"
  quoted_passages:
    - "vCluster OSS with embedded SQLite backing store; Longhorn-backed PV for control-plane state; ResourceQuota / LimitRange / NetworkPolicy enforced on every tenant by default."
  relevance: "Frank's authoritative in-repo design doc for the vCluster layer — the source of truth the template values.yaml descends from. Treat as a vendor-docs source because for this Paper, Frank IS one of the vendors being evaluated."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/vclusters/template/values.yaml"
  date: 2026-05-22
  demonstrates: "The OSS-edition design choices encoded in YAML: SQLite (embedded — etcd requires a Pro license), Longhorn-backed PV for control-plane state, k3s distro with bumped init-container memory, ResourceQuota / LimitRange / NetworkPolicy enforced on every tenant by default. This is what 'sensible defaults for a homelab sandbox' actually looks like in 83 lines."
- kind: yaml
  path_or_url: "apps/vclusters/experiments/values.yaml"
  date: 2026-05-22
  demonstrates: "The two-layer values pattern in action — a 20-line file that is almost entirely commented examples. The emptiness IS the point: the template carries the policy, the instance file only exists to give a new vCluster a home for the overrides it will eventually need."
- kind: yaml
  path_or_url: "apps/root/templates/vcluster-experiments.yaml"
  date: 2026-05-22
  demonstrates: "The integration cost of running vCluster under ArgoCD: a non-trivial ignoreDifferences block on the StatefulSet to keep ArgoCD from fighting the chart's vClusterConfigHash annotation and the K8s-defaulted StatefulSet fields (whenScaled, revisionHistoryLimit, updateStrategy). The fix is four jsonPointers, but it is the kind of seam you only find by running it under GitOps."
- kind: commit
  path_or_url: "docs/superpowers/plans/2026-03-20--repo--multi-cluster-restructure/"
  date: 2026-03-20
  demonstrates: "Structural evidence that Frank's answer to 'I need a second cluster for the public edge' was NOT another vCluster — it was a real Talos cluster on Hetzner (Hop). The plan to restructure the monorepo for multi-cluster is the architectural admission that vCluster is one rung on the tenancy ladder, not the whole ladder."
- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-05-22
  demonstrates: "Negative result — at time of dossier authoring, grep over agents/rules/frank-gotchas.md and docs/runbooks/frank-gotchas/*.md returns zero vCluster-specific entries. The absence is itself the finding: vCluster OSS + SQLite + Longhorn-PV has run on Frank without producing a single registry-worthy scar. That is the most surprising result of the Paper — at homelab scale, the category is calm."

## Diagrams planned
- landscape:
    x_axis: "Tenant isolation strength (soft ↔ hard)"
    y_axis: "Per-tenant runtime cost (low ↔ high)"
    vendors_plotted:
      - "Plain namespaces + RBAC"
      - "Capsule"
      - "vCluster (OSS)"
      - "Kamaji"
      - "HyperShift"
      - "Cluster API (real cluster)"
- architecture_comparison:
    vendors:
      - "Capsule (shared control plane)"
      - "vCluster (virtual control plane, StatefulSet)"
      - "Kamaji (virtual control plane, Deployments + external datastore)"
      - "Cluster API (real cluster per tenant)"
- decision_tree:
    leaves: 4

## Named gaps (≥1)
- "No public, apples-to-apples benchmark of per-vCluster steady-state RAM/CPU floor across realistic workload mixes at homelab scale (3–8 nodes, 1–10 tenants, mixed idle and active). Vendor docs publish best-case numbers (200–300 MiB for an idle SQLite-backed control plane) and the K8s SIG-Multitenancy working group has produced a categorization framework (soft vs. hard tenancy) but not a cross-vendor cost measurement. The gap matters because the decision between namespace tenancy and virtual-cluster tenancy is gated on this number — a 50-MiB RoleBinding per tenant vs. a 300-MiB StatefulSet per tenant is the math that flips the answer at 5+ tenants on a 64-GiB node. Nobody has published the curve."

## Counter-arguments considered (≥1)
- "For a 3-person team running 5 services, plain namespaces + RBAC + Cilium NetworkPolicies + a couple of ResourceQuotas is fine — why doesn't that win for Frank? Answer: it DOES win for that team. Plain namespaces are the right answer when the tenants are trusted, the CRD churn is low, and nobody needs to install a cluster-scoped resource. Frank's actual tenants are agents and experiments — secure-agent pods running arbitrary code, sandbox installs of unfamiliar Helm charts, kubeconfig handoffs to external users who should see zero of the host cluster. None of those use cases survive on namespace-only isolation. The counter-argument wins for the team whose tenants are well-behaved internal services; for Frank, whose tenants are deliberately ill-behaved, vCluster's API isolation is the point. The fuller honest answer adds: even Frank doesn't use vCluster for everything — the public-edge workload got its own real cluster (Hop), because the threat model (public internet, separate geography, separate kernel) categorically doesn't fit any shape of in-cluster tenancy."
