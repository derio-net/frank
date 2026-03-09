# Design: RTX 5070 PCIe Link Speed Fix (gpu-1)

## Background

After reseating the RTX 5070 in `gpu-1`, the card was detected on the PCIe bus but the link
is negotiating at PCIe Gen 1 (2.5 GT/s) instead of the expected Gen 5 (32 GT/s):

```
pci 0000:01:00.0: 32.000 Gb/s available PCIe bandwidth, limited by 2.5 GT/s PCIe x16 link
```

## Root Cause

Two contributing factors were investigated:

**1. NVIDIA open kernel module bug (primary cause)**
The NVIDIA open kernel modules (confirmed across 570.x, 580.x, 590.x) attempt Gen 5 link
training on Blackwell GPUs. Gen 5 equalization fails, and the driver falls back all the way to
Gen 1 instead of the highest stable speed (Gen 4). This is a confirmed upstream bug tracked at
[NVIDIA/open-gpu-kernel-modules#1010](https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1010),
open as of 2026-03-05 with no fix confirmed.

**2. BIOS outdated (contributing factor)**
`gpu-1` runs BIOS F3 (2024-09-27), which predates the RTX 50-series launch (January 2025).
Gigabyte has released F4, F5, and F6 since then. No changelog entry explicitly addresses PCIe
Gen 5 / Blackwell link speed, but F6 is the current stable release and should be applied.

**Driver upgrade path unavailable:** The latest Talos
`nvidia-open-gpu-kernel-modules-production` extension is still `570.211.01` — the same version
currently running. No fixed driver version exists in the extension registry.

**Windows reference:** On Windows with driver 581.80, the same hardware runs at Gen 4 (16 GT/s),
not Gen 5. Gen 4 is the realistic target on Linux until the upstream bug is fixed.

## Approach

**Approach B — BIOS update + force Gen 4 in BIOS settings.**

By capping the PCIe slot at Gen 4 from within BIOS, the link trains at Gen 4 before the OS
loads. The NVIDIA driver finds a stable Gen 4 link already established and accepts it — the
broken Gen 5 training path is never triggered.

Expected improvement: 2.5 GT/s → 16 GT/s (6.4× bandwidth increase).

Approaches considered and ruled out:
- **BIOS update only (Approach A):** No changelog evidence it fixes the speed; driver bug
  persists regardless.
- **Driver/extension upgrade (Approach C):** No fixed driver available in Talos extension
  registry; upstream bug unresolved.

## Cluster Impact

`gpu-1` is a worker node with a `NoSchedule` taint (GPU workloads only). Taking it offline
for a BIOS update has zero impact on cluster availability or non-GPU workloads.

## Section 1 — Backup & BIOS Update (F3 → F6)

1. Boot into BIOS setup (DEL on POST) while still on F3
2. **Save & Exit → Save Profiles** → export current settings to USB as `z790-eagle-f3-backup.cmo`
3. Use **Q-Flash** (F8 from within BIOS) to flash the F6 BIOS file from USB
4. Board reboots automatically; re-enter BIOS setup and verify version shows F6
5. Save the F6 defaults as a clean baseline: `z790-eagle-f6-defaults.cmo`
6. ⚠️ **Check Secure Boot:** F6 enables Secure Boot by default — Talos does not use Secure Boot
   and the node will fail to boot if it is left on. Navigate to
   **Settings → Miscellaneous → Secure Boot** and confirm it is **Disabled**.

**Rollback — BIOS flash:** Re-flash F3 via Q-Flash using the F3 file (pre-download to USB
before starting), then load `z790-eagle-f3-backup.cmo` to restore all previous settings.

## Section 2 — Force PCIe Gen 4 in BIOS Settings

1. Navigate to **Settings → IO Ports → PEG/PCIe Slot Configuration**
2. Change the x16 slot from **Auto** → **Gen 4**
3. Save and exit (F10)

**Rollback — Gen 4 setting only:** Load `z790-eagle-f6-defaults.cmo` to revert to F6 defaults
with PCIe back on Auto.

## Section 3 — Verification

After `gpu-1` boots back into Talos:

```bash
# Confirm node is Ready
kubectl get node gpu-1

# Check PCIe link speed — should now show 16 GT/s instead of 2.5 GT/s
talosctl -n 192.168.55.31 dmesg | grep "0000:01:00.0" | grep "GT/s"

# Confirm NVIDIA kernel module still loads cleanly
talosctl -n 192.168.55.31 dmesg | grep NVRM

# Confirm DRI devices still present
talosctl -n 192.168.55.31 ls /dev/dri

# Confirm GPU still detected by the operator
kubectl get node gpu-1 --show-labels | tr ',' '\n' | grep "nvidia.com/gpu.present"
```

**Success criteria:**
- Node returns to Ready
- dmesg shows `16.0 GT/s` on `0000:01:00.0`
- NVRM module loads without error
- `card0` and `renderD128` present
- `nvidia.com/gpu.present=true` still set

**If the link is still Gen 1 after all this:** The driver bug is hitting even with Gen 4 forced
at BIOS level. Open a follow-up task to track
[NVIDIA/open-gpu-kernel-modules#1010](https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1010)
and revisit when a fixed driver lands in the Talos extension registry.

## Future Work

Once NVIDIA closes issue #1010 with a confirmed fix, and that driver version is available in
the Talos `nvidia-open-gpu-kernel-modules-production` extension registry:
1. Update the extension pin in `patches/phase04-gpu/402-gpu1-nvidia-extensions.yaml`
2. Change PCIe setting back to **Auto** in BIOS to allow Gen 5 training
3. Verify `32.0 GT/s` in dmesg
