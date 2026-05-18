---
paper: 04-distributed-storage
status: draft
---

## Vendors in scope (≥3, typically 4–6)
- name: Longhorn
  positioning: "Rancher/SUSE — distributed block storage for Kubernetes with snapshots, backups, and a friendly UI."
  primary_url: "https://longhorn.io"
- name: Rook-Ceph
  positioning: "Operator-driven Ceph on Kubernetes — the 'real' distributed storage, unified block/file/object."
  primary_url: "https://rook.io"
- name: OpenEBS Mayastor
  positioning: "NVMe-over-Fabrics replicated block storage — performance-first, MayaData-led."
  primary_url: "https://openebs.io/"
- name: Piraeus / LINSTOR
  positioning: "LINBIT's K8s offering — DRBD-based block replication with kernel-level guarantees."
  primary_url: "https://piraeus.io"
- name: Portworx
  positioning: "Commercial, enterprise SLA, PX-Backup — paid distributed storage for production Kubernetes."
  primary_url: "https://portworx.com"
- name: local-path-provisioner
  positioning: "Rancher's trivial single-node baseline — hostPath PVCs, no replication, useful as the 'null hypothesis'."
  primary_url: "https://github.com/rancher/local-path-provisioner"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Longhorn — Architecture and Concepts"
  type: vendor-docs
  url: "https://longhorn.io/docs/"
  quoted_passages:
    - "Longhorn creates a dedicated storage controller for each volume and synchronously replicates the volume across multiple replicas stored on multiple nodes."
    - "The default replica count is 3. Each replica is placed on a different node based on the configured replica scheduling policy."
  relevance: "Vendor's own articulation of Longhorn's per-volume-engine architecture. Defines the model Frank actually runs (engine pod + N replica pods per volume) and grounds the §3 architecture comparison in Longhorn's authoritative description."

- title: "Rook — Architecture overview"
  type: vendor-docs
  url: "https://rook.io/docs/rook/latest-release/Getting-Started/intro/"
  quoted_passages:
    - "Rook is an open source cloud-native storage orchestrator, providing the platform, framework, and support for Ceph storage to natively integrate with cloud-native environments."
    - "Rook automates deployment, bootstrapping, configuration, provisioning, scaling, upgrading, migration, disaster recovery, monitoring, and resource management."
  relevance: "Definitive description of the operator-driven Ceph deployment model. Anchors the §3 architecture diagram for Rook-Ceph and the §4 'CRUSH wants ≥5 OSD hosts' rule."

- title: "Ceph: A Scalable, High-Performance Distributed File System (Weil et al., OSDI '06)"
  type: paper
  url: "https://www.ssrc.ucsc.edu/Papers/weil-osdi06.pdf"
  quoted_passages:
    - "We have designed and implemented Ceph, a distributed file system that provides excellent performance, reliability, and scalability."
    - "Ceph maximizes the separation between data and metadata management by replacing allocation tables with a pseudo-random data distribution function (CRUSH) designed for heterogeneous and dynamic clusters of unreliable object storage devices (OSDs)."
  relevance: "Foundational academic paper that introduces the CRUSH placement algorithm, the same machinery Rook still deploys twenty years later. Used in §2 and §3 to anchor the centralized-storage definition and explain why Ceph's minimum-host count is what it is."

- title: "Longhorn vs Ceph (Rook) — Reddit r/kubernetes practitioner thread"
  type: benchmark
  url: "https://www.reddit.com/r/kubernetes/comments/15h0sw5/longhorn_vs_ceph/"
  quoted_passages:
    - "Longhorn is much simpler to set up and operate. Ceph is more powerful but requires more nodes and more tuning to perform well."
    - "I run Longhorn on a 3-node cluster with NVMe drives and it just works."
  relevance: "Practitioner-level head-to-head with reproducible setup notes — explicitly names the 'Ceph needs more nodes to perform' rule of thumb cited in §4. Not a controlled benchmark, but the closest thing the community has to one at homelab scale, and representative of the consensus."

