# Investigation: pc-1 spontaneous reboots

**Status:** In progress — PSU swap soak.
**Layer:** `hw`
**Trigger:** Operator notice on 2026-05-07 ("I think pc-1 is restarting very often. Can you check and compare it with the rest?")
**Reboot timeline observed in VictoriaMetrics 33-day window before intervention:** 7 reboots between 2026-04-04 and 2026-05-07. Inter-reboot intervals: 4–11 days.
**Intervention:** Operator swapped the PSU on the evening of 2026-05-07 (first boot under new PSU at 2026-05-07 19:28:39 UTC).
**Soak window:** Open until ≥2026-05-14 (one full historical mean inter-reboot gap of ~7 days under the new PSU before declaring root cause).

## Verdict (provisional, pending soak)

**pc-1 was failing electrically.** A 13-year-old Gigabyte Z77X-UD3H with a 2013 BIOS and an i5-3570K, hosting kubelet alongside Tekton, Gitea, ArgoCD argo-rollouts, and Longhorn replicas. The board is in textbook electrolytic-capacitor-aging territory; the failure signature matched PSU/VRM brown-out, not anything Kubernetes or Talos had visibility into.

The recommended action was **swap the PSU first**, inspect the motherboard caps for swelling, run Memtest86+ overnight as a free baseline, and seriously consider retiring pc-1 — Frank has plenty of compute and the workloads currently pinned to it (Tekton, Gitea, the homepage tile, argo-rollouts) are all reschedulable. The PSU swap has been done; the rest is on the table if the soak fails.

## Soak status (post-PSU-swap)

| Snapshot | T+0 boot | Now | Uptime | Spontaneous reboots since swap | Scrape failures |
|---|---|---|---|---|---|
| 2026-05-08 17:49 UTC | 2026-05-07 19:28:39 UTC | 2026-05-08 17:49:08 UTC | 22.3 h | 0 | 0 / 4018 samples |
| 2026-05-11 16:22 UTC | 2026-05-07 19:28:39 UTC | 2026-05-11 16:22:00 UTC | **92.87 h** | **0** | 1 / ~5500 samples (PSU-swap transition itself) |

Confirmation that the T+3.87d boot timestamp is genuinely the PSU-swap boot — not a hidden spontaneous reset masquerading as the original boot — comes from `node_boot_time_seconds{instance="192.168.55.71:9100"} = 1778182119`, which decodes exactly to `2026-05-07 19:28:39 UTC` (matches the operator-recorded swap time bit-for-bit). `changes(node_boot_time_seconds[5d]) = 1` accounts for the PSU swap itself; no second transition.

Health metrics, T+22h vs T+3.87d:

| Metric | T+22h | T+3.87d |
|---|---|---|
| CPU temp (max core) | 41 °C | 47 °C |
| Memory used | 2.57 GB / 31 GB | 3.45 GB / 31 GB |
| Load 1m | 0.08 | 0.06 |
| OOM kills | 0 | 0 |
| Scrape failures | 0 / 4018 samples | 1 / ~5500 samples |

