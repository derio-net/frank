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

The requesting repo is private; this repo is public. Operator asked for discretion. Spec, plan, PR body, runbook entries and any blog text must not name the consumer repo, its product, or its corpus, and must not reproduce its benchmark queries, document titles or corpus statistics. The bare 'multilingual' property IS kept — it is the generic technical driver for choosing bge-m3 over an English-centric model. Treat a breach as a blocking review finding.

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

<!-- fr:journal kind=discovery scope=spec id=disc-gate-pass created=2026-08-02T15:33:17 -->
### disc-gate-pass · discovery · GATE PASSED: OVMS enumerates the iGPU on a Talos control-plane node

Ran openvino/model_server:2026.2.1-gpu on mini-1 with a real ResourceClaim. Log: 'Available devices for Open VINO: CPU, GPU'. The design's central premise is verified, not hoped for. Run during DESIGN rather than deferred to phase 1, which is what surfaced the findings below before a plan was written.

<!-- fr:journal kind=review scope=spec id=r-model-acquisition created=2026-08-02T15:33:19 -->
### r-model-acquisition · review · Spec review: the model-acquisition design was disproven and replaced

Draft had initContainers running 'ovms --pull'. The gate showed three blocking facts. (1) Without --weight-format, pull downloads raw HF safetensors and the model then fails to load: 'Either openvino_tokenizer.xml was not provided or it was not loaded correctly'. (2) With --weight-format int8 the real error appears: 'missing optimum-intel. Use the ovms package with optimum-intel installed' — and Docker Hub publishes only 2026.2.1 and 2026.2.1-gpu for this release, neither of which carries it. (3) The pre-converted OpenVINO/ HF org has only bge-base-en-v1.5 and bge-reranker-base, i.e. ENGLISH-only variants — precisely the model class this request exists to move away from. Operator chose a CI-built model image (Frank's existing apps/<app>/docker + build workflow pattern, as used by comfyui/openrgb/gpu-switcher), built with OVMS's own export_model.py so the IR, tokenizer XML, graph.pbtxt and merged config.json all land in the layout OVMS expects. Runtime stays STOCK upstream; only a bag of model files is maintained here. Rejected alternatives: custom OVMS image with optimum-intel (in-pod conversion on an etcd member, runtime HF egress, unpinned bytes); ~20 community HF IR conversions (unvetted personal accounts); operator converts by hand (breaks declarative-only).

<!-- fr:journal kind=review scope=spec id=r-readiness-probe created=2026-08-02T15:33:20 -->
### r-readiness-probe · review · Spec review: readiness probe would have marked a dead pod healthy

Draft used GET /v2/health/ready. The gate showed OVMS answering that endpoint with 200 while its only servable sat in LOADING_PRECONDITION_FAILED — it reports SERVER liveness, not model readiness. Left as drafted it would have produced a Ready pod, a green ArgoCD Application, and every request failing. Changed to model-level /v2/models/<name>/ready, with /v1/config as the per-servable diagnostic. Same silent-green family as the config-reaches-the-process traps already in this repo's gotchas.

<!-- fr:journal kind=review scope=spec id=r-seed-version-gate created=2026-08-02T15:33:22 -->
### r-seed-version-gate · review · Spec review: seed-if-absent would have reproduced a known Frank bug

The initContainer seeding the model PVC must be version-gated by a marker file, not 'copy if the directory is absent'. Frank already documents this exact failure for the comfyui custom-nodes PVC: an image update never reaches an already-seeded volume, pods stay Ready, and stale content is served indefinitely. Written into the spec so the first model bump does not silently fail to deploy.
