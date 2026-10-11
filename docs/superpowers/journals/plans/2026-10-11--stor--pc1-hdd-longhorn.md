# Journal: 2026-10-11--stor--pc1-hdd-longhorn

<!-- fr:journal kind=decision scope=plan id=plan-one-agentic-phase created=2026-10-11T19:15:26+00:00 -->
### plan-one-agentic-phase · decision · One agentic phase plus a back-loaded [manual] phase

Every repo change serves one ask and reviews as one ~700-line diff (mostly docs). The operator's SMART/sdd/apply/merge sequence is the trailing [manual] phase; a drive SMART excludes is removed by an operator commit on this PR, which the guard tolerates because it derives the drive set from the 402 patch.

<!-- fr:journal kind=discovery scope=plan id=p1-uservolumeconfig-schema created=2026-10-11T20:27:41+00:00 phase=1 -->
### p1-uservolumeconfig-schema · discovery · Talos v1.12 UserVolumeConfig schema matches the spec (phase 1)

Checked siderolabs/talos v1.12.6 website/content/v1.12/reference/configuration/block/uservolumeconfig.md:
provisioning.diskSelector.match (CEL), minSize (optional), maxSize, grow, filesystem.type, mount at /var/mnt/<name>.
`disk.wwid` is a valid CEL field: the CEL `disk` variable is the block.DiskSpec protobuf, which has `wwid` (pkg/machinery/resources/block/disk.go). No spec amendment needed; minSize is optional upstream but kept as a safety floor.

<!-- fr:journal kind=discovery scope=plan id=p1-vendor-vct-schema created=2026-10-11T20:27:41+00:00 phase=1 -->
### p1-vendor-vct-schema · discovery · apps/tekton/vendor contains CRD-schema volumeClaimTemplate keys (phase 1)

The guard's volumeClaimTemplate walk skips apps/tekton/vendor, whose upstream CRD schemas contain `volumeClaimTemplate` mappings that are not workspaces. The 11 real sites are all asserted.

<!-- fr:journal kind=discovery scope=plan id=p1-helm-render created=2026-10-11T20:27:41+00:00 phase=1 -->
### p1-helm-render · discovery · Chart 1.11.2 exposes allowEmptyDiskSelectorVolume and renders false (phase 1)

helm show values lists the key (default ~); helm template with apps/longhorn/values.yaml renders `allow-empty-disk-selector-volume: false` in the default-setting ConfigMap.

<!-- fr:journal kind=discovery scope=plan id=p1-suite-scope created=2026-10-11T20:27:41+00:00 phase=1 -->
### p1-suite-scope · discovery · Full suite run excludes hugo-building tests (phase 1)

scripts/tests ran with test_image_optimization_adoption, test_series_index_adoption and test_series_index_resync ignored (they build with hugo and can hang); alert-agent handler suite not run. Run in CI.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t1 created=2026-10-11T20:27:41+00:00 phase=1 -->
### no-refactor-p1-t1 · discovery · no-refactor-because P1.T1 (phase 1)

Single new test module written once against the spec; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-10-11T20:27:41+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

Three new declarative files, no pre-existing code touched; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-10-11T20:27:41+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

Added one manifest and one commented values key; header comment rewrite was the only edit to existing text.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t4 created=2026-10-11T20:27:41+00:00 phase=1 -->
### no-refactor-p1-t4 · discovery · no-refactor-because P1.T4 (phase 1)

Mechanical one-token repoint plus a comment rewrite; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t5 created=2026-10-11T20:27:41+00:00 phase=1 -->
### no-refactor-p1-t5 · discovery · no-refactor-because P1.T5 (phase 1)

Doc edits only; nothing to clean.
