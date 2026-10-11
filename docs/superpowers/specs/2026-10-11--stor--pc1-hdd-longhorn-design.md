# pc-1's three idle HDDs into Longhorn — a health-gated, isolated `hdd` tier for CI scratch

**Date:** 2026-10-11
**Layer:** stor (Layer 4, fix/extension — existing building/operating posts are updated, no new post)
**Status:** Draft — spec only; planning waits for the operator's go
**Issue:** derio-net/frank#824 (decisions owed: [comment 6106885345](https://github.com/derio-net/frank/issues/824#issuecomment-6106885345))

## Context

pc-1 (`192.168.55.71`, worker, `role=cicd`) carries three data HDDs that were never
wired into anything. Longhorn has only ever seen the 62 GB `EPHEMERAL` partition on its
64 GB boot SSD, and that disk is over-committed. Measured 2026-10-11:

| device | model | size | WWID | state |
|---|---|---|---|---|
| `sda` | Crucial M4-CT064M4SSD2 | 64 GB | `naa.500a075103235393` | boot: EFI/META/STATE + `EPHEMERAL` (`sda4`, Longhorn's only pc-1 disk) |
| `sdb` | WDC WD10EADS-00L (WD Green, 2008–09) | 1.0 TB | `naa.50014ee2ae0311c3` | blank, no partition table |
| `sdc` | WDC WD10EADS-00L (WD Green, 2008–09) | 1.0 TB | `naa.50014ee203581a1f` | blank, no partition table |
| `sdd` | WDC WD5000AAKS-0 (WD Blue, 2008–09) | 500 GB | `naa.50014ee0556235e7` | GPT, one 500 GB xfs partition `sdd1`, unmounted, contents unknown |

(`talosctl -n 192.168.55.71 get disks` / `get discoveredvolumes` / `get volumestatus`;
Talos v1.12.6. All three HDDs report an empty `SERIAL`, so the WWID is the only stable
identifier Talos exposes for them.)

Longhorn's view of pc-1: one disk, `default-disk-082400000000`, `storageMaximum` 57 Gi,
`storageScheduled` 60 Gi. That is past its ceiling, so pc-1 accepts no new replicas.

`patches/phase03-longhorn/README.md` lists these drives as replica disks, but only
gpu-1 ever received a mount patch (`401-gpu1-extra-disks.yaml`). The README's inventory
has also drifted: it lists 500/640/640 GB HDDs and gives the SSD as `sdc`.

### Three things the live cluster showed that the issue did not

1. **A disk tag does not isolate anything here.** The Longhorn setting
   `allow-empty-disk-selector-volume` is `true`, which is the chart default. A volume
   with no `diskSelector` may therefore schedule onto *any* disk, tagged or not. gpu-1's
   "dedicated" `gpu-local` SSDs prove it. Their only consumers by design are
   `longhorn-gpu-local` volumes, yet they hold ~1.1 TiB of scheduled replicas from the
   default pool and from `longhorn-cicd`: `secure-agent-pod/agent-home`,
   `n8n-01/n8n-01-data`, `zot/zot-pvc`, ~40 Tekton workspaces and more. Meanwhile gpu-1's
   own NVMe default disk has **0 Gi scheduled**: Longhorn prefers the disk with the most
   free space. Tag pc-1's HDDs `hdd` without changing that setting, and the default pool
   would favour them for the same reason.
2. **`longhorn-cicd` was never pinned to pc-1.** Its header comment reads "single
   replica for pc-1 CI/CD workloads", but the class has no disk or node selector. Its
   replicas sit wherever there is room: 155 replicas cluster-wide on gpu-1, only 8 on pc-1.
3. **An HDD-only class is single-replica by construction.**
   `replica-soft-anti-affinity` is `false`, so replicas of one volume must sit on
   different nodes. Only pc-1 will have `hdd` disks, so a `longhorn-hdd` volume can have
   exactly one replica. Nothing stored there has redundancy across the three drives.
   That restricts it to re-creatable data.

### Who consumes `longhorn-cicd` today

- Long-lived: `gitea/gitea-shared-storage` (repos, 10 Gi; `apps/gitea/values.yaml:88`),
  `zot/zot-pvc` (image blobs, 50 Gi; `apps/zot/values.yaml:84`),
  `gitea-runner/act-runner-data` (20 Gi; `apps/gitea-runner/manifests/pvc.yaml:19`).
- Per-run CI workspaces (`volumeClaimTemplate`s, ~150 live PVCs at 2/8 Gi):
  - `apps/tekton/triggers/eventlistener-github.yaml`: 11 sites. Their pods are already
    pinned to pc-1 (`nodeSelector: {kubernetes.io/hostname: pc-1}`).
  - `apps/tekton/triggers/kid-laptops-ci.yaml:86`: not node-pinned, by design (comment at
    `:84`).
  - `apps/tekton/triggers/triggertemplate.yaml:41`: the generic Gitea CI template, not
    node-pinned.

## Requirements

R1. Before any HDD receives Longhorn data, each of the three drives is SMART-checked from a privileged debug pod: overall health, the attribute table and a completed **long** self-test. A drive is excluded if any of these hold: overall health FAIL, the long test fails, or attribute 5 (Reallocated Sector Count), 197 (Current Pending Sector) or 198 (Offline Uncorrectable) has a non-zero raw value. Power-On Hours (9), Load Cycle Count (193) and UDMA CRC Error Count (199) are recorded but are not gates. Each drive's results and verdict are posted to frank#824.
R2. `sdd1` is mounted read-only once and its contents listed. If it holds no user data, `sdd` is wiped and proceeds through the same path as the other admitted drives. If it holds anything, a summary (top-level paths and sizes, no file contents) is posted to frank#824 and `sdd` is paused until the operator rules on it. `sdb` and `sdc` go ahead regardless. No agent copies data off `sdd` or wipes it without that ruling.
R3. Each admitted drive is provisioned by a Talos `UserVolumeConfig` that selects it by WWID, as a CEL `diskSelector.match` on `disk.wwid`, never by `/dev/sdX`. The volume is xfs and mounted at `/var/mnt/hdd-<last 8 hex digits of the WWID>`. All of them ship in one Omni ConfigPatch scoped to pc-1's cluster-machine UUID, and every mount survives a reboot.
R4. Each admitted drive's mount is a Longhorn disk on `nodes.longhorn.io/pc-1`. The disk is named `hdd-<wwid8>`, tagged `hdd`, has `storageReserved: 0` (the global 15 % `storageMinimalAvailablePercentage` is the floor) and `allowScheduling: true`. The exact disk entries live in git as a patch file applied by a documented `# manual-operation`. ArgoCD never owns the `nodes.longhorn.io` CR. gpu-1's two existing `gpu-local` disks are backfilled into the same convention, and pc-1's existing default disk is left as it is.
R5. `apps/longhorn/values.yaml` sets `defaultSettings.allowEmptyDiskSelectorVolume: false`, so no volume without a `diskSelector` is newly scheduled onto a tagged disk, whether `hdd` or `gpu-local`. Existing replicas are not moved by this change.
R6. A new StorageClass `longhorn-hdd` (ArgoCD-managed in `apps/longhorn/manifests/`) provisions single-replica volumes restricted to `hdd`-tagged disks.
R7. Every per-run CI workspace `volumeClaimTemplate` uses `longhorn-hdd`: all 11 sites in `eventlistener-github.yaml`, plus `kid-laptops-ci.yaml` and `triggertemplate.yaml`. Gitea repos, Zot blobs and act-runner data stay on `longhorn-cicd`.
R8. The repo tells the truth afterwards. `patches/phase03-longhorn/README.md` carries the measured inventory (model, size, WWID, role), names the new files, and fixes its `phase3-longhorn` path typos. `frank-gotchas.md` gains a one-liner (full prose in `docs/runbooks/frank-gotchas/storage-secrets-ssa.md`) that a Longhorn disk tag does not isolate while `allow-empty-disk-selector-volume` is true. The manual ops are synced to `docs/runbooks/manual-operations.yaml`, and the Layer 4 posts `building/03-storage` and `operating/02-storage-backups` describe the HDD tier.
R9. An offline guard test, run in CI, pins the declarative half. Its assertions:
   - The ConfigPatch selects disks by WWID and contains no `/dev/sd`.
   - Every Longhorn disk path in the node-disk patch file equals a `UserVolumeConfig` mount.
   - `longhorn-hdd` has `numberOfReplicas: "1"` and `diskSelector: hdd`.
   - `allowEmptyDiskSelectorVolume` is `false`.
   - Every CI `volumeClaimTemplate` names `longhorn-hdd`, and no long-lived consumer does.

## Design

### Operator rulings (brainstorm, 2026-10-11)

| # | Decision (issue comment item) | Ruling |
|---|---|---|
| 1 | SMART gate | **Strict**: overall/long-test failure or any non-zero 5/197/198 excludes the drive (R1) |
| 2 | `sdd`'s xfs data | **Stop and ask**: any content pauses `sdd` alone for an operator ruling (R2) |
| 3 | Pool placement | **(a) dedicated**: `hdd` tag + `longhorn-hdd` class, and flip `allow-empty-disk-selector-volume` to `false` (R5, R6) |
| 3b | Which workloads move | **CI scratch only**, a new class; Gitea, Zot and act-runner stay on `longhorn-cicd` (R7) |
| 3c | Which CI workspaces (round 2) | **All of them**, including the two non-pinned templates, accepting the pc-1 dependency (see Risks) |
| 4 | Stable binding | **Talos `UserVolumeConfig` + WWID CEL selector** (R3), not legacy `machine.disks` |
| 5 | Codify or manual | **Manual op, with the exact patch held in git**; gpu-1 is backfilled (R4) |
| — | Verification | **`live`, post-merge** for every row; offline guards run in CI (R9) |

### Repo changes

1. **`patches/phase03-longhorn/402-pc1-hdd-volumes.yaml`**: an Omni `ConfigPatches`
   resource. It has `id: 402-pc1-hdd-volumes`, labels `omni.sidero.dev/cluster: frank` and
   `omni.sidero.dev/cluster-machine: 03de0294-0480-05ab-3106-410700080009` (pc-1, per
   `patches/README.md:11`). Its `spec.data` is a multi-document config with one
   `UserVolumeConfig` per admitted drive:

   ```yaml
   apiVersion: v1alpha1
   kind: UserVolumeConfig
   name: hdd-ae0311c3                     # sdb today; name follows the WWID, never the sdX letter
   provisioning:
     diskSelector:
       match: disk.wwid == "naa.50014ee2ae0311c3"
     minSize: 900GB
     grow: true
   filesystem:
     type: xfs
   ---
   # hdd-03581a1f  → naa.50014ee203581a1f (minSize 900GB)
   # hdd-556235e7  → naa.50014ee0556235e7 (minSize 450GB) — only if R2 clears sdd
   ```

   Talos mounts a user volume at `/var/mnt/<name>`. A drive excluded by R1 or held back by
   R2 is simply left out of the patch. The implementer checks the exact field set
   (`minSize` requirement, CEL field name `disk.wwid`) against the Talos v1.12 reference
   before writing it. The values above come from the live `get disks` output.
   `401-gpu1-extra-disks.yaml` is **not** migrated; it keeps working on `machine.disks`.

2. **`patches/phase03-longhorn/longhorn-node-disks-pc-1.yaml`** and
   **`…-gpu-1.yaml`**: merge-patch bodies for `nodes.longhorn.io/<node>`, each holding
   only that node's extra disks:

   ```yaml
   spec:
     disks:
       hdd-ae0311c3:
         path: /var/mnt/hdd-ae0311c3/
         diskType: filesystem
         allowScheduling: true
         evictionRequested: false
         storageReserved: 0
         tags: ["hdd"]
       # … one entry per admitted drive
   ```

   The gpu-1 file reproduces the live `gpu-sda-4000000000000` / `gpu-sdb-4000000000000`
   entries exactly, so applying it is a no-op today. The entry map is keyed by disk name,
   so a merge patch never touches the `default-disk-*` entry longhorn-manager wrote.

3. **`apps/longhorn/manifests/storageclass-longhorn-hdd.yaml`**:

   ```yaml
   apiVersion: storage.k8s.io/v1
   kind: StorageClass
   metadata:
     name: longhorn-hdd
   provisioner: driver.longhorn.io
   reclaimPolicy: Delete
   volumeBindingMode: Immediate
   allowVolumeExpansion: true
   parameters:
     numberOfReplicas: "1"        # only pc-1 has hdd disks and node anti-affinity is hard
     diskSelector: "hdd"
     dataLocality: "disabled"     # the selector already fixes the replica's node
   ```

   The `longhorn-cicd` header comment is corrected to say what that class really does,
   which is single-replica, unpinned.

4. **`apps/longhorn/values.yaml`**: `defaultSettings.allowEmptyDiskSelectorVolume:
   false`, with a comment carrying the gpu-local evidence above. Chart 1.11.2 exposes the
   key (`helm show values longhorn --version 1.11.2`). Expected effect: new default-pool
   replicas on gpu-1 go to its NVMe default disk (928 Gi max, 0 scheduled) instead of the
   `gpu-local` SSDs. Existing replicas stay where they are until something rebuilds them
   (`replica-auto-balance` is `disabled`).

5. **CI workspaces → `longhorn-hdd`**: the 13 `storageClassName: longhorn-cicd` lines
   listed in R7. The `kid-laptops-ci.yaml:84` comment is rewritten, since the class is now
   pinned to pc-1's disks even though the pod is not.

6. **Docs (R8)** and **guard test (R9)**: `scripts/tests/test_pc1_hdd_longhorn.py`.

### Live sequence (manual operations; the plan front-loads these that can precede merge)

The ordering exists so the default pool never sees an HDD that it could schedule onto.

1. **SMART (R1).** Run a privileged debug pod on pc-1 from an image that already ships
   `smartctl`, pinned by digest, with no package install at runtime. Steps:
   `smartctl -H -A -i`, then `smartctl -t long` on all three drives in parallel. Wait for
   each drive's own polling time (`smartctl -c`), then `smartctl -l selftest`. Post results
   to #824 and delete the pod.
2. **`sdd` inspection (R2).** Mount `sdd1` with `mount -o ro,norecovery` (xfs refuses a
   plain read-only mount when its log is dirty), list it, unmount. If it is empty, wipe it
   with `talosctl -n 192.168.55.71 wipe disk sdd`, which Talos needs before it will
   provision a disk that already has a partition table. Otherwise post the summary and
   hold `sdd`.
3. **Talos volumes (R3).** Run `omnictl apply -f
   patches/phase03-longhorn/402-pc1-hdd-volumes.yaml`. Verify with
   `talosctl get volumestatus` / `mountstatus` that each `hdd-*` volume is `ready` at
   `/var/mnt/hdd-*`.
4. **Longhorn disks, unschedulable first.** Apply
   `longhorn-node-disks-pc-1.yaml` with every entry's `allowScheduling` overridden to
   `false`, then confirm the disks report `Ready`.
5. **Merge.** ArgoCD lands the setting, `longhorn-hdd` and the CI repoint. Assert on the
   artifact, not on ArgoCD's sync status:
   `kubectl -n longhorn-system get settings.longhorn.io allow-empty-disk-selector-volume`
   must read `false`. Also compare the app's `status.operationState` revision against the
   merge SHA (see the stale-revision gotchas). Between the merge and step 6, new CI PVCs
   sit `Pending`. That is expected and clears once scheduling is allowed.
6. **Allow scheduling.** Re-apply `longhorn-node-disks-pc-1.yaml` as written in git
   (`allowScheduling: true`).
7. **Prove it.** Run three checks:
   - A test PVC on `longhorn-hdd` binds, its replica's `diskPath` is a `/var/mnt/hdd-*`,
     and a pod writes and reads it.
   - A test PVC on `longhorn` gets no replica on any `hdd-*` or `gpu-local` disk.
   - The next real Tekton run's workspace lands on an `hdd-*` disk.
8. **Reboot survival (R3).** Reboot pc-1 with a `kubectl` drain, not
   `talosctl reboot --drain` (see the Omni gotchas). Then confirm that the mounts and the
   Longhorn disks come back `Ready`.

## Verification

strategy: live
- stor-pc1-hdd-health-gated: live — SMART must run on the physical drives; no pre-merge strategy can reach pc-1's hardware
- stor-pc1-hdd-stable-binding: live — the WWID binding is only proven by Talos provisioning the real disks and by a reboot
- stor-hdd-pool-isolated: live — placement is decided by the live Longhorn scheduler against live settings; CI checks only the declared inputs (R9)
- stor-ci-workspaces-on-hdd: live — needs a real PipelineRun to provision its workspace

## Test Plan

| Req | Check | When |
|-----|-------|------|
| R9 (R3–R7 declared) | `scripts/tests/test_pc1_hdd_longhorn.py` | CI |
| R1 | Per-drive SMART table + verdict posted on #824 | pre-merge (manual op) |
| R2 | `sdd` listing posted, or the wipe recorded, on #824 | pre-merge (manual op) |
| R3 | `talosctl get volumestatus` shows each `hdd-*` `ready` at `/var/mnt/hdd-*`, before and after a pc-1 reboot | post-merge — operator-driven |
| R4 | `nodes.longhorn.io/pc-1` lists the `hdd-*` disks `Ready`/`Schedulable` with tag `hdd`; the gpu-1 patch re-applies as a no-op | post-merge — operator-driven |
| R5 | Live setting reads `false`; a fresh `longhorn`-class test PVC has no replica on an `hdd-*` or `gpu-local` disk | post-merge — operator-driven |
| R6, R7 | A `longhorn-hdd` test PVC and the next real Tekton workspace each have their replica on a `/var/mnt/hdd-*` path | post-merge — operator-driven |
| R8 | Capacity audit's physical-disk table shows pc-1's admitted drives as `in use` | post-merge — operator-driven |

## Out of scope

- Moving existing replicas off gpu-1's `gpu-local` SSDs, or anything else already placed.
  The flip only governs new placement. Relocation would be its own change.
- Easing pc-1's over-committed `EPHEMERAL` default disk (60/57 Gi), which keeps its
  current replicas.
- Moving Gitea, Zot or act-runner data, which stays on `longhorn-cicd` by ruling 3b.
- Migrating gpu-1's `401` patch from `machine.disks` to `UserVolumeConfig`.
- Alerting on HDD health. Longhorn's `node-disk-health-monitoring` is already on; a
  SMART-based alert would be a follow-up.

## Risks

- **CI now depends on pc-1 (ruling 3c).** `kid-laptops-ci` and the generic Gitea
  template used to provision anywhere. Their workspaces now need pc-1's disks, so a pc-1
  outage leaves those PipelineRuns `Pending`. That includes a recurrence of the
  2013-board brown-outs (`docs/investigations/2026-05-11--hw--pc-1-reboot-investigation.md`).
  The pods themselves can still run on other nodes and reach the replica over iSCSI.
  The `eventlistener-github` pipelines were already pinned to pc-1 and lose nothing.
- **2008-era drives with no redundancy.** R1 is the gate; one replica is the accepted
  cost of keeping only re-creatable data there. A drive that dies takes in-flight CI
  workspaces with it, and they are re-run.
- **The setting flip is global.** It affects new placement for every tagged disk, which
  includes `gpu-local`. Existing replicas are not evicted. One assumption needs checking
  in the plan: that Longhorn does not mark existing empty-selector replicas on tagged
  disks as failed or unschedulable after the flip. Step 5's assertion plus a
  `kubectl get volumes.longhorn.io` robustness sweep catches it if it does.
- **WD Green head parking.** The WD10EADS parks its heads after 8 s idle. Load Cycle
  Count (193) is recorded under R1 as a baseline, not a gate.
- **`sdd` misjudged.** R2 resolves doubt toward the operator, so `sdd` is only wiped
  after a listing shows it is empty.

## Implementation Plans

None yet. Planning starts after the operator rules on this spec.
