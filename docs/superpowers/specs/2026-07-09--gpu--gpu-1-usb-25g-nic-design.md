# gpu-1 USB 2.5G NIC Replacement Design

**Date:** 2026-07-09  
**Layer:** gpu  
**Status:** Design update  
**Context:** gpu-1's onboard Realtek `enp3s0` NIC was damaged or left marginal by the recent power outage. `pcie_aspm=off` suppressed the flap storm but did not cure the hardware. The PCIe I22X-LAN card did not fix the issue, so the next replacement path is a USB 2.5G Ethernet adapter.

## Problem

gpu-1 is Frank's only NVIDIA GPU node and hosts GPU workloads plus several hard-pinned agent shells. Its onboard Realtek 2.5GbE NIC (`enp3s0`, r8169) has already proven it can flap hard enough to strip `192.168.55.31/24` from the node interface, collapse Cilium's direct-routing datapath, and drop every LoadBalancer-backed SSH session into gpu-1 pods at once.

PR #515 first prepared `pcie_aspm=off`; PR #582 corrected the Omni mechanism to `KernelArgs.omni.sidero.dev`. That moved the incident from a storm to rare blips, which is a mitigation, not a repair. The attempted PCIe I22X-LAN replacement did not resolve the hardware path. The durable fix is still to stop relying on the damaged onboard NIC, but the replacement device is now the incoming USB 2.5G adapter.

## Decision

Install the USB 2.5G Ethernet adapter in gpu-1 and move the existing node address, `192.168.55.31/24`, to that adapter.

The Talos config should bind by the new adapter's MAC address, not by the observed Linux interface name. USB NIC interface names can shift across ports, hubs, and boot ordering; the MAC is the stable identifier. The onboard Realtek NIC should remain unplugged after the migration rather than used as fallback, because a damaged fallback still creates noise and ambiguity.

## Scope

In scope:

- Replace the I22X-LAN repo-prep artifacts with a USB 2.5G adapter Omni ConfigPatch template.
- Update gpu-1 runbooks and gotchas so future operators know the PCIe card was not the final fix.
- Preserve `pcie_aspm=off` for now; it is harmless insurance for the broader PCIe platform until the replacement has soaked.
- Define an operator-driven maintenance-window Test Plan for the USB adapter once it arrives.

Out of scope:

- Guessing the USB adapter MAC address before it is installed.
- Assuming Talos has the driver before checking the live link list and kernel logs.
- Using the damaged Realtek NIC as a failover path.
- Renumbering gpu-1 or changing Kubernetes node identity.

## Implementation Shape

The repo carries `patches/phase04-gpu/404-gpu1-usb-25g-nic.template.yaml`, a deliberately non-applied template. During the maintenance window the operator plugs in the USB adapter, discovers its MAC address, copies the template to `404-gpu1-usb-25g-nic.yaml`, replaces the MAC placeholder, validates the YAML, and applies it through Omni.

Expected Talos shape:

- `machine.network.interfaces[].deviceSelector.hardwareAddr: <USB_25G_MAC_ADDRESS>`
- `addresses: [192.168.55.31/24]`
- default route via the existing LAN gateway
- `dhcp: false`

If live discovery shows the current gateway is not `192.168.55.1`, the operator must use the live default gateway, not the template comment. Frank is declarative, not clairvoyant. That remains annoying.

## Acceptance

- gpu-1 remains the same Kubernetes node and serves `192.168.55.31` through the USB 2.5G adapter.
- Talos detects the adapter with a usable driver and stable link.
- Cilium on gpu-1 initializes its direct-routing datapath against the replacement NIC and stays healthy.
- `layer-1-nic-link-flap` stays quiet for gpu-1 over the post-swap soak window.
- GPU workloads survive the maintenance event and return to service after gpu-1 rejoins.

## Test Plan

Post-merge, operator-driven maintenance-window swap after the USB adapter arrives:

1. Before shutdown, capture current state: `kubectl get node gpu-1 -o wide`, `talosctl -n 192.168.55.31 get links`, `talosctl -n 192.168.55.31 dmesg | grep -Ei 'enp3s0|r8169|usb|cdc|r815|aqc|realtek|ether' | tail -80`, and the current `node_network_carrier_changes_total` value for gpu-1.
2. Power down gpu-1, plug in the USB 2.5G Ethernet adapter, move the Ethernet cable from the onboard Realtek port to the USB adapter, and leave the onboard port unplugged.
3. Boot gpu-1 and discover the new interface: `talosctl -n 192.168.55.31 get links` or Omni console if the address does not come back immediately. Record interface name, MAC, driver hint from `dmesg`, and negotiated speed/link state.
4. If Talos does not detect the adapter, stop and record the vendor/device evidence before changing config. Do not guess a patch for a missing driver.
5. Copy `patches/phase04-gpu/404-gpu1-usb-25g-nic.template.yaml` to `patches/phase04-gpu/404-gpu1-usb-25g-nic.yaml`, replace `<USB_25G_MAC_ADDRESS>` with the discovered MAC, and commit that concrete patch to this PR.
6. Apply with Omni: `omnictl apply -f patches/phase04-gpu/404-gpu1-usb-25g-nic.yaml`.
7. Verify node identity and networking: `kubectl get node gpu-1 -o wide`, Cilium pod on gpu-1 Ready, `cilium-dbg status --brief` from the gpu-1 Cilium pod, and LoadBalancer SSH paths to gpu-1-hosted agent pods reconnect.
8. Verify GPU workloads return: `kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'` returns `1`; Ollama/ComfyUI/agent pods are Ready or intentionally scaled.
9. Soak for 24h and confirm `increase(node_network_carrier_changes_total{instance="192.168.55.31:9100"}[30m])` does not breach the `layer-1-nic-link-flap` threshold. Record the metrics query and outcome in the PR before merge-ready.

## Implementation Plans

| Plan | Status | Notes |
| ---- | ------ | ----- |
| `docs/superpowers/plans/2026-07-09--gpu--gpu-1-usb-25g-nic/` | Draft | Repo prep plus final manual hardware/Omni phase for the incoming USB adapter. |
