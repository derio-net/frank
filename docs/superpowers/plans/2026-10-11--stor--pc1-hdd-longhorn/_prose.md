# pc-1 HDDs into Longhorn — implementation plan

**Status:** In Progress
**Spec:** `docs/superpowers/specs/2026-10-11--stor--pc1-hdd-longhorn-design.md` (operator approved 2026-10-11)
**Issue:** derio-net/frank#824 (referenced, not a tracking issue)

## Shape

Two phases, one PR.

**Phase 1 (agentic, standard)** declares everything that lives in git, test-first:

- a guard test (`scripts/tests/test_pc1_hdd_longhorn.py`) that reads the admitted drive set
  from the Talos patch itself, so removing a drive later is a two-file deletion with the test
  still green;
- the Omni ConfigPatch `402-pc1-hdd-volumes.yaml` (three `UserVolumeConfig`s bound by WWID);
- the Longhorn node-disk patch files for pc-1 and gpu-1 (manual-op inputs, never ArgoCD-owned);
- the `longhorn-hdd` StorageClass and `allowEmptyDiskSelectorVolume: false`;
- all 11 per-run CI workspace templates repointed to `longhorn-hdd`;
- the R8 documentation sweep and the gotcha.

**Phase 2 ([manual], back-loaded)** is the operator's: SMART gate and the `sdd` inspection
(either may delete a drive from the two patch files with a commit on this PR), the Omni apply,
the Longhorn disks added unschedulable, then merge, asserting the flipped setting on the live
cluster before allowing scheduling, proving placement, and a reboot. The PR merges only after
Phase 2's pre-merge tasks, because the Talos volumes and the unschedulable disks must exist
first; the post-merge tasks are the spec's Test Plan rows.

Why one agentic phase: every repo change serves the same ask and reviews comfortably as one
diff (~700 lines, most of it documentation); a split would add a full executor and reviewer
round trip for no independent review value.

## Ordering invariant

At no moment may an `hdd`-tagged disk be schedulable while `allow-empty-disk-selector-volume`
is still `true`; otherwise the default pool favours the HDDs (most free space). Phase 2 enforces it:
disks are added with `allowScheduling: false` before merge, and flipped to `true` only after
the live setting reads `false`.
