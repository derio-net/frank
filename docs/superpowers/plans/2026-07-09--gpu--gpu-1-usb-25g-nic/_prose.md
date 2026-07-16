# gpu-1 USB 2.5G NIC Replacement — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-07-09--gpu--gpu-1-usb-25g-nic-design.md`  
**Layer:** gpu · **Repo:** derio-net/frank · **Branch:** `feat/gpu-1-i22x-lan-apply`

## Why

gpu-1's onboard Realtek `enp3s0` has already caused a Cilium datapath collapse after the power outage. `pcie_aspm=off` stopped the page storm but did not restore confidence in the port. The attempted PCIe I22X-LAN replacement did not fix the path, so the next repair is the incoming USB 2.5G Ethernet adapter.

## Approach

Prepare the repo for a MAC-bound Talos ConfigPatch and document the operator runbook. The actual USB adapter arrival, installation, driver/link discovery, concrete patch creation, Omni apply, and 24h soak are manual and intentionally back-loaded.

## Phases

1. **Repo prep and validation** — replace the I22X-LAN prep with a non-applied USB 2.5G adapter template, update gpu-1 docs/gotchas, and validate YAML/agent config.
2. **[manual] USB adapter install and Omni apply** — operator plugs in the adapter, confirms Talos detects it, fills the MAC-bound concrete patch, applies it, verifies Cilium/GPU/workloads, and records the 24h flap soak.

## Acceptance Rows

The plan links rows for gpu-1 network stability, USB adapter detection, Cilium datapath recovery, and GPU workload return after the maintenance event.

## Phase 2 — manual operation (operator, maintenance window)

```yaml
# manual-operation
id: gpu-gpu1-usb-25g-nic-install
layer: gpu
app: gpu-1
plan: 2026-07-09--gpu--gpu-1-usb-25g-nic
when: After the USB 2.5G Ethernet adapter arrives, during a gpu-1 maintenance window.
why_manual: Physical USB adapter installation, live NIC MAC/driver discovery, and Omni apply/reboot are operator-only actions.
commands: |
  # Before shutdown: capture current state and recent Realtek/USB evidence.
  kubectl get node gpu-1 -o wide
  talosctl -n 192.168.55.31 get links
  talosctl -n 192.168.55.31 dmesg | grep -Ei 'enp3s0|r8169|usb|cdc|r815|aqc|realtek|ether' | tail -80

  # Power down gpu-1, plug in the USB 2.5G adapter, move the Ethernet cable
  # to the adapter, and leave the onboard Realtek port unplugged.

  # After boot: discover the adapter MAC/name/driver. If 192.168.55.31 does
  # not return before the patch, use Omni console/local Talos access.
  talosctl -n 192.168.55.31 get links
  talosctl -n 192.168.55.31 dmesg | grep -Ei 'usb|cdc|r815|aqc|realtek|ether' | tail -80

  cp patches/phase04-gpu/404-gpu1-usb-25g-nic.template.yaml \
    patches/phase04-gpu/404-gpu1-usb-25g-nic.yaml
  # Replace <USB_25G_MAC_ADDRESS> with the discovered MAC and adjust gateway if needed.
  omnictl apply -f patches/phase04-gpu/404-gpu1-usb-25g-nic.yaml
verify: |
  kubectl get node gpu-1 -o wide
  kubectl -n kube-system get pod -o wide | grep 'cilium-.*gpu-1'
  kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
  # 24h soak: confirm the layer-1-nic-link-flap threshold does not breach for gpu-1.
status: pending
```

## Deviation — 2026-07-16: USB NIC firmware warning

Live-verified 2026-07-11 that Talos loads the USB adapter's r8152 driver but logs
`Direct firmware load for rtl_nic/rtl8156b-2.fw failed` — the RTL8156B firmware blob
is absent from gpu-1's schematic (recorded in acceptance row `gpu1-usb-25g-detected`:
"missing rtl8156b firmware patch logged but link works"). The link runs on the chip's
built-in firmware, so this is cosmetic, but it is fixed by adding the
`siderolabs/realtek-firmware` extension (ships the full `rtl_nic/` tree) to gpu-1's
single per-machine extension list, `patches/phase04-gpu/402-gpu1-nvidia-extensions.yaml`.
Because a per-machine `ExtensionsConfiguration` overrides rather than merges, the
firmware extension MUST go in that existing file (not a new one). Re-applying it
rebuilds the image and reboots gpu-1 → operator-only, maintenance window (below).

```yaml
# manual-operation
id: gpu-gpu1-usb-25g-nic-firmware
layer: gpu
app: gpu-1
plan: 2026-07-09--gpu--gpu-1-usb-25g-nic
when: Next gpu-1 maintenance window (image rebuild + reboot). Bundle with any other pending gpu-1 schematic change (e.g. 403 PCIe ASPM) to avoid a second reboot.
why_manual: Re-applying an ExtensionsConfiguration rebuilds gpu-1's Talos image and reboots the only GPU node; Omni apply is operator-only.
commands: |
  # Capture the current (failing) firmware log line for before/after evidence.
  talosctl -n 192.168.55.31 dmesg | grep -i 'rtl8156b-2.fw'   # expect: "Direct firmware load ... failed"

  # Apply the updated single per-machine extensions list (now includes siderolabs/realtek-firmware).
  source .env_devops
  omnictl apply -f patches/phase04-gpu/402-gpu1-nvidia-extensions.yaml
  # gpu-1 rebuilds its image and reboots. Wait for it to return.
  source .env
  kubectl get node gpu-1 -w   # wait until Ready
verify: |
  source .env
  talosctl -n 192.168.55.31 get extensions | grep realtek-firmware       # present
  talosctl -n 192.168.55.31 dmesg | grep -i 'rtl8156b-2.fw'              # no "failed" line
  kubectl get node gpu-1 -o wide                                          # Ready on 192.168.55.31
  kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'  # still 1 (schematic override kept nvidia)
status: pending
```

## Post-Merge Test Plan

Use the spec's maintenance-window Test Plan verbatim. The layer is not complete until Talos detects the adapter, the concrete MAC-bound patch is pushed, the node returns on `192.168.55.31`, Cilium is healthy on gpu-1, the NVIDIA allocatable count is `1`, and the 24h flap soak stays below alert threshold.