- title: "Frank — Storage / Secrets / SSA gotchas (RWO PVC + RollingUpdate deadlock, ESO empty-data rejection)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "RWO PVC + RollingUpdate deadlocks; use strategy: Recreate. Switching strategy via Helm needs a one-time kubectl patch to clear the orphan rollingUpdate: block."
    - "ESO: empty data: [] is rejected; delete the ExternalSecret if all keys are removed."
    - "SOPS-encrypted secrets must NOT be ArgoCD-managed; apply out-of-band from secrets/."
  relevance: "Frank's own running postmortem registry — concrete operational scars accumulated while running Longhorn in production for this learning platform. Provides the source-of-truth dates and recovery commands for §5 scar callouts and underwrites the §6 decision-tree branches."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/longhorn/values.yaml"
  date: 2026-02-15
  demonstrates: "Frank's Longhorn replica count is bound to the control-plane count by construction — `defaultReplicaCount: 3` matches the three control-plane nodes (mini-1 / mini-2 / mini-3). Not chosen for durability math; chosen because that's the node fleet."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-05-03
  demonstrates: "The RWO PVC + RollingUpdate deadlock: a chart with strategy RollingUpdate plus a ReadWriteOnce PVC cannot replace its pod, because the new pod can never attach the volume while the old one still holds it. Forced Frank to standardize on strategy Recreate for every stateful chart in apps/ — a discovery that ripples into every Helm values file with a persistent volume."

- kind: commit
  path_or_url: "https://github.com/derio-net/frank/commit/e40c952"
  date: 2026-05-03
  demonstrates: "The one-time kubectl patch that cleared the orphan rollingUpdate block when switching strategy via Helm. Helm's chart rendering cannot delete keys from a live resource — strategy switches require manual surgery. An immutability boundary inside an otherwise declarative stack."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/storage-secrets-ssa.md"
  date: 2026-04-20
  demonstrates: "The ESO empty data:[] admission rejection: when all keys are removed from an ExternalSecret, the resulting empty data shape is rejected by the admission webhook. The ExternalSecret itself must be deleted, not zeroed. Declarative tooling does not infer 'empty' from 'missing'."

- kind: grafana-screenshot
  path_or_url: "blog/content/docs/papers/04-distributed-storage/longhorn-3-replica-healthy-TODO.png"
  date: 2026-05-19
  demonstrates: "Longhorn UI snapshot showing healthy volumes with 3 replicas each, distributed across mini-1 / mini-2 / mini-3. The visible evidence that the replica_count = control_plane_count shape is what's actually running, and that a Healthy state is what default settings produce."

## Diagrams planned
- landscape:
    x_axis: "OSS ↔ Commercial"
    y_axis: "Centralized ↔ Replicated-per-volume"
    vendors_plotted: ["Longhorn", "Rook-Ceph", "OpenEBS Mayastor", "Piraeus / LINSTOR", "Portworx", "local-path-provisioner"]
- architecture_comparison:
    vendors: ["Longhorn", "Rook-Ceph", "OpenEBS Mayastor", "Piraeus / LINSTOR", "Portworx"]
- decision_tree:
    leaves: 4
    description: "Question: who keeps your bytes alive on bare metal? Branches on node count and RWX-need, terminating in: local-path, Longhorn, Rook-Ceph (forced), Rook-Ceph (sweet spot). A fifth-leaf 'production SLA → Portworx or managed cloud' override is dashed-subordinate."

## Named gaps (≥1)
- "No published TCO comparison of Longhorn vs Rook-Ceph at ≤10-node scale that accounts for operational burden — only $/GB. Every available comparison either (a) benchmarks performance without cost, or (b) compares cloud storage pricing without measuring the ops tax on the bare-metal side. The single most useful number for a decision-maker — 'how many hours per month does each option cost you?' — does not exist as published work."

## Counter-arguments considered (≥1)
- "Managed cloud storage (EBS, Persistent Disk, Azure Managed Disks) at small scale is cheaper per-GB than amortized homelab hardware AND erases the operational tax — why doesn't that win for Frank? Answer: same as Paper 00. Frank is a learning platform. The reason to run Longhorn is to encounter the RWO-RollingUpdate deadlock, the SSA discipline, the empty-ExternalSecret admission rejection — first-hand. Managed cloud storage hides exactly the failure modes the cluster exists to teach. For a production team, the counter-argument wins; for Frank, that is the point."
