<!-- fr:journal-schema=3 -->
# Journal: 2026-11-08--agents--retire-vk

<!-- fr:journal kind=discovery scope=spec id=operator-brief created=2026-11-08T19:31:46+00:00 input=true -->
### operator-brief · discovery · Operator brief (verbatim)

I decided to retire VK completely, in two phases. First remove all dependencies, alarms, images. Second: take the secure-agent-pod down if it's not otherwise used (it is not but it's temporary), mark the blog post(s) superceded and clean up

<!-- fr:journal kind=decision scope=spec id=d-pod-end-state created=2026-11-08T21:39:16+00:00 decided_by=operator -->
### d-pod-end-state · decision · Archive then delete the pod

The operator's interactive triage run is the only temporary use. Archive the files worth keeping, then delete the Application, namespace, PVC, LoadBalancers and cluster-admin binding.

<!-- fr:journal kind=decision scope=spec id=d-chorebot created=2026-11-08T21:39:16+00:00 decided_by=operator -->
### d-chorebot · decision · Let chorebot stop

No migration. Its data in Notion and code in willikins allow later revival.

<!-- fr:journal kind=decision scope=spec id=d-images created=2026-11-08T21:39:16+00:00 decided_by=operator -->
### d-images · decision · Stop builds, archive the fork, keep GHCR packages

The agent-images legs are removed, derio-net/vibe-kanban is archived, and published packages are retained so old commits still resolve.

<!-- fr:journal kind=decision scope=spec id=d-shipping created=2026-11-08T21:39:16+00:00 decided_by=operator -->
### d-shipping · decision · Two PRs with live checks

vk-local stays until Phase 2 so Phase 1 never rolls the pod. Phase 2 is held until the triage run ends and the archive verifies.
