# gpu-1 I22X-LAN NIC Replacement — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-07-09--gpu--gpu-1-i22x-lan-design.md`  
**Layer:** gpu · **Repo:** derio-net/frank · **Branch:** `feat/gpu-1-i22x-lan`

## Why

gpu-1's onboard Realtek `enp3s0` has already caused a Cilium datapath collapse after the power outage. `pcie_aspm=off` stopped the page storm but did not restore confidence in the port. The I22X-LAN PCIe card is the hardware repair.

## Approach

Prepare the repo for a MAC-bound Talos ConfigPatch and document the operator runbook. The agentic phase can safely add the template and update docs. The actual hardware install, MAC discovery, concrete patch creation, Omni apply, and 24h soak are manual and intentionally back-loaded.

## Phases

1. **Repo prep and validation** — add the non-applied I22X-LAN template, update gpu-1 docs/gotchas, and validate YAML/agent config.
2. **[manual] hardware install and Omni apply** — operator installs the card, fills the MAC-bound concrete patch, applies it, verifies Cilium/GPU/workloads, and records the 24h flap soak.

## Acceptance Rows

The plan links rows added for gpu-1 network stability, Cilium datapath recovery, and GPU workload return after the maintenance event.

## Phase 2 — manual operation (operator, maintenance window)

```yaml
# manual-operation
id: gpu-gpu1-i22x-lan-install
layer: gpu
app: gpu-1
plan: 2026-07-09--gpu--gpu-1-i22x-lan
when: During a gpu-1 maintenance window after this PR's repo-prep phase lands.
why_manual: Physical PCIe installation, live NIC MAC discovery, and Omni apply/reboot are operator-only actions.
commands: |
  # Before shutdown: capture current state and recent Realtek/I22X evidence.
  kubectl get node gpu-1 -o wide
  talosctl -n 192.168.55.31 dmesg | grep -E 'enp3s0|r8169|igc|i225|i226' | tail -50

  # Power down gpu-1, install the I22X-LAN PCIe card, move the Ethernet cable
  # to the new card, and leave the onboard Realtek port unplugged.

  # After boot: discover the new NIC MAC/name/driver. If 192.168.55.31 does
  # not return before the patch, use Omni console/local Talos access.
  talosctl -n 192.168.55.31 get links

  cp patches/phase04-gpu/404-gpu1-i22x-lan.template.yaml \
    patches/phase04-gpu/404-gpu1-i22x-lan.yaml
  # Replace <I22X_MAC_ADDRESS> with the discovered MAC and adjust gateway if needed.
  omnictl apply -f patches/phase04-gpu/404-gpu1-i22x-lan.yaml
verify: |
  kubectl get node gpu-1 -o wide
  kubectl -n kube-system get pod -o wide | grep 'cilium-.*gpu-1'
  kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
  # 24h soak: confirm the layer-1-nic-link-flap threshold does not breach for gpu-1.
status: pending
```

## Post-Merge Test Plan

Use the spec's maintenance-window Test Plan verbatim. The layer is not complete until the concrete MAC-bound patch is pushed, the node returns on `192.168.55.31`, Cilium is healthy on gpu-1, the NVIDIA allocatable count is `1`, and the 24h flap soak stays below alert threshold.
