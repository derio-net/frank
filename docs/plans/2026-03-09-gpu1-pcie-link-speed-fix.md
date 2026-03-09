# RTX 5070 PCIe Link Speed Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix `gpu-1` PCIe link speed from Gen 1 (2.5 GT/s) to Gen 4 (16 GT/s) by updating the BIOS from F3 to F6 and forcing PCIe Gen 4 in BIOS settings.

**Architecture:** All work is physical/firmware — no cluster code changes. BIOS updated via Gigabyte Q-Flash from USB. PCIe Gen 4 forced at firmware level to bypass a confirmed bug in NVIDIA open kernel modules (570.x–590.x) where Gen 5 training failure falls back to Gen 1 instead of Gen 4. See design doc: `docs/plans/2026-03-09-gpu1-pcie-link-speed-fix-design.md`.

**Tech Stack:** Gigabyte Q-Flash, Talos Linux, kubectl, talosctl

---

### Task 1: Prepare the USB Drive

**Files:** None (local workstation)

**Step 1: Download BIOS files**

Go to the Gigabyte Z790 Eagle AX (Rev 1.x) support page and download:
- **F6** (latest — target version)
- **F3** (current — rollback fallback)

Place both `.F6` and `.F3` files in the root of a FAT32-formatted USB drive. Do not rename the files.

**Step 2: Verify USB contents**

The USB root should contain exactly:
```
Z790EAGLEAX.F6
Z790EAGLEAX.F3
```

(Exact filenames may vary — Gigabyte's naming convention is `<BOARDNAME>.<VERSION>`.)

**Step 3: Commit nothing — this task has no repo changes**

---

### Task 2: Backup F3 Settings & Flash to F6

> **This is a manual operation — requires physical access to gpu-1.**

```yaml
# manual-operation
id: gpu1-bios-f3-to-f6
phase: 4
app: gpu-operator
plan: docs/plans/2026-03-09-gpu1-pcie-link-speed-fix.md
when: "After Task 1 — USB drive prepared with F6 and F3 BIOS files"
why_manual: "BIOS update requires physical access to the machine and Q-Flash interaction — cannot be done remotely or declaratively"
commands:
  - "Power on gpu-1, press DEL during POST to enter BIOS setup"
  - "Save & Exit → Save Profiles → export to USB as z790-eagle-f3-backup.cmo"
  - "Press F8 to launch Q-Flash, select Z790EAGLEAX.F6 from USB, confirm flash"
  - "Wait for board to reboot automatically, re-enter BIOS setup (DEL on POST)"
  - "Verify BIOS version shows F6 in the top-right corner of the BIOS screen"
  - "Save & Exit → Save Profiles → export to USB as z790-eagle-f6-defaults.cmo"
  - "⚠️  Settings → Miscellaneous → Secure Boot → confirm DISABLED (F6 enables it by default)"
verify:
  - "BIOS version shown as F6 in BIOS setup header"
  - "Secure Boot shows Disabled"
status: pending
```

**Rollback if F6 flash fails or node won't boot:**
```
Q-Flash → select Z790EAGLEAX.F3 → flash
Load profile z790-eagle-f3-backup.cmo from USB
```

---

### Task 3: Force PCIe Gen 4

> **This is a manual operation — performed immediately after Task 2, still in BIOS setup.**

```yaml
# manual-operation
id: gpu1-pcie-gen4
phase: 4
app: gpu-operator
plan: docs/plans/2026-03-09-gpu1-pcie-link-speed-fix.md
when: "After Task 2 — BIOS F6 confirmed, Secure Boot confirmed disabled"
why_manual: "PCIe slot speed is a BIOS setting — no Talos patch or kernel parameter equivalent exists for this board/driver combination"
commands:
  - "Settings → IO Ports → PEG/PCIe Slot Configuration"
  - "Set the x16 slot from Auto → Gen 4"
  - "Press F10 to save and exit"
  - "Allow gpu-1 to boot into Talos"
verify:
  - "talosctl -n 192.168.55.31 dmesg | grep '0000:01:00.0' | grep 'GT/s'"
  - "Output should show 16.0 GT/s (not 2.5 GT/s)"
status: pending
```

**Rollback — undo Gen 4 setting only:**
```
Enter BIOS → Save & Exit → Load Profiles → z790-eagle-f6-defaults.cmo
```

---

### Task 4: Verify Cluster Health

**Step 1: Confirm node is Ready**

```bash
source .env
kubectl get node gpu-1
```

Expected:
```
NAME    STATUS   ROLES    AGE   VERSION
gpu-1   Ready    <none>   ...   v1.35.2
```

**Step 2: Confirm PCIe link speed**

```bash
talosctl -n 192.168.55.31 dmesg | grep "0000:01:00.0" | grep "GT/s"
```

Expected (success):
```
pci 0000:01:00.0: 256.000 Gb/s available PCIe bandwidth, limited by 16.0 GT/s PCIe x16 link
```

**Step 3: Confirm NVIDIA module loads cleanly**

```bash
talosctl -n 192.168.55.31 dmesg | grep NVRM
```

Expected:
```
NVRM: loading NVIDIA UNIX Open Kernel Module for x86_64  570.211.01
```

**Step 4: Confirm DRI devices present**

```bash
talosctl -n 192.168.55.31 ls /dev/dri
```

Expected:
```
card0
renderD128
```

**Step 5: Confirm GPU detected by operator**

```bash
kubectl get node gpu-1 --show-labels | tr ',' '\n' | grep "nvidia.com/gpu.present"
```

Expected:
```
nvidia.com/gpu.present=true
```

**Step 6: If still Gen 1 after all steps**

The upstream driver bug is triggering even with Gen 4 forced at BIOS level.
Open a follow-up task to track https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1010
and revisit when a fixed driver lands in the Talos extension registry.

---

### Task 5: Sync Runbook

**Step 1: Run sync-runbook to register the two manual operations**

```bash
/sync-runbook
```

This adds `gpu1-bios-f3-to-f6` and `gpu1-pcie-gen4` to `docs/runbooks/manual-operations.yaml`.

**Step 2: Update manual operation statuses to `done` in this plan**

Edit `docs/plans/2026-03-09-gpu1-pcie-link-speed-fix.md`:
- Change `status: pending` → `status: done` on both manual-operation blocks

**Step 3: Commit**

```bash
git add docs/plans/2026-03-09-gpu1-pcie-link-speed-fix.md
git add docs/runbooks/manual-operations.yaml
git commit -m "ops(gpu1): flash BIOS F6 and force PCIe Gen 4 — link speed 2.5→16 GT/s"
```

---

## Future Work

Once NVIDIA closes issue #1010 with a confirmed fix and that driver appears in the Talos
`nvidia-open-gpu-kernel-modules-production` extension registry:

1. Update extension pin in `patches/phase04-gpu/402-gpu1-nvidia-extensions.yaml`
2. Change PCIe setting back to **Auto** in BIOS to allow Gen 5 training
3. Verify `32.0 GT/s` in dmesg
