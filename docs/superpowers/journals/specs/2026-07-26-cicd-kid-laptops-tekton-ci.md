# Journal: 2026-07-26-cicd-kid-laptops-tekton-ci

<!-- fr:journal kind=decision scope=spec id=d1-kubevirt-spec-only created=2026-07-26T17:05:14 -->
### d1-kubevirt-spec-only · decision · KubeVirt: spec-only this run; deploy in a follow-up

Operator, batched Q&A. This run rewrites the parked VMs design spec (research-backed) and ships only CI that needs no hypervisor. The KubeVirt install becomes its own plan off the new spec. Rationale: 'we only implement what we can support today'.

<!-- fr:journal kind=decision scope=spec id=d2-kubevirt-full-shape created=2026-07-26T17:05:16 -->
### d2-kubevirt-full-shape · decision · When KubeVirt lands: operator + CDI + kubevirt-manager UI

Operator, batched Q&A. Revive the parked design in full. Driven by the second use case (persistent Windows VM): Win11 hard-requires vTPM + UEFI SecureBoot (features.smm) and a real console, so CDI v1.65.0 DataVolumes on Longhorn and kubevirt-manager (chart 0.6.0) on 192.168.55.205 behind authentik-forwardauth + homepage tile are load-bearing, not decoration.

<!-- fr:journal kind=decision scope=spec id=d3-virt-layer-21 created=2026-07-26T17:05:17 -->
### d3-virt-layer-21 · decision · New layer code: virt = Layer 21 (Virtualization)

Operator, batched Q&A. The parked spec was filed under 'hw'; VMs are their own capability domain. blog/data/roadmap.yaml already reserves a 'Virtual Machines — upcoming' entry listing KubeVirt/CDI/Manager/DataVolumes.

<!-- fr:journal kind=decision scope=spec id=d4-gitea-mirror-public created=2026-07-26T17:05:19 -->
### d4-gitea-mirror-public · decision · Gitea mirror repo is public inside the in-cluster Gitea

Operator, batched Q&A. Tekton's git resolver in URL mode cannot pass credentials, and the kid-laptops contract pins that mode. Gitea is LAN-only (192.168.55.209, no ingress, no public DNS); precedent is the public tekton-bot/frank mirror. Keeps the documented PipelineRun contract byte-for-byte. Trade-off accepted: LAN readers can read a repo that is private on GitHub.

<!-- fr:journal kind=decision scope=spec id=d5-kid-laptops-companion-pr created=2026-07-26T17:05:20 -->
### d5-kid-laptops-companion-pr · decision · This run also opens a companion PR on derio-homelab/kid-laptops

Operator, batched Q&A. Overrides their offer to make the change themselves. Scope: real Zot coordinates in the three places that must agree, and — the larger part — making the molecule tasks conditional so a Python-only run is a legitimate green.

<!-- fr:journal kind=decision scope=spec id=d6-python-only-pipeline created=2026-07-26T17:05:22 -->
### d6-python-only-pipeline · decision · Pipeline scope today: Python/Ansible checks only; molecule deferred

Operator, batched Q&A. lint + syntax + unit-tests run now. molecule-base/molecule-teardown stay unrun until KubeVirt is live; the containerDisk gets built on the laptop (Intel i9, HVF-accelerated qemu already installed) and pushed to Zot at that point — not built in-pipeline.

<!-- fr:journal kind=decision scope=spec id=d7-reply-to-issue created=2026-07-26T17:05:23 -->
### d7-reply-to-issue · decision · Report back on kid-laptops#43 rather than flipping acceptance rows

Operator, batched Q&A, and kid-laptops' own request. The report must correct their premise: the workstation HAS qemu/packer/docker; Frank (Talos) has none of them and no shell.

<!-- fr:journal kind=review scope=spec id=r1-spec-review created=2026-07-26T17:10:55 -->
### r1-spec-review · review · Spec review against Q&A answers and live cluster

Verified rather than assumed: VMX/amd64 on all five x86 nodes (raspi-1 arm64, no VMX) — spec's hardware table now measured; longhorn-cicd is numberOfReplicas=1 dataLocality=best-effort, NOT node-pinned, so it is safe for the CI workspace; enable-git-resolver=true confirmed in the tekton-pipelines-RESOLVERS namespace. One finding fixed: run-id was specified as bare $(uid), but Tekton documents $(uid) only as 'a random value, like the generateName postfix' — random is not unique, and the request calls a run-id collision catastrophic (two runs destroy each other's VM). Changed to <short-sha>-$(uid).

<!-- fr:journal kind=finding scope=spec id=f1-generic-trigger-catches-kid-laptops created=2026-07-26T17:10:57 state=fixed -->
### f1-generic-trigger-catches-kid-laptops · finding [fixed] · Generic gitea-push trigger would fire a second, failing pipeline

apps/tekton/triggers/eventlistener.yaml filters on !full_name.startsWith('agentic-stoa/'), so any derio-homelab/kid-laptops push ALSO matches the generic gitea-ci trigger — every push would create two PipelineRuns, one of them failing. Found by reading the live EventListener rather than the request. Fix: extend the exclusion to derio-homelab/ plus a tripwire test; test plan step 4 asserts exactly one PipelineRun.
