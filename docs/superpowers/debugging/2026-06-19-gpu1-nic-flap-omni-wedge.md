# Debugging log — gpu-1 NIC flap "fix won't apply" → wedged Omni control plane

**Date:** 2026-06-19
**Layer:** gpu (gpu-1 hardware) + Omni control plane
**Trigger:** "there are a lot of grafana notifications. What's going on?"
**Outcome:** PR #582 (KernelArgs mechanism fix) + `docker restart omni` (out-of-band recovery). NIC-flap storm resolved.

## Symptom & reproduction

- A flood of Grafana → Telegram notifications.
- Surface cause found fast: gpu-1's `enp3s0` (Realtek r8169) NIC was link-flapping every 1–2 min (`talosctl -n 192.168.55.31 dmesg | grep 'Link is'` showed continuous Down/Up; 138 carrier-change lines), collapsing the Cilium datapath and re-firing `layer-1-nic-link-flap` plus cascading Layer-5/8 alerts.
- The chronic flap had a *merged* durable fix (`#515`, 2026-06-09: `pcie_aspm=off`) that had **never taken effect** — `/proc/cmdline` lacked the arg months later.

## Evidence (the data-flow trace)

1. `pcie_aspm=off` was declared via a `ConfigPatches` resource (`machine.install.extraKernelArgs`). After `omnictl apply`, Omni merged it into the *desired* machine config — but `configapplystatus: 2`, `configuptodate: true`, and the **schematic id never changed**; no reinstall, no reboot.
2. The machines boot a **UKI** (`grubUseUKICmdline: true`) → kernel cmdline is baked into the signed image; only the installer rewrites it. `machine.install.extraKernelArgs` doesn't change the schematic id, so Omni never reinstalls. **Wrong mechanism.**
3. The right mechanism exists: `KernelArgs.omni.sidero.dev` (introduced Omni v1.3.0; the kernel-arg analogue of the `ExtensionsConfigurations` that *did* install gpu-1's nvidia extensions). Replaced the ConfigPatch with a `KernelArgs` resource → Omni **recomputed the schematic** (`bc199057…` → `fd54cfc7…`, desired kernelargs now include `pcie_aspm=off`).
4. **But the machine still never upgraded.** `kernelargsstatus.CURRENT ARGS` stayed `[]`; gpu-1 never rebooted. Same shape as the ConfigPatch: desired-state set, nothing applied.
5. Auth dead-ends while trying to force it: `talosctl upgrade` → `PermissionDenied` for the reader config **and** a freshly-minted Omni-Admin config (Omni's proxy reserves Upgrade for itself); `omnictl talosconfig --break-glass` → `not allowed` (disabled for the devops SA). So no direct path existed either.
6. Pivoted to Omni server logs (`ssh frank-omni`, `docker logs omni`): **frozen.** `wc -l` static (1,591,650 lines, delta 0 over 5s); newest log line timestamped **~61 days old** — *older than the container's own `StartedAt`*. Host clock fine now (NTP-synced); disk 2% used; process up, ~0 CPU, not OOM-killed.

## Root cause

Two stacked causes, both required to explain "the fix never applied":

1. **Wrong mechanism (repo bug):** `#515` used a `ConfigPatches` `machine.install.extraKernelArgs` for a kernel arg on an Omni-managed UKI machine. That never changes the schematic id, so Omni never reinstalls — the arg was inert. Fixed by `#582` (KernelArgs resource).
2. **Wedged Omni control plane (operational):** the on-prem `omni` container's reconcile runtime had **silently deadlocked** since a power-outage cold boot ~10 days prior. The Pi has no RTC → booted with a stale clock → NTP later jumped time forward by weeks → etcd/raft + Go timers wedged. Omni kept serving cached reads (UI/omnictl green, `configuptodate: true`) while reconciling **nothing**. So even the *correct* KernelArgs resource queued against a dead runtime.

"X because Y": *gpu-1's kernel arg never applied because (a) it was declared via a mechanism Omni doesn't reinstall for, and (b) Omni's reconcile runtime was dead and applied nothing at all.*

## Fix

- **Repo:** `patches/phase04-gpu/403-gpu1-pcie-aspm.yaml` → `KernelArgs.omni.sidero.dev` resource (PR #582).
- **Operational:** `docker restart omni` on the Omni host. With the clock NTP-synced, the runtime re-initialised and reconciled the backlog — `kernelargsstatus.CURRENT ARGS` flipped to `["pcie_aspm=off"]`, gpu-1 reinstalled + rebooted, and `dmesg` confirmed `pcie_aspm=off` in the live `Kernel command line:`.

### Verification

- `talosctl -n 192.168.55.31 dmesg | grep pcie_aspm=off` → present (live).
- Flap rate: ~every 1–2 min → **~1 flap in 6h** (storm gone; below the `>6/30m` alert threshold). **Suppressed, not 100% cured** — ASPM-off addresses the L1-wake mechanism but the r8169 isn't perfectly stable. Escalation ladder (cable/switch port → 1G cap → NIC replace) remains if isolated blips recur.

## Rejected hypotheses

- **Break-glass taint blocks upgrades.** Plausible (Frank tainted for months) and reframed the taint from cosmetic to possibly-functional mid-investigation — but the UI was all green with no taint banner, and the real blocker was the wedged runtime. Taint was a red herring for *this* problem.
- **Omni v1.5.0 lacks KernelArgs support.** No — the feature shipped in v1.3.0; v1.5.0 has it. (It does lack a *UI surface* in v1.5.0, which misled the "I can't find it in the GUI" check.)
- **NIC flap blocking the installer image pull.** Considered as one of three causes for "won't upgrade"; ruled out by the frozen `docker logs` pointing at a dead runtime, not a pull error.
- **`docker logs` proves Omni is dead/alive.** Unreliable here — it stayed frozen even after the restart revived the runtime (a json-file attach quirk). The trustworthy signal was **functional**: `kernelargsstatus.CURRENT ARGS` flipping.
- **A plain reboot (Omni UI) would apply the arg.** No — UKI cmdline is fixed until the installer reruns; a plain reboot returns on the old image. Only an Omni-driven schematic reinstall applies it.

## Durable follow-up (not in this repo)

Gate the `omni` container start on `time-sync.target` / `fake-hwclock` (and ideally add a hardware RTC to the Pi) so a power-cut cold boot can't operate with a stale clock and re-wedge the runtime. The repo `omni/` dir is a copy — this must be applied on the live host. Full prose: `docs/runbooks/frank-gotchas/omni.md`.
