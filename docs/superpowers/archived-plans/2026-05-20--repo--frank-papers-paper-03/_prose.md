# The Frank Papers — Paper 03: eBPF Networking Without a Service Mesh

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Complete (2026-05-20) — Paper 03 draft published on branch `paper-03`; PR open for human review.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 02, 04,
06, 07, 10, 11, 14 published.

Paper 03 is the networking capability Paper: 2400–4200 words, the standard
skeleton (§1 capability → §2 landscape → §3 architecture per vendor → §4
scale → §5 Frank's choice → §6 generalization → §7 roadmap), and the
Paper that confronts the *eBPF vs service-mesh vs kube-proxy* question
head-on. The capability under examination is *pod-to-pod and
external-to-pod network reachability on Kubernetes* — who carries the
packet, who enforces the policy, who tells you what just happened, and
what tax do they charge for any of it?

The vendor space splits on two axes: data-plane technology (iptables
vs eBPF vs userspace sidecar proxies) and observability surface
(reactive `kubectl describe` only vs structured flow logs vs full L7
mTLS inspection). Six candidates make the landscape, with **Cilium**
as Frank's case study — eBPF-native data plane, L2 LBIPAM for bare-metal
LoadBalancer Services, Hubble for flow observability, all in one Helm
chart with `kubeProxyReplacement: true`. The other vendors exist in the
dossier so §3 can compare architectures and §6 can branch the decision
tree without strawmanning the alternatives.

The scars are the point. The FQDN `CiliumNetworkPolicy` whose stale BPF
rules persisted in the data path after we deleted the policy — for hours,
until we restarted the agent on each node. The `lbipam.cilium.io/ips`
annotation alone leaving a Service `<pending>` for 41 days because we
hadn't added the matching `sharing-key`. The half-hour we spent reading
old GitHub issues looking for a `MixedProtocolLBService` feature gate
that Cilium 1.17 + K8s 1.35 had already shipped on. These aren't
decorations on the §5 narrative — they're why the §6 decision tree
has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on the absence of an apples-to-apples
"CNI total operational tax" benchmark (data-plane CPU, policy enforcement
overhead, observability stack overhead, ops time per incident, all
bundled), and the counter-argument that for an AWS-native cluster the
VPC CNI is the rational default and replacing it with Cilium is overkill.
Parallel subagents per vendor are appropriate — one each for Cilium,
Calico, kube-proxy+iptables, Istio, Linkerd2, and cloud-managed CNIs —
with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"for an AWS-native cluster
with mostly stateful workloads and no policy needs, the VPC CNI is the
rational default — why doesn't that win for Frank?"* Same shape as
Paper 04's framing applied to the networking capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (mesh-sidecar P99, eBPF map sizing at N endpoints, conntrack table growth)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (FQDN-stale-BPF, LBIPAM sharing-key, MixedProtocolLBService gate-free)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a glowing network packet traced through
a row of eBPF hooks (no service mesh sidecars), thin black tie, round
reading glasses. The visual metaphor is *the packet's path through the
kernel*. Mermaid diagrams: §1 stack position, §2 landscape (quadrantChart)
+ capability matrix, §3 four-to-six architecture flowcharts, §6 decision
tree. At least one Hubble UI screenshot captured live from the cluster
(192.168.55.202). Cluster-side captures may be deferred with `-TODO.png`
placeholders if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: verify the auto-rendered
cross-link chips appear on Building 02-foundation and Operating
01-cluster-nodes, append Paper 03 to the Papers `_index.md` list,
update README if relevant, set plan status to Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
