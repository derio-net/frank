# OpenRGB IT5701 On-Demand Control Investigation

**Date:** 2026-03-09 (updated 2026-03-10)
**Status:** Closed — root cause confirmed, requires USB traffic capture on Windows to fix
**Outcome:** IT5701 V3.5.14.0 has a firmware write lock set by BIOS; unlock sequence unknown

---

## The Problem

Phase 6 established a Kubernetes DaemonSet that controls the ARGB LEDs on gpu-1 by running
OpenRGB against the onboard IT5701-GIGABYTE USB HID controller. The original design used two
containers: an init container to apply the LED config and a `--server` main container as
keepalive.

After a hardware maintenance session (reseating the RTX 5070, CMOS reset, BIOS update F3→F6,
several reboots), the LEDs started showing random colors — green, then blue, then lila — on
every boot instead of the configured black.

---

## Investigation Phase 1 — The Two-Container Regression

**Hypothesis:** The `--server` container is interfering with the init container.

The IT5701 controller saves its last color to non-volatile memory. When OpenRGB starts a
server, it runs a device initialization sequence that restores the controller's saved NV state
— overwriting whatever the init container just applied. Because multiple OpenRGB invocations
had touched the device in different sequences during the hardware session, the NV state was
non-deterministic across reboots (different colors from different writes).

**Fix:** Replace the two-container pod with a single container running
`openrgb --noautoconnect $OPENRGB_ARGS && sleep infinity`. The `--noautoconnect` flag runs
OpenRGB in standalone mode without starting a server, so there is nothing to reinitialize the
device afterward.

**Verification:** Cold boot confirmed LEDs did not turn on (no rainbow, no color). Declared
fixed.

---

## Investigation Phase 2 — On-Demand Writes Don't Work

**Discovery:** While testing a ConfigMap color change (white, `ffffff`), the LED color did
not change — neither on pod restart nor on exec into the running pod.

This triggered a deeper investigation.

### What was tried

| Test | Result |
|------|--------|
| `openrgb --noautoconnect -d 0 -m Static -c ffffff` | Exit 0, no change |
| `openrgb --noautoconnect -d 0 -m Direct -c ffffff` | Exit 0, no change |
| `openrgb --noautoconnect -d 0 --zone 0/1/2 -m Static -c ff0000` | Exit 0, no change |
| `openrgb -d 0 -m Static -c ff0000` (no --noautoconnect) | Exit 0, no change |
| Server + auto-connect client `-d 0 -m static -c ff0000` | Exit 0, no change |
| `dd if=/dev/zero bs=64 count=1 of=/dev/hidraw2` | Success — device IS writable |
| `openrgb --noautoconnect --list-devices` | Device found at `/dev/hidraw2` |
| `openrgb --noautoconnect -vv -d 0 -m static -c ff0000` | No log output after device detection |

### Key observations

1. **Device is found:** `--list-devices` shows `Z790 EAGLE AX (IT5701-GIGABYTE V3.5.14.0)`.
2. **Raw writes work:** `dd` can write to `/dev/hidraw2` (file is accessible, no permission issue).
3. **OpenRGB exits 0:** No error signaled, but nothing happens.
4. **No log output after detection:** Verbose (`-vv`) logging covers the full device detection
   phase but produces zero output about mode or color application. The application pipeline
   after detection is either silent or not executing.
5. **Server mode also fails:** Starting OpenRGB in `--server` mode and sending SDK commands
   via a connected client also produced no LED change — the device detects and enumerates
   correctly but writes are silently dropped.

### Timing hypothesis (investigated and rejected)

Early suspicion was that the IT5701 only accepts writes during a brief hardware initialization
window after a true power-on. This was plausible given that:
- `talosctl reboot` uses kexec (kernel restarts without hardware power cycle), so the IT5701
  never resets
- The rainbow startup sequence (which signals fresh hardware init) only appears on true
  cold boots, not kexec reboots

The timing hypothesis was not confirmed: even in contexts where the write window should have
been open (shortly after pod start on a fresh kexec boot), writes failed. And the server mode
also failed, which has different timing characteristics.

---

## Root Cause — IT5701 Firmware Version Incompatibility