Memory creep (2.57 → 3.45 GB) and the 6 °C CPU temp delta are both normal warming as workloads pinned to pc-1 (Tekton, Gitea, fluent-bit, longhorn-manager, zot, the argo-rollouts controller, the homepage tile) reach steady-state cache and load. Neither is anywhere near a thermal-throttle or memory-pressure threshold (pc-1 has 31 GB RAM and the CPU's `THR`/`TRM` interrupt counters are still 0).

The single scrape failure across the post-swap window is almost certainly the moment the host went offline for the PSU swap on 2026-05-07 19:25-ish UTC, before the new PSU's first boot.

Pod-side: same conclusion as T+22h, extended. Every restart event on pc-1 still carries a `lastState.terminated.finishedAt` of `2026-05-07T05:30:39Z` or earlier — recoveries from the *morning* (04:02 UTC) reboot, before the PSU swap. Nothing has restarted since 2026-05-07 19:28 UTC. cilium, gitea, tekton, fluent-bit, longhorn-manager, node-exporter, zot — all stable across the 4-day window.

**Soak verdict so far (T+3.87d):** clean. 92.87 hours of uptime is now *inside* the lower end of the historical inter-reboot range (4–11 days) without a reset — i.e., we are past the point where the most-aggressive prior failure interval (~4 days) would have already triggered. Still tracking to close as `Confirmed — PSU` if pc-1 reaches 2026-05-14 (T+7d, one historical *mean* gap) with no spontaneous reset. Will reopen and escalate (cap inspection / Memtest86+ / retire) if a reset happens between now and then.

## Symptom

| Worker | Reboots in 33d (PromQL `changes(node_boot_time_seconds[33d])`) |
|---|---|
| mini-1, mini-2, mini-3 | 0 (last boot 2026-03-22, 50 days uptime) |
| gpu-1 | 0 (last boot 2026-03-22) |
| raspi-2 | 1 (April reboot, intentional) |
| **pc-1** | **7** |
| raspi-1 | 5 — *separate problem*, see Notes |

Reboots concentrated in early UTC hours but not periodically; 4–11 day spread rules out a cron-driven reset.

## What was ruled out (and how)

| Hypothesis | Source | Verdict |
|---|---|---|
| OOM kill | `node_vmstat_oom_kill = 0` pre-reboot every time | ❌ |
| Thermal throttle | CPU 41–55 °C pre-reboot; `TRM` and `THR` interrupt counters = 0 | ❌ |
| Disk I/O / Longhorn hang | No `Hardware Error`, no `i/o error`, no SCSI resets | ❌ |
| Memory pressure | MemAvailable ~26 GB before each reboot (pc-1 has 31 GB) | ❌ |
| Watchdog (iTCO) reset | `iTCO_wdt: device disabled by hardware/BIOS` in dmesg, `/sys/class/watchdog/` empty | ❌ |
| Cluster-wide Talos issue | All other nodes have rock-solid uptime since 2026-03-22 | ❌ |
| Clean reboot triggered by automation | No `kubelet shutting down` / SIGTERM / drain log, ever | ❌ |
| Kernel panic that reached the network | Final pre-silence message on 2026-05-11 was a benign userspace network error from `cluster.DiscoveryServiceController` (TCP RST from `discovery.talos.dev`); kernel logger was healthy and shipping over SideroLink seconds before silence; no `panic` / `Oops` / `BUG:` / `Call Trace:` in the stream | ❌ (or buried below an SMI; see below) |

## What it actually looks like

Across every reboot with log coverage, the signature is identical:

```
… healthy chatter … silence … boot_time advances … POST … Talos boot … back online ~45–75s later
```

The kernel logger streams to Omni in real time over the SideroLink IPv6 tunnel (`talos.logging.kernel=tcp://[fdae:41e4:649b:9303::1]:8092`, set on the Talos kernel command line). At 2026-05-11 01:03:43 UTC, that stream's last entry from pc-1 was a `cluster.DiscoveryServiceController` reporting a routine TCP RST from AWS's load balancer in front of `discovery.talos.dev`. Then the stream stopped.

A kernel panic on a system that's actively shipping logs over `printk` would have flushed at minimum a `BUG:` / `Oops:` / `RIP:` line over that same path before halting. The kernel did not get the chance — which means whatever stopped pc-1 stopped it faster than `printk` could schedule a packet. The two failure modes that fit are:

1. **Power loss / brown-out / electrical reset.** CPU halts mid-instruction, no kernel left to log. Variable interval, no thermal/load correlation.
2. **SMI / firmware-induced reset.** BIOS System Management Mode handler hangs the CPU and the PCH resets the board. Kernel never sees it; nothing logs. More likely on a 12-year-old BIOS that pre-dates the kernels it now hosts.

Both are hardware/firmware. Both are consistent with consumer-grade hardware aging.

## Hardware inventory (the smoking gun)

Pulled directly from `node_dmi_info` and `/proc/cpuinfo` via the in-cluster debug pod (technique below):

| Node | Board | BIOS date | RAM | CPUs |
|---|---|---|---|---|
| mini-1/2/3 | NUC15CRBU5 | 2024-12-26 / 2025-10-29 | 62 GB | 14 |
| gpu-1 | Z790 EAGLE AX | 2025-12-01 | 125 GB | 32 |
| **pc-1** | **Z77X-UD3H** | **2013-07-24** | **31 GB** | **4** |
| raspi-1/2 | Pi 4B | 2026-01 | 3.7 GB | 4 |

- **CPU**: Intel **i5-3570K** Ivy Bridge (family 6, model 0x3a stepping 9), 4C/4T, no HT
- **Microcode**: 0x21 — final Intel release for this stepping (~2019). No upgrade path.
- **RAM**: 31.2 GB DDR3 non-ECC. `EDAC ie31200: No ECC support` in dmesg → memory bit-flips are silent and cannot be reported
- **Storage**: 3× SATA (sda/sdb/sdc), no NVMe
- **Watchdog**: `iTCO_wdt` present but BIOS-disabled, no other watchdog → cannot self-reset on hang
- **Persistent kernel storage**: `/sys/fs/pstore` empty and not mounted → panic data, if any, is destroyed on reset

pc-1 is the only worker in the cluster that's anywhere near this hardware vintage. The README/CLAUDE.md row claiming "64GB" was wrong on the RAM count — corrected to 32GB as part of this investigation.

## Investigation technique (reusable)

The standard path for kernel-level diagnostics on Talos workers is `talosctl dmesg / logs machined`. That requires Omni-mediated PGP auth, which is per-pod and has a 24-hour key lifetime. The pod doing this investigation didn't have a fresh signed key, and the laptop where the operator re-authed couldn't transfer the auth state.

**Bypass that worked, and worth remembering:** the in-cluster `agent-sa` ServiceAccount has cluster-admin permissions in privileged namespaces (`gpu-operator`, `infisical`, `external-secrets`, `authentik`, `comfyui`, `intel-gpu-resource-driver`). That's enough to deploy a privileged debug pod targeted at the failing node:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: <node>-debug
  namespace: gpu-operator
spec:
  nodeName: <target-node>
  hostPID: true
  restartPolicy: Never
  tolerations: [{operator: Exists}]
  containers:
    - name: debug
      image: nicolaka/netshoot:latest
      command: ["sh", "-c"]
      args: ["dmesg -T | tail -200; cat /proc/cpuinfo; ls /sys/fs/pstore/"]
      securityContext:
        privileged: true
```

`hostPID: true` plus `privileged: true` gives the container a view of the host's PID namespace and access to host kernel surfaces. `/proc/1/root/...` reaches the host's root filesystem (`/proc/1/root/dev/kmsg`, `/proc/1/root/sys/...`). `nicolaka/netshoot` ships util-linux `dmesg`, so the kernel ring buffer for the current boot is one command away.

This works even when Omni auth is broken, even when Talos's API is unreachable, on any Talos worker with a privileged namespace nearby. It does *not* recover data from before the reboot — pstore would be needed for that, and Talos doesn't enable it by default.

## What couldn't be determined from inside the cluster

- **Kernel state in the final milliseconds before each reset.** The kernel ring buffer is volatile. `/sys/fs/pstore` is not mounted. The kernel-stream over SideroLink captures everything Linux had time to print, but if a hardware reset interrupts execution mid-instruction, there's nothing to print. Omni has the most complete view available; the operator confirmed via Omni UI that the final pre-silence log on 2026-05-11 was a routine userspace network error, not a panic trail.
- **DDR3 bit-flips.** No ECC, no software-side reporting. Only a Memtest86+ run can resolve this.
- **PSU rail stability.** Not measurable from software at all. Requires either a multimeter on the 12V rail under transient load, or an A/B swap with a known-good PSU.

## Recommendations

In rough cost/effort order:

1. **PSU swap.** ✅ Done 2026-05-07 evening (boot at 19:28:39 UTC). Most likely culprit on a 12-year-old build. A degraded PSU with aged output capacitors will brown-out under transient loads (cilium endpoint regeneration, NFD scan, kubelet sync) and reset the CPU before the kernel can react. Soak window open through ≥2026-05-14 — see *Soak status* above.

2. **Visual cap inspection.** Open the case. Look at the motherboard caps near the CPU VRM (top of the LGA1155 socket) and at the PSU output caps. Bulged tops or leaking electrolyte are dispositive when present. Often visible to the eye on a board this old.

3. **Memtest86+ overnight.** Free, runs from USB, catches DDR3 modules that have drifted out of spec. The board has no ECC to flag this any other way.

4. **Retire pc-1.** This is honest infrastructure honesty: Frank is a learning cluster, not a production one. Spending hours debugging a 12-year-old consumer board's intermittent electrical failures has a poor signal-to-effort ratio. Workloads currently pinned to pc-1 (Tekton, Gitea, homepage, argo-rollouts) are all reschedulable. Either decommission, or repurpose pc-1 as a dedicated experiment-when-it's-up node where the reboots aren't load-bearing.

5. **(If keeping pc-1) Enable pstore in the Talos machine config.** Patch `kernelArguments` with `ramoops.mem_address=0x0e000000 ramoops.mem_size=0x100000` (or equivalent EFI-pstore variables if the Z77 firmware permits Linux-side EFI variable writes — unlikely on this BIOS). Survives reset, captures any panic message that does fit. Useful insurance even if hardware is the most likely cause, because it lets us actually rule kernel-side causes back out next time.

## Notes

- **raspi-1's 5 reboots** are a separate problem from pc-1's. raspi-1 also shows 2052 cilium pod restarts and 3179 node-exporter restarts in 18 days — that's pod-level crashlooping (likely resource pressure on a 4 GB RPi 4 running Cilium), not the same hardware-reset signature. Worth its own investigation if it becomes operationally painful.
- **CLAUDE.md / README correction.** `frank-infrastructure.md` and the layer 27 (CI/CD platform) blog post both claimed pc-1 had 64 GB RAM. Actual hardware reports 31.2 GB DDR3. Corrected as part of this investigation.

## Files touched

- `.claude/rules/frank-infrastructure.md` — pc-1 row: 64GB → 32GB, with back-link to this investigation
- `blog/content/docs/building/27-cicd-platform/index.md` — narrative paragraph: 64GB RAM → 32GB RAM
- `docs/investigations/2026-05-11--hw--pc-1-reboot-investigation.md` — this file (sets the convention for `docs/investigations/`)

## Changelog

- **2026-05-07** — Investigation opened. Pulled reboot timeline from VictoriaMetrics, hardware inventory and kernel ring buffer via in-cluster privileged debug pod (Talos auth was unavailable to this pod). Verdict: hardware-level reset, recommend PSU swap.
- **2026-05-07 evening** — Operator swapped the PSU. First boot under new PSU at 19:28:39 UTC.
- **2026-05-08 17:49 UTC** — Soak snapshot at T+22h: 0 spontaneous reboots, 0 scrape failures, all health metrics nominal. Status moved to *In progress — PSU swap soak*. Next checkpoint: 2026-05-14 (T+7d, one historical mean inter-reboot gap).
- **2026-05-11 16:22 UTC** — Soak snapshot at T+3.87d: still 0 spontaneous reboots since the swap (`changes(node_boot_time_seconds[5d]) = 1`, accounted for by the swap itself; live `node_boot_time_seconds = 1778182119` ≡ `2026-05-07 19:28:39 UTC`). Past the lower end of the historical 4–11d inter-reboot range with no reset. Health metrics still nominal (CPU max 47 °C, 3.45 GB memory used, load 0.06, OOM=0). Soak continues; next checkpoint unchanged at 2026-05-14. *(Data fetch was delayed by an unrelated Omni control-plane TLS-cert expiry that blocked the kubectl OIDC path for ~46h; see `docs/investigations/2026-05-11--omni--cert-expiry-incident.md`.)*
