---
title: "Why Build a Kubernetes Homelab?"
series: ["building"]
layer: repo
date: 2026-03-06
draft: false
tags: ["introduction", "architecture"]
summary: "The motivation behind Frank, the Talos Cluster — learning enterprise infrastructure and building interesting projects on your own hardware."
weight: 2
reader_goal: "Decide whether this cluster architecture suits your own homelab goals and map its two-layer management model"
diataxis: explanation
last_updated: 2026-07-15
---

I knew Kubernetes from the cloud. {{< abbr "EKS" >}}, {{< abbr "GKE" >}} — they hand you a cluster with networking, storage, and GPU scheduling already wired. You push a manifest, it works, and you have no idea how. The abstraction is the point if your job is shipping features. But if your job is understanding infrastructure, the abstraction is the obstacle.

I wanted to know what happens between `kubectl apply` and a running pod. How does the {{< abbr "CNI" >}} assign an IP? How does Longhorn replicate data without a SAN? How does an immutable OS manage disk mounts when there is no SSH and no shell? You can read about eBPF kube-proxy replacement or {{< abbr "DRA" >}}-based GPU sharing all day. But you can also break it, fix it, and actually learn it.

The hardware was already sitting around. An i9 desktop retired from daily use. A stack of Intel {{< abbr "NUC" "NUCs" >}}. Two Raspberry Pi 4s gathering dust. The cluster turns idle machines into a platform. The goal was never "run a production cluster at home." It was to build one that *could* be production, so the skills transfer directly.

## The Shape That Emerged

What started as "throw Kubernetes on some boxes" became a four-zone design, driven less by planning and more by what each machine forced us to confront.

```mermaid
flowchart LR
  subgraph M[Zone A — Management]
    omni[raspi-omni<br/>Omni + Authentik + Traefik]
  end
  subgraph C[Zone B — Core HA]
    n1[mini-1<br/>CP + Worker]
    n2[mini-2<br/>CP + Worker]
    n3[mini-3<br/>CP + Worker]
  end
  subgraph G[Zone C — AI Compute]
    gpu[gpu-1<br/>RTX 5070, 128GB, 8TB SSD]
  end
  subgraph E[Zone D — Edge]
    pc[pc-1<br/>Legacy desktop]
    r1[raspi-1<br/>Pi 4]
    r2[raspi-2<br/>Pi 4]
  end

  omni -->|machine config| n1
  omni -->|machine config| n2
  omni -->|machine config| n3
  omni -->|machine config| gpu
  omni -->|machine config| pc
```

**Zone A** is a single Raspberry Pi 5 that lives outside the cluster. It runs Sidero Omni (machine lifecycle), Authentik ({{< abbr "SSO" >}}), and Traefik (ingress). Putting management outside the cluster was a lesson learned the hard way — more on that in Missteps.

**Zone B** is three identical Intel NUCs (Ultra 5, 64GB, 1TB NVMe). They form the {{< abbr "HA" >}} control plane. Because Talos lets control planes run workloads, these also host Longhorn storage and most cluster services. Identical hardware means predictable capacity. No surprises.

**Zone C** is one machine: a custom desktop with an i9, 128GB RAM, an RTX 5070, and two 4TB SATA SSDs. It is the single node that makes the cluster interesting — local {{< abbr "LLM" >}} inference, diffusion models, agentic workloads. Everything GPU-related lands here.

**Zone D** is the rag-tag edge: a legacy desktop (pc-1) and two Raspberry Pi 4s. They run CI/CD pipelines, monitoring scrapers, DNS caches — workloads that need to be always-on but do not need a GPU or fast storage.

{{< screenshot src="homelab.png" alt="The Frank cluster in its natural habitat. The minis are hidden behind a patch panel. The GPU desktop stands to the left. The Raspberry Pis are in a horizontal rack kit alongside other network gear. The GPU did not fit in a rack-mountable case so it lives in a gaming case with LEDs that never turn off." caption="The Frank cluster in its natural habitat. The minis are hidden behind a patch panel. The GPU desktop stands to the left. The Raspberry Pis are in a horizontal rack kit alongside other network gear. The GPU did not fit in a rack-mountable case so it lives in a gaming case with LEDs that never turn off." >}}

## The Two-Layer Model That Makes It Work

The single most important design decision was separating machine config from workload config. It was not obvious at first. Early on, Omni and ArgoCD overlapped in confusing ways — Omni would install an OS extension, ArgoCD would try to manage the same resource, and neither knew about the other.

The fix was a clean boundary:

- **Layer 1 (Machine Config):** Sidero Omni manages Talos Linux machine configurations — OS extensions, kernel modules, disk mounts, network settings. Applied via `omnictl` config patches. Version-controlled in `clusters/frank/`.
- **Layer 2 (Workloads):** ArgoCD manages everything running *on* Kubernetes — CNI, storage, GPU drivers, applications. GitOps via `apps/` in the same repo.

Omni never touches workloads. ArgoCD never touches machine config. When a problem surfaces, you know which layer to debug.

![Omni cluster dashboard showing all seven nodes, their roles, and resource usage](omni-cluster.png)

## Verify the boundary on your own cluster