**Finding:** The IT5701 on this board reports firmware version `V3.5.14.0`. The only version
confirmed to work with OpenRGB 0.9 in the issue tracker is `V3.5.5.0` (from a B760 GAMING X
AX, issue #3709). Version `V3.5.14.0` is newer and likely changed the USB HID protocol in a
way OpenRGB 0.9 does not support.

The BIOS F3→F6 update is the probable trigger: Gigabyte ships embedded IT5701 firmware
updates with BIOS revisions, and the F4/F5/F6 cycle likely bumped the controller from the
`V3.5.5.x` range to `V3.5.14.0`.

This explains the verbose log behavior: OpenRGB 0.9 successfully enumerates the device (the
enumeration protocol still works), but the write commands use a protocol format the newer
firmware does not recognize, and the firmware silently discards them.

### Why the original init container worked

The original Phase 6 implementation worked on BIOS F3, where the IT5701 firmware was an
older version compatible with OpenRGB 0.9. After the BIOS update to F6, the firmware changed
and standalone writes stopped working. The "LEDs are off" state seen on subsequent cold boots
was the IT5701 replaying its NV-saved color (black, from a write that succeeded before the
firmware update), not our OpenRGB command succeeding.

---

## Fix — Build OpenRGB 1.0rc2

OpenRGB 0.9 was released July 2023. OpenRGB 1.0rc2 was released September 2025 — roughly
two years of IT5701 and Gigabyte motherboard compatibility updates. IT5701 `V3.5.14.0` is
likely supported.

**No pre-built Docker image exists for OpenRGB 1.0rc2.** `swensorm/openrgb` (the image used
by Phase 6) has not published anything beyond `release_0.9`.

### Build approach

- Source: `https://codeberg.org/OpenRGB/OpenRGB`
- Tag: `release_candidate_1.0rc2`
- Build system: qmake (unchanged from 0.9)
- Key requirement: `QT_QPA_PLATFORM=offscreen` — Qt panics without a display unless the
  offscreen platform backend is set
- Avoid `make install`: 1.0rc2 tries to write to `/etc/systemd/system` during install,
  which breaks Docker builds; copy the binary directly instead
- Binary path: `/src/OpenRGB/openrgb` (build dir)

### Files created

- `apps/openrgb/docker/Dockerfile` — multi-stage build producing a slim runtime image
- `.github/workflows/build-openrgb.yml` — builds and pushes to
  `ghcr.io/derio-net/openrgb:1.0rc2` on push to `apps/openrgb/docker/**`

### DaemonSet update (complete)

`apps/openrgb/manifests/daemonset.yaml` updated to `ghcr.io/derio-net/openrgb:1.0rc2`.
Testing confirmed the image runs correctly; on-demand writes still fail (see Phase 3).

---

## Investigation Phase 3 — OpenRGB 1.0rc2 Also Fails

**Date:** 2026-03-10

A custom Docker image was built from OpenRGB 1.0rc2 (`release_candidate_1.0rc2` tag on
Codeberg) and deployed to `ghcr.io/derio-net/openrgb:1.0rc2`. The DaemonSet was updated to
use this image.

### Build notes

- `make install` is broken in 1.0rc2 (tries to write to `/etc/systemd/system`); binary copied
  from build dir directly
- `ca-certificates` required in the builder stage (Codeberg uses TLS; the base image
  `debian:bookworm-slim` ships without CA certs)
- `QT_QPA_PLATFORM=offscreen` required — Qt panics without a display backend
- GHCR packages default private even on public repos; had to manually set package visibility
  to Public before the pod could pull the image

### 1.0rc2 behavior

| Test | Result |
|------|--------|
| `--list-devices` | Device found: `Z790 EAGLE AX`, firmware `V3.5.14.0`, Zones: D_LED1 D_LED2 |
| Modes | `[Direct] Static Breathing Flashing 'Color Cycle' 'Double Flash' Wave Random 'Wave 1/2/3/4'` |
| `-d 0 -m Static -c ff0000` | Exit 0, LEDs unchanged |
| `-d 0 -m Direct -c ff0000` | Exit 0, LEDs unchanged |
| `-d 0 --zone 0 -m Static -c ff0000` | Exit 0, LEDs unchanged |
| USB device reset + immediate write | LEDs unchanged |
| `-vv` verbose log | Shows `[CLI] using device number 0 for argument 0` then immediately `OpenRGB finishing with exit code 0` — no mode/color write output |

### Key observations

1. **1.0rc2 detects the device differently from 0.9**: 0.9 showed 3 zones
   (D_LED1 Bottom, D_LED2 Top, Motherboard) and 8 LEDs total. 1.0rc2 shows only 2 zones
   (D_LED1, D_LED2) with no LED count in the `--list-devices` output.
2. **No LED count reported**: If the LED count query returned 0 for both ARGB strip zones,
   `SetStripColors()` would loop over 0 LEDs and write nothing. This would explain exit 0
   with no effect.
3. **Verbose log ends immediately after device selection**: After `[CLI] using device number 0
   for argument 0`, the program exits with no write-phase output. The IT5701 driver may not
   log write operations, or the write phase is being skipped.

### Protocol analysis (IT5701 source code review)

After reviewing the OpenRGB 1.0rc2 Gigabyte RGB Fusion 2 USB controller source:

- All HID communication uses **feature reports** (`ioctl(HIDIOCSFEATURE)`), not interrupt
  OUT reports. Plain `write()` to hidraw sends interrupt OUT reports, which the IT5701 rejects
  with I/O error. The earlier `dd if=/dev/zero` "success" was a no-op write to the wrong
  endpoint.
- A **commit packet** (`[0xCC, 0x28, ...]`) is mandatory — without it, no color change
  appears. OpenRGB's `ApplyEffect()` is supposed to send this automatically.
- **Critical finding**: The IT5701 (PID `0x5702`) and IT5711 (PID `0x5711`) take completely
  separate code paths. OpenRGB 1.0rc2 added significant new features for the IT5711
  (calibration data, 4 DLED headers, Wave/Double Flash modes, LampArray disable). The IT5701
  code path received far less attention. If V3.5.14.0 introduced a protocol change that only
  the IT5711 path accounts for, IT5701 writes would continue to fail.

### Current hypothesis

The Z790 Eagle AX's IT5701 (PID `0x5702`) with firmware `V3.5.14.0` is not correctly
supported in OpenRGB 1.0rc2. The IT5711 (PID `0x5711`) path likely got the V3.5.x
compatibility fixes; the IT5701 path did not. Writes enumerate and parse correctly but the
actual HID feature report sequence is either wrong or missing a required step for this
firmware version.

---

## Current State

- DaemonSet runs `ghcr.io/derio-net/openrgb:1.0rc2` with `--noautoconnect -d 0 -m Static -c 000000`
- LED state: black (off) — replaying the NV-saved color from before the BIOS update
- On-demand color changes: not working with any tested OpenRGB version or invocation method
- The single-container design (no server) remains correct to prevent NV state corruption

---

## Open Questions

1. Does IT5701 PID `0x5702` with V3.5.14.0 work with any OpenRGB version beyond 1.0rc2?
2. Is this a known issue in the OpenRGB tracker? (not confirmed — no issue found for PID 5702
   + V3.5.14.0 specifically)
3. Does the LED count query return 0 for the ARGB zones on V3.5.14.0? If so, this is a
   discrete bug separate from the general protocol incompatibility.

## Paths Forward

| Option | Notes |
|--------|-------|
| Wait for upstream OpenRGB fix | Passive — file a bug with firmware version + PID, wait for support |
| BIOS downgrade to F3 | Restores compatible firmware; loses BIOS security/stability updates |
| Raw HID protocol reverse engineering | Capture Windows RGB Fusion traffic, implement correct V3.5.14.0 packets directly |
| Accept NV replay state | LEDs stay black (off) — the NV state set before the BIOS update persists correctly |

### Direct HID protocol investigation (definitive)

**Date:** 2026-03-10

With OpenRGB exhausted, a Python probe pod was run with `ioctl(HIDIOCSFEATURE)` to
send raw HID feature reports directly — bypassing OpenRGB entirely.

**Key findings:**

1. **Correct ioctl confirmed**: `HIDIOCSFEATURE = 0xC0404806`
   (`_IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, 64)` — direction is 3, not 1).
   Using 0x40404806 caused `EINVAL`; 0xC0404806 worked.

2. **Device info readback** (`[0xCC, 0x60]` → `HIDIOCGFEATURE`):
   `cc 01 00 07 03 05 0e 00 00 00 00 01 49 54 35 37 ...`
   Bytes 4–7 = `03 05 0E 00` = firmware V3.5.14.0.
   `support_cmd_flag` (byte 6) = `0x0E` — OpenRGB's `>= 0x02` check passes,
   so `EnableLampArray(false)` IS called during OpenRGB init. LampArray is not
   the cause.

3. **Write storage confirmed**: After writing Static red to register `0x20`,
   the readback showed `effect_type = 0x01` (Static) and `color BGR = 00 00 FF`
   (red). The device stores the write correctly.

4. **All commit variants tried, all fail:**
   - `[0xCC, 0x28, 0xFF, 0x00]` — IT5701 fast apply
   - `[0xCC, 0x28, 0xFF, 0x07]` — IT5711 fast apply
   - zone 0 only, all zones full, all bits set
   — none produced any physical LED change.

5. **Rapid-fire loop (245 cycles in 3 seconds) — zero effect**: Sending
   `SetStripBuiltinEffectState(0xFF)` + Static red on all zone registers +
   both apply variants, 245 times in 3 seconds, produced not a single flicker.

6. **No host process writing to the device**: `lsof`/`/proc` scan confirmed no
   process has `/dev/hidraw2` open between our writes. The rainbow is driven
   entirely by the IT5701's own autonomous firmware.

**Definitive conclusion**: The IT5701 V3.5.14.0 firmware enters a **write-locked
state** set by the BIOS on cold boot. It accepts all HID feature reports without
error and stores them in registers, but the physical LED output never changes.
The unlock sequence required to exit this locked state is unknown — it exists
only in Gigabyte's Windows RGB Fusion binary and has not been reverse-engineered
or documented anywhere publicly.

### Talos udev rules (tried, did not fix)

Added `machine.udev.rules` to the gpu-1 Talos machine config via
`patches/phase04-gpu/05-gpu1-openrgb-udev.yaml` (Omni config patch
`305-gpu1-openrgb-udev`). Rule content:

```
SUBSYSTEMS=="usb|hidraw", ATTRS{idVendor}=="048d", ATTRS{idProduct}=="5702", TAG+="uaccess", TAG+="Gigabyte_RGB_Fusion_2_USB"
```

Result: no change. The `TAG+="uaccess"` rule affects user-space device access via
systemd-logind; it has no effect on a privileged root container. The write protocol
issue is unrelated to udev permissions. Patch left in place as it is correct hygiene
for future non-root scenarios and matches OpenRGB's standard setup.

---

## Timeline

| Time | Event |
|------|-------|
| Phase 6 setup | Two-container DaemonSet deployed, LEDs off (working, BIOS F3) |
| Hardware session | GPU reseated, CMOS reset, BIOS F3→F6, multiple reboots |
| Post-hardware | LEDs showing green/blue/lila on each boot (regression) |
| Investigation | Root cause: `--server` container restoring NV state |
| Fix attempt 1 | Single container, `--noautoconnect`, `sleep 30` |
| Verification | Cold boot: LEDs off — attributed to fix, actually NV replay of black |
| On-demand test | ConfigMap changed to `ffffff`, pod restarted — no change |
| Deep debug | All write approaches fail; verbose log shows no post-detection activity |
| Root cause | IT5701 firmware `V3.5.14.0` incompatible with OpenRGB 0.9 protocol |
| Fix staged | OpenRGB 1.0rc2 Dockerfile + GitHub Actions build pipeline created |
| GHCR build | Image `ghcr.io/derio-net/openrgb:1.0rc2` built and pushed; package set public |
| 1.0rc2 testing | DaemonSet updated; writes still fail — USB reset, zone targeting, all modes |
| Protocol analysis | Source reviewed: IT5701 PID 5702 + V3.5.14.0 not fixed in 1.0rc2 |
| Status | Blocked — awaiting upstream OpenRGB fix or manual protocol reverse engineering |
