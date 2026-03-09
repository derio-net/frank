# OpenRGB IT5701 On-Demand Control Investigation

**Date:** 2026-03-09
**Status:** In progress — OpenRGB 1.0rc2 image build pending
**Outcome:** Root cause identified; fix staged for testing

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

### DaemonSet update (pending image build)

After the image is built and available at `ghcr.io/derio-net/openrgb:1.0rc2`, update
`apps/openrgb/manifests/daemonset.yaml`:

```yaml
image: ghcr.io/derio-net/openrgb:1.0rc2
```

Then retest on-demand color writes.

---

## Open Questions

1. Does OpenRGB 1.0rc2 actually fix IT5701 `V3.5.14.0` writes? (unconfirmed — testing
   pending image build)
2. If 1.0rc2 writes work, do they persist to NV memory, or only change the current display
   state? (affects cold boot behavior)
3. The correct value for `sleep` before the OpenRGB command: `sleep 5` targets the cold boot
   hardware initialization window; `sleep 30` was added to wait for the hardware rainbow but
   overshoots the window. If 1.0rc2 writes work at any time (no window constraint), the sleep
   value matters less.

---

## Timeline

| Time | Event |
|------|-------|
| Phase 6 setup | Two-container DaemonSet deployed, LEDs off (working) |
| Hardware session | GPU reseated, CMOS reset, BIOS F3→F6, multiple reboots |
| Post-hardware | LEDs showing green/blue/lila on each boot (regression) |
| Investigation | Root cause: `--server` container restoring NV state |
| Fix attempt 1 | Single container, `--noautoconnect`, `sleep 30` |
| Verification | Cold boot: LEDs off — attributed to fix, actually NV replay |
| On-demand test | ConfigMap changed to `ffffff`, pod restarted — no change |
| Deep debug | All write approaches fail; verbose log shows no post-detection activity |
| Root cause | IT5701 firmware `V3.5.14.0` incompatible with OpenRGB 0.9 protocol |
| Fix staged | OpenRGB 1.0rc2 Dockerfile + GitHub Actions build pipeline created |
