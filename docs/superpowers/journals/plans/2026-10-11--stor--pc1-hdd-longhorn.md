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

<!-- fr:journal kind=review scope=plan id=p1-review-r1 created=2026-10-11T20:46:28+00:00 phase=1 -->
### p1-review-r1 · review · Phase 1 code review: approve with minor fixes — 4 findings (3 in, 1 out) (phase 1)

Reviewer checked the 402 ConfigPatch (WWID CEL selectors, hdd-<last8> names, pc-1 machine label), the node-disk patches (gpu-1 file equals README Step 6 live entries → no-op), longhorn-hdd parameters, the values flip, the 11 Tekton repoint sites (no other line changed), Gitea/Zot/act-runner unchanged, docs and Hugo shortcodes; ran the guard (9 passed). No ArgoCD sync risk. Findings: p1-r1, p1-r2, p1-r3 (in), p1-r4 (out).

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-10-11T20:46:28+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · test_docs_tell_the_truth covers 3 of 7 R8 docs, matches only "on pc-1"/"pins pvcs", exempts any "correction" line, never asserts storage-secrets-ssa.md prose (phase 1)

scripts/tests/test_pc1_hdd_longhorn.py:146-161 at 1d9fa42c.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-10-11T20:46:28+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · Zot checked by whole-file substring plus a vacuous `assert zot is not None` (phase 1)

scripts/tests/test_pc1_hdd_longhorn.py:137-144; apps/zot/values.yaml:80-84.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-10-11T20:46:28+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · phase03 README Step 8 and operating/02 point at manual-op ids not yet in manual-operations.yaml (phase 1)

R8 says the manual ops are synced; the sync was deferred to the phase 2 close-out.

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-10-11T20:46:28+00:00 phase=1 state=open review_scope=out -->
### p1-r4 · finding [open] (reviewer: out of scope) · phase3-longhorn typo survives in patches/README.md:28 and patches/phase03-longhorn/longhorn-values.yaml:9 (phase 1)

Pre-existing; R8 names only the phase03 README.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-10-11T20:46:28+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: test_docs_tell_the_truth covers 3 of 7 R8 docs, matches only "on pc-1"/"pins pvcs", exempts any "correction" line, never asserts storage-secrets-ssa.md prose (phase 1)

Guard now scans README.md, the longhorn-cicd SC, building/03-storage, building/27, operating/02 and operating/22; matches '(pinned to|pins (PVCs) to|pinned on|for|on) pc-1' on lines naming longhorn-cicd; exempts only a dated 'Correction <date>' note; asserts the storage-secrets-ssa.md '## …allow-empty-disk-selector-volume' heading. Negative controls (old SC header, old building/27 subheading, 'pins PVCs … on pc-1') are caught.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-10-11T20:46:28+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: Zot checked by whole-file substring plus a vacuous `assert zot is not None` (phase 1)

assert zot['pvc']['storageClassName'] == 'longhorn-cicd'.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-10-11T20:46:28+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: phase03 README Step 8 and operating/02 point at manual-op ids not yet in manual-operations.yaml (phase 1)

The five stor-pc1-* blocks from 02.yaml appended to docs/runbooks/manual-operations.yaml (status pending) and guarded by test_manual_operations_synced, which was red before the append. Full-file re-sort skipped to avoid churning 158 unrelated entries; phase 2 close-out still runs /sync-runbook for statuses.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-10-11T20:46:28+00:00 phase=1 state=open resolves=p1-r4 out_of_scope=true -->
### p1-r4-resolved · finding [out-of-scope] · resolves p1-r4: phase3-longhorn typo survives in patches/README.md:28 and patches/phase03-longhorn/longhorn-values.yaml:9 (phase 1)

Both typos predate this change and are outside R8's named file; fixing them is the operator's call.
