---
paper: 02-immutable-os
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Talos Linux
  positioning: "Sidero — API-driven immutable Linux for Kubernetes; no SSH, no shell, machine config as YAML."
  primary_url: "https://www.talos.dev"
- name: Fedora CoreOS
  positioning: "Red Hat — Ignition-bootstrapped immutable Linux with transactional rpm-ostree updates."
  primary_url: "https://docs.fedoraproject.org/en-US/fedora-coreos/"
- name: Flatcar Container Linux
  positioning: "Microsoft (ex-Kinvolk) — CoreOS-lineage continuation; dual-partition A/B updates, Ignition-based."
  primary_url: "https://www.flatcar.org/"
- name: Bottlerocket
  positioning: "AWS — purpose-built container host, API-driven config, transactional updates, ECR/EKS aligned."
  primary_url: "https://aws.amazon.com/bottlerocket/"
- name: Ubuntu Core
  positioning: "Canonical — fully snap-based immutable Ubuntu for appliances and edge; the IoT/embedded angle."
  primary_url: "https://ubuntu.com/core"
- name: Ubuntu Server + Ansible (mutable baseline)
  positioning: "The status-quo default — general-purpose distro plus a config-management overlay. The anti-immutable reference point."
  primary_url: "https://ubuntu.com/server"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Talos Linux — Concepts"
  type: vendor-docs
  url: "https://www.talos.dev/v1.11/learn-more/concepts/"
  quoted_passages:
    - "Talos is a modern OS designed to be secure, immutable, and minimal."
    - "Talos is configured exclusively through an API; there is no SSH access or interactive shell."
    - "Machine configuration is the source of truth: applying a new config replaces the existing one."
  relevance: "Vendor's canonical articulation of Talos's API-only management model and the 'no SSH, no shell' posture. Defines the model Frank actually runs on all seven nodes and grounds the architecture diagram in the vendor's own authoritative description."

- title: "Fedora CoreOS — Documentation"
  type: vendor-docs
  url: "https://docs.fedoraproject.org/en-US/fedora-coreos/"
  quoted_passages:
    - "Fedora CoreOS is an automatically-updating, minimal operating system for running containerized workloads securely and at scale."
    - "It is the successor to CoreOS Container Linux and Atomic Host, combining the provisioning tools, automatic update model, and philosophy of CoreOS Container Linux with the packaging technology, OCI support, and SELinux security of Atomic Host."
    - "Provisioning is performed by Ignition, which runs only on the first boot."
  relevance: "Vendor's own description of the Fedora CoreOS model — first-boot Ignition + rpm-ostree A/B updates. Anchors the Fedora CoreOS architecture diagram and supports the quadrant placement (immutable + Ignition-bootstrapped, not API-driven the way Talos and Bottlerocket are)."

- title: "Ignition (CoreOS) — Specification"
  type: vendor-docs
  url: "https://coreos.github.io/ignition/"
  quoted_passages:
    - "Ignition is a provisioning utility designed specifically for CoreOS-like OSes that reads its configuration from the system's firmware and applies it during the initramfs."
    - "Ignition runs only once on the first boot."
  relevance: "The Ignition spec underpins both Fedora CoreOS and Flatcar. Used to explain the shared 'image-based, Ignition-bootstrapped' family of immutable OSes that sits between Talos and the mutable baseline."

- title: "Bottlerocket: A special-purpose container operating system (AWS blog)"
  type: paper
  url: "https://aws.amazon.com/blogs/containers/bottlerocket-a-special-purpose-container-operating-system/"
  quoted_passages:
    - "Bottlerocket is a Linux-based open-source operating system that we built from the ground up to run containers."
    - "We've removed everything that's not needed to run containers, which reduces the attack surface area and the resources used."
    - "All software changes are applied via image-based updates, which enable faster, more reliable updates that can be quickly rolled back if necessary."
  relevance: "AWS's own design rationale for Bottlerocket — purpose-built, image-based updates, minimal surface area. The canonical AWS articulation referenced by every Bottlerocket-vs-X comparison. Used in landscape positioning, architecture diagram, and the ASG-coordinated update story."

- title: "ImmutableServer (Martin Fowler / ThoughtWorks)"
  type: paper
  url: "https://martinfowler.com/bliki/ImmutableServer.html"
  quoted_passages:
    - "An ImmutableServer is one that, once instantiated, is never modified. Updates and fixes occur not by changing the existing server, but by creating a new one."
    - "Phoenix servers go further: they are also re-created from scratch regularly, regardless of need."
  relevance: "The canonical framing essay that names the immutable-server pattern and contrasts it with traditional mutable infrastructure. Used to anchor the capability question and to draw the philosophical line between Frank's choice (immutable) and the mutable baseline."