A boundary is easy to describe and easy to violate, so check it rather than believe it. The zone labels are the cheapest probe: they are declared in machine config, which means Layer 1 put them there and Kubernetes is only reporting them back.

```console
$ kubectl get nodes -L zone,tier,accelerator
NAME      STATUS   ROLES           AGE    VERSION   ZONE         TIER        ACCELERATOR
gpu-1     Ready    <none>          148d   v1.35.3   ai-compute   standard    nvidia
mini-1    Ready    control-plane   148d   v1.35.3   core         standard    intel-igpu
mini-2    Ready    control-plane   148d   v1.35.3   core         standard    intel-igpu
mini-3    Ready    control-plane   148d   v1.35.3   core         standard    intel-igpu
pc-1      Ready    <none>          148d   v1.35.3   edge         standard
raspi-1   Ready    <none>          148d   v1.35.3   edge         low-power
raspi-2   Ready    <none>          148d   v1.35.3   edge         low-power
```

Seven nodes, three zones. Zone A is not in that list, and its absence is the whole point: management lives outside the cluster it manages, so it has no node to appear as. The day Zone A shows up in `kubectl get nodes` is the day the separation quietly collapsed.

Run that against a fresh cluster of your own and the last three columns come back empty, which is the useful part. Empty means nothing has claimed those machines yet. Filling the columns by hand with `kubectl label node` also works, and it is the wrong answer: the label then lives only in etcd, so it survives exactly until the node is reimaged.

Now trace one of those labels back to the file that declares it:

```console
$ grep -rn 'zone: ai-compute' patches/ apps/
patches/phase01-node-config/03-labels-gpu-1.yaml:13:                zone: ai-compute
```

One hit, and it is under `patches/`. Nothing under `apps/`. That is the two-layer model reduced to a grep: machine facts are declared where Omni can see them, and workloads are declared where ArgoCD can see them. Neither directory carries the other's business.

Run the same grep against your own repo. If a node label turns up inside a Helm chart, the layers have started to leak, and the first question of every future debugging session ("which layer owns this?") no longer has an answer.

## What the Series Covers

Each post in this series builds one layer on top of the last. The roadmap below shows the full sequence — the post you are reading sits at Layer 0, the motivation.

{{< roadmap >}}

## What You Need to Follow This

- Familiarity with `kubectl` and basic Kubernetes concepts (Pod, Service, Deployment)
- A Talos-compatible machine (x86 or ARM64) to experiment on — even a single node is enough for most layers
- About 30 minutes per layer post

The series assumes you are building alongside. Each post ends with a running cluster state you can verify.

## What Transfers

None of this is specific to my hardware. Three things are worth carrying to whatever you build next:

- **Give every fact one owner, and make ownership greppable.** The value of the two-layer split is not tidiness. It is that "which layer owns this?" is answerable with `grep` at 2am instead of being a matter of opinion.
- **Put management outside the thing it manages.** Anything you need in order to fix the cluster should not require the cluster to be working. That rule cost me a rebuild to learn, and it applies equally to a CI runner, a backup target, or a secrets store.
- **Mismatched hardware is a feature while you are learning.** Identical nodes teach you the happy path. A Raspberry Pi and an RTX 5070 in the same scheduler teach you what a node selector is actually for, and they do it on the first day rather than the first outage.

## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---------------|-----------------|-----------------|--------|
| **Management ran on mini-1** — Omni and Authentik shared the first control-plane node at boot | A control-plane reboot would take down management (Omni) and auth (Authentik) simultaneously, creating a circular dependency where nothing could restart without the other | Moved Omni and Authentik to a dedicated Raspberry Pi 5 outside the cluster | `frank-infrastructure.md` |
| **Zone D was originally just pc-1** — the Raspberry Pis were added months later as an afterthought | The cluster needed low-power edge nodes for always-on workloads (DNS caches, monitoring scrapers) without burning 65W x86 idle power | Added raspi-1 and raspi-2 as `tier: low-power` edge workers | `ce2fcd9e` |
| **No hardware photo for the first three months** — readers had diagrams of logical topology but no sense of the physical rack layout | The abstract diagrams made the cluster feel theoretical; the photo made it real | Added `homelab.png` showing the rack, minis, and gpu-1 workstation | `46673fde` |
| **Early drafts documented a manual kubeadm install on Ubuntu** — the entire bootstrap section described a flow that Omni later replaced | Omni support was added mid-series, making the documented approach obsolete and requiring a full revision of the foundation post | Rewrote to describe Omni-based bootstrap as the primary path | `ce2fcd9e` |

## References

- [Talos Linux](https://www.talos.dev/) — Immutable, secure, minimal Kubernetes OS
- [Sidero Omni](https://www.siderolabs.com/omni/) — SaaS-simple Kubernetes cluster management for Talos Linux
- [ArgoCD](https://argo-cd.readthedocs.io/en/stable/) — Declarative GitOps continuous delivery for Kubernetes
- [Cilium](https://docs.cilium.io/en/stable/) — eBPF-based networking, observability, and security
- [Longhorn](https://longhorn.io/) — Cloud-native distributed block storage for Kubernetes
- [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/) — GPU management in Kubernetes
