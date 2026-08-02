# Journal: 2026-08-02--infer--igpu-embedding-rerank

<!-- fr:journal kind=decision scope=spec id=d-runtime created=2026-08-02T13:59:15 -->
### d-runtime · decision · Runtime: OpenVINO Model Server

Operator chose OVMS over llama.cpp-SYCL and Infinity-OpenVINO. One server hosts BOTH models (one Deployment, one ResourceClaim, one iGPU); /v3/rerank already returns the exact {results:[{index,relevance_score}]} shape with no adapter; --target_device NPU stays reachable later as a values change. Accepted costs: /v3/ rather than /v1/ paths, and a pull/convert step before serving.

<!-- fr:journal kind=decision scope=spec id=d-routing created=2026-08-02T13:59:17 -->
### d-routing · decision · Routing: in-cluster ClusterIP only, no LiteLLM change

Operator chose the minimal exposure. No LoadBalancer IP, no IngressRoute, no LiteLLM alias. LiteLLM's rerank providers each assume their own URL path, so fronting /v3/rerank means writing a shim — the highest-effort, lowest-information part of the request, and the part the request itself hedged. Aliasing only embeddings would put half a pair on the gateway, which is more confusing than neither. Laptop access is kubectl port-forward. Revisit when a second consumer exists.

<!-- fr:journal kind=decision scope=spec id=d-footprint created=2026-08-02T13:59:18 -->
### d-footprint · decision · Footprint: 1 replica pinned to mini-1, hard ceiling

Operator chose one replica over three. requests 500m/2Gi, limits 2 CPU/6Gi. Pinned by hostname to mini-1 (most headroom of the three control-plane minis), leaving mini-2 and mini-3 untouched as comparison arms for the control-plane-health check. Scaling to 3 later is a replicas change. One replica produces every number the spike needs; three would triple control-plane exposure before anything has been measured.

<!-- fr:journal kind=decision scope=spec id=d-model-tiers created=2026-08-02T13:59:20 -->
### d-model-tiers · decision · Subagent model tiers bound

fr models resolve was unbound for claude-code. Operator chose mechanical=haiku, standard=sonnet, hard=opus. Persisted to ~/.config/fr/models.yaml.

<!-- fr:journal kind=decision scope=spec id=d-discretion created=2026-08-02T13:59:21 -->
### d-discretion · decision · Consumer repo stays unnamed in all public artifacts

The requesting repo is private; this repo is public. Operator asked for discretion. Spec, plan, PR body, runbook entries and any blog text must not name the consumer repo, its product, or its corpus, and must not reproduce its benchmark queries, document titles or corpus statistics. The multilingual (three European languages) property IS kept — it is the generic technical driver for choosing bge-m3 over an English-centric model. Treat a breach as a blocking review finding.

<!-- fr:journal kind=review scope=spec id=r-image-tag created=2026-08-02T13:59:47 -->
### r-image-tag · review · Spec review: image tag was deferred when it was answerable

Draft listed 'OVMS GPU tag not pinned yet' as a named gap and left phase 1 to pick one. Docker Hub shows 2026.2.1-gpu as the newest released GPU tag (2026-07). Pinned in the spec; the gap now reads correctly as 'unverified that THIS build enumerates Meteor Lake under Talos 6.18', which is the compute gap, not a tagging question. Deferring an answerable question into the plan is how latest-gpu ends up shipping.

<!-- fr:journal kind=review scope=spec id=r-fsgroup created=2026-08-02T13:59:48 -->
### r-fsgroup · review · Spec review: missing fsGroup would have failed the pod at first boot

Draft specified runAsUser 5000 (verified: the OVMS image's own non-privileged user) but no fsGroup. Longhorn PVCs mount root-owned, so the pull initContainer — running as 5000 — could not have written the model repository. Same trap already documented for Tekton workspaces in this repo's gotchas. Added fsGroup: 5000 and called out that the failure is visible only if you watch the initContainer rather than the pod.

<!-- fr:journal kind=review scope=spec id=r-cpu-control created=2026-08-02T13:59:50 -->
### r-cpu-control · review · Spec review: promoted the strongest counter-argument into the test plan

The minis are 14-core and ~95% idle, so 'the iGPU beats these CPUs for a 568M cross-encoder' is a hypothesis, not a premise. Without a CPU arm the spike can only report that the iGPU works, never that claiming it was worth the DRA plumbing. Added --target_device CPU on the same node as a control arm (Test Plan row 5) and stated that a CPU win is a legitimate, cheaper result.

<!-- fr:journal kind=review scope=spec id=r-codebase-checks created=2026-08-02T13:59:51 -->
### r-codebase-checks · review · Spec review: codebase references verified

Checked each concrete reference the spec makes: apps/intel-gpu-driver/ exists (the phase05 README's apps/intel-gpu-plugin/ does not); project 'infrastructure' is what all 68 Application CRs use; storageClass 'longhorn' exists and is default; docs/runbooks/frank-gotchas/ has an index README requiring a row for any new topic file; blog/content/docs/building/10-local-inference and operating/07-inference both exist, so this extends Layer 11 rather than creating a layer; scripts/ already holds committed Python. No dangling references.

<!-- fr:journal kind=discovery scope=spec id=disc-dra-proof created=2026-08-02T13:59:52 -->
### disc-dra-proof · discovery · DRA path proven live, with a negative control

A throwaway ResourceClaim + pod on mini-1 got /dev/dri/{card0,renderD128} injected, crw-rw-rw- root:root — so no render-GID/supplementalGroups work is needed. The identical pod WITHOUT a claim had no /dev/dri at all, which matters because Frank's containerd has cluster-wide CDI discovery enabled (phase05) and could plausibly have injected the device for free. Also: ResourceSlice advertises capacity.memory 0 (shared host RAM), so a claim requesting GPU memory can never satisfy. Egress to huggingface.co from a mini pod works. PodSecurity enforces baseline, warns on restricted. Both probes deleted; resourceclaims back to empty.