- title: "Frank — OS / Talos / Hop gotchas (postmortem registry)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/hop-gotchas.md"
  quoted_passages:
    - "talosctl apply-config --config-patch patches the base file, not the running config — all patches must be combined in one invocation."
    - "Talos control-plane taint must be removed for single-node cluster (allowSchedulingOnControlPlanes: true in Talos config)."
    - "PodSecurity namespaces must be labeled pod-security.kubernetes.io/enforce: privileged for hostPort/privileged pods."
  relevance: "Frank's own running postmortem registry — concrete operational scars accumulated across two clusters (Frank, Hop) while running Talos in production for this learning platform. Provides the source-of-truth dates and recovery commands for the scar callouts and underwrites the decision-tree branches."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "patches/phase01-node-config/"
  date: 2026-02-01
  demonstrates: "Frank's full declarative machine-config story for all seven nodes rendered as Talos ConfigPatches under Omni. Node labels, zone topology, control-plane scheduling — all flow through Git -> Omni -> Talos, not kubectl label or interactive ssh. The first-class declarative entry point for the whole cluster."

- kind: yaml
  path_or_url: "patches/phase04-gpu/"
  date: 2026-03-10
  demonstrates: "The GPU layer extends the base machine config with NVIDIA system extensions and udev rules through the same declarative pipeline. Even a kernel-module-level concern goes through the same Git -> Omni -> Talos render path as a node label — there is no second 'kernel modules are special' rule."

- kind: incident
  path_or_url: "agents/rules/hop-gotchas.md"
  date: 2026-04-22
  demonstrates: "The talosctl apply-config --config-patch surprise: patches the base file, not the running config — all patches must be combined in one invocation. Talos's immutability isn't a UX nicety; it forces machine config to be treated as a single source-of-truth render, not a series of incremental edits the way kubectl conditioned us to expect."

- kind: incident
  path_or_url: "agents/rules/hop-gotchas.md"
  date: 2026-04-22
  demonstrates: "The Hop single-node cluster's allowSchedulingOnControlPlanes: true requirement. By default Talos refuses to schedule workloads on a control-plane node. On a single-node cluster this manifests as 'no pod ever enters Running' with no obvious signal — an evening spent assuming the CNI was broken before the actual taint was the culprit."

- kind: incident
  path_or_url: "docs/superpowers/specs/2026-03-10--gpu--operator-talos-fix-design.md"
  date: 2026-03-10
  demonstrates: "The GPU Operator Talos validation fix: NVIDIA's off-the-shelf operator's init containers wait forever for /run/nvidia/validations/toolkit-ready, a file the toolkit DaemonSet would normally create — except Talos disables that DaemonSet because the driver and toolkit come from system extensions. Required its own entire plan. The immutable-OS guarantee includes 'no — you can't do that the old way'."

- kind: grafana-screenshot
  path_or_url: "blog/content/docs/papers/02-immutable-os/omni-machines-TODO.png"
  date: 2026-05-19
  demonstrates: "Omni UI snapshot showing all 7 machines in the frank cluster (mini-1/2/3, gpu-1, raspi-1/2, pc-1) running the same Talos version. The visible evidence that one machine-config render pipeline absorbs x86/ARM/iGPU/dGPU heterogeneity without a per-host playbook."

## Diagrams planned
- landscape:
    x_axis: "Mutable <-> Immutable"
    y_axis: "Config-mgmt overlay <-> API-driven"
    vendors_plotted: ["Talos Linux", "Bottlerocket", "Fedora CoreOS", "Flatcar", "Ubuntu Core", "Ubuntu + Ansible"]
- architecture_comparison:
    vendors: ["Talos Linux", "Bottlerocket", "Fedora CoreOS", "Flatcar", "Ubuntu Core"]
- decision_tree:
    leaves: 4
    description: "Question: what OS should run on your cluster nodes? Branches on workload context (laptop / dev, bare-metal homelab, AWS shop, edge/IoT) and terminates in: Ubuntu Server (general-purpose), Talos Linux (Frank's pick), Bottlerocket (AWS alignment), Ubuntu Core or Flatcar (appliance/edge)."

## Named gaps (≥1)
- "No published TCO comparison of immutable-OS vs mutable-distro-plus-Ansible at homelab and small-team scale that accounts for both blast-radius cost (mutable: a single bad apt-get blows up a node) AND learning-curve cost (immutable: an entirely new mental model for day-2 ops). Vendor whitepapers benchmark update speed and security posture; community writeups focus on the 'cool factor' of API-driven OS. The single most useful number — 'hours per month spent on OS-level firefighting on each side, at N=5 nodes' — does not exist as published work."

## Counter-arguments considered (≥1)
- "Mutable distros (Ubuntu Server, Debian, RHEL) plus a competent Ansible/Puppet setup is the path 90 percent of teams should take. Familiar tooling, broad community, no retraining, no special-case kernel-module dance. Why doesn't that win for Frank? Answer: same shape as Paper 00. Frank is a learning platform. The reason to run Talos is to encounter the --config-patch rebuild semantics, the single-node control-plane taint, the GPU validation surprise — first-hand. Mutable-plus-Ansible hides exactly the failure modes the cluster exists to teach. For a production team running familiar workloads on well-known hardware, the counter-argument wins; for Frank, that is the point."
