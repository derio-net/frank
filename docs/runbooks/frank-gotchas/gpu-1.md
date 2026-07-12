# Frank Gotchas — gpu-1 specifics

Long-form companion to the **gpu-1 specifics** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## NoSchedule taint pattern (defensive even when the live taint list is empty)

gpu-1 has no NoSchedule taint at the moment (`spec.taints: []` on the Node), but the cluster idiom for pinning a workload there is `nodeSelector: kubernetes.io/hostname: gpu-1` plus a defensive `nvidia.com/gpu:NoSchedule` toleration (ollama, n8n, openrgb, secure-agent-pod, paperclip all carry it). The toleration is insurance against the GPU operator re-asserting the taint on driver re-validation; pods without it would be evicted in that window. Keep mirroring the pattern even when the live taint list is empty.

## `kubectl port-forward` flakes with CNI-netns errors

`kubectl port-forward` (and CLIs that wrap it, like `argocd --port-forward`) regularly fails on pods scheduled to gpu-1 with `failed to execute portforward in network namespace "/var/run/netns/cni-…": read: connection reset by peer`. The flake is CNI-netns-level, not app-level.

Workarounds:

- For `argocd app list/get`: use `kubectl get application -n argocd -o wide` — same columns (sync/health/revision/project), native transport, no port-forward.
- For metrics endpoints (blackbox `/probe`, pushgateway `/metrics`, etc.): `kubectl exec deploy/<target> -- wget -qO- localhost:<port>/<path>` instead of port-forward + local curl. The exec path uses the pod's own network namespace cleanly.
- Pods on mini-1/2/3 are unaffected — only gpu-1's netns has the issue.

## enp3s0/r8169 link-flap — `pcie_aspm=off` suppresses it; USB 2.5G replaces it

gpu-1's onboard 2.5GbE NIC (`enp3s0`, Realtek r8169) chronically link-flaps — `Link is Down`/`Up` every minute or two — which strips the node IP off Cilium's direct-routing device and collapses the datapath (mass SSH/pod-traffic drop; watched by the `layer-1-nic-link-flap` Grafana alert, `increase(node_network_carrier_changes_total[30m]) > 6`). It's a classic r8169 PCIe Active State Power Management instability: the link drops into L1 during an idle lull and the PHY mishandles the wake.

### The fix that worked — and how to apply kernel args on this cluster

`pcie_aspm=off` (boot arg, pins the PCIe link at L0 so the broken L1-wake path is never exercised). On Frank this is **#582** — and the *mechanism* is the load-bearing lesson:

- **Use a `KernelArgs.omni.sidero.dev` resource, NOT a `ConfigPatches` `machine.install.extraKernelArgs`.** Frank's machines boot a UKI (`grubUseUKICmdline: true`), so the cmdline is baked into the signed image — kernel args must flow through the Omni **schematic**. `machine.install.extraKernelArgs` does *not* change the schematic id, so Omni reports `configuptodate: true` and never reinstalls; the arg is inert (this is why `#515`, merged 2026-06-09, never applied). The `KernelArgs` resource (keyed by machine-id, the kernel-arg analogue of `402`'s `ExtensionsConfigurations`) folds the arg into the schematic → Omni recomputes the install image → Omni-managed reinstall + reboot. Declarative, no break-glass, no taint. Resource lives at `patches/phase04-gpu/403-gpu1-pcie-aspm.yaml`.
- `talosctl upgrade` (the old patch's documented fallback) is **refused by Omni's API proxy for every role** including Admin — the only direct-talosctl path is `--break-glass`, which taints the cluster (and was disabled for the devops SA anyway). Don't go there; the `KernelArgs` route is the supported one.
- Omni **v1.5.0 has no UI surface** for kernel args (the machine page shows extensions + config-patches only). Inspect via `omnictl get kernelargs <machine-id> -o yaml` and `omnictl get kernelargsstatus <machine-id>` (the latter's `CURRENT ARGS` flips to the applied value, and `CURRENT CMDLINE` shows the live cmdline once the reboot lands).
- **Verify live** (UI/status can lag): `talosctl -n 192.168.55.31 dmesg | grep pcie_aspm=off` (the kernel `Kernel command line:` boot line). The Omni-issued reader talosconfig may lack `os:admin` for `talosctl read /proc/cmdline` (esp. after an `omni` restart rotates certs) — `dmesg` works at a lower role.

### Suppresses, does not cure

Post-deploy (#582, 2026-06-19): flap rate dropped from ~every 1–2 min (138 events accrued) to **~1 flap in 6 hours** — far below the alert threshold, so the notification storm is gone, but the NIC is **not 100% stable**.

The current durable path is replacement, not more Realtek tuning. The attempted PCIe I22X-LAN card did not fix the path, so the next repair is the incoming USB 2.5G Ethernet adapter: move `192.168.55.31/24` to that adapter with a MAC-bound Talos ConfigPatch and leave the onboard Realtek port unplugged. The repo carries the fill-in template at `patches/phase04-gpu/404-gpu1-usb-25g-nic.template.yaml`; after live MAC/driver discovery, copy it to `404-gpu1-usb-25g-nic.yaml`, replace `<USB_25G_MAC_ADDRESS>`, apply with Omni, and soak the `layer-1-nic-link-flap` metric for 24h.

### Incident note

The fix was delayed not just by the wrong mechanism but by a **wedged Omni control plane** — after a power-outage cold boot, Omni's reconcile runtime had silently deadlocked on a clock-jump and applied nothing for days (see `omni.md`). The `KernelArgs` resource only reconciled and rebooted gpu-1 *after* `docker restart omni` revived the runtime.

## USB 2.5G static config → DNS boot-hang (see `networking.md`)

The USB 2.5G migration (`404-gpu1-usb-25g-nic.yaml`) made gpu-1 the fleet's first **static-networked** host — `dhcp: false` with no `nameservers`. On the 2026-07-12 power-restart it hung ~12h "pinging but dead": static interface → public-DNS fallback (`1.1.1.1`/`8.8.8.8`) → ACL-blocked → no NTP → time-sync-gated `apid`/`kubelet`/`siderolink`. Fixed fleet-wide by the cluster-wide `102-cluster-nameservers` patch. Full failure chain, console signature, and the emergency ACL unblock: **`networking.md` → "Static Talos interface with no `nameservers`"**.

## Ollama "system memory" errors mean container cgroup RAM, not VRAM

When Ollama returns `model requires more system memory (X GiB) than is available (Y MiB)`, "system memory" means container RAM, not GPU VRAM. With `OLLAMA_KEEP_ALIVE=24h` page cache from previously-loaded models pins the cgroup near its `resources.limits.memory` ceiling, so a 15 GB model can fail to load even when `nvidia-smi` shows ~15 GB of VRAM free and the host has 60 GB of RAM idle — the gpu-1 container was simply at 31/32 GiB.

Diagnose by comparing `cat /sys/fs/cgroup/memory.{current,max}` (the real constraint) against `nvidia-smi --query-gpu=memory.free` (often misleadingly empty for this error). Reducing `num_ctx` via a derived Modelfile does **not** help — the bottleneck is at-load working buffers, not steady-state KV cache, so the error message is identical at 32K and 8K context.

Fix on Frank was bumping `apps/ollama/values.yaml` `resources.limits.memory` from 32Gi → 64Gi to comfortably fit the 5-model lineup with 24h keepalive.

## ComfyUI custom-node PVC seed (version-gated re-seed)

ComfyUI's custom nodes are baked into the image at `/opt/stoa-custom-nodes/` but
run from the `comfyui-custom-nodes` PVC mounted at `/app/custom_nodes` (the PVC
mount **shadows** the baked dir). `entrypoint.sh` copies the baked nodes into the
PVC on boot.

**The bug (2026-06-15, after the v0.24 bump).** The seed was *seed-if-absent*
(`if [ ! -d "$DEST/$name" ]`), so once a node existed in the PVC it was never
refreshed. A Dockerfile node patch therefore never reached an already-seeded PVC.
The `ComfyUI-LTXVideo` `pyramid_blending.py` kornia-`pad` patch (image rev 3) sat
in the baked copy while the PVC kept a stale **unpatched** copy from the original
seed. On `v0.9.2` the bundled kornia still exported `pad`, so the unpatched copy
imported fine and the bug stayed latent. The `v0.24.0` rebuild pulled **kornia
0.8.3**, which *dropped* `pad` from `kornia.geometry.transform.pyramid`, so the
stale PVC copy hit `ImportError: cannot import name 'pad'` and the whole node pack
logged `IMPORT FAILED` — taking the LTX loaders offline.

**Why it's invisible to a Ready check.** ComfyUI's HTTP server on `:8188` boots
even when custom-node imports fail (they're logged and skipped), so the pod is
`1/1 Ready`. Probe the actual node via `GET /object_info` (e.g. the LTX loader /
`CheckpointLoaderSimple.ckpt_name`), never pod existence — same lesson as the
GPU-time-share health probes.

**The fix (rev 5, version-gated re-seed).** A `.seed-version` marker keyed on
`${COMFYUI_REF}-stoa${STOA_NODES}` is baked at `/opt/stoa-custom-nodes/.seed-version`
(Dockerfile) and recorded in the PVC at `/app/custom_nodes/.stoa-seed-version`
after seeding. `entrypoint.sh` now: seeds a node when absent, **re-seeds
(overwrites) when `WANT != HAVE`** (i.e. on a deliberate image-rev bump), then
writes the marker. Manager-installed / operator-added nodes are not in `$STAGE`,
so they are never touched; an in-PVC edit to a *baked* node is superseded on a
bump (same tradeoff as `hermes-venv-seed`). Unchanged seed-version → no-op,
preserving the old behaviour between bumps. Mechanically: **bump `STOA_NODES`
whenever a baked node's files change** and the re-seed reaches the PVC on next
pod boot.

Recovery without a re-seeding image (one-off): remove the stale baked node from
the PVC and restart so the entrypoint re-seeds the patched copy —
`kubectl -n comfyui exec deploy/comfyui -- rm -rf /app/custom_nodes/<NodeName>`
then `kubectl -n comfyui rollout restart deploy/comfyui`.

**Persistence (which dirs survive a restart).** Only `/app/models`
(`comfyui-models`), `/app/custom_nodes` (`comfyui-custom-nodes`), `/app/output`
(`comfyui-output`) and `/app/user` (`comfyui-user`) are PVC-backed. `output`
(generated assets) and `user` (saved workflows/settings) were added later — they
were ephemeral originally, so a pod recreate (image bump or GPU-time-share scale
0→1) silently wiped renders and saved workflows (cost an early set of stoa-agent
test assets). Anything ComfyUI writes elsewhere in `/app` is still ephemeral.

## Intel GPU Resource Driver (separate from gpu-1)

Uses a vendored chart with K8s 1.35 DRA patches. Lives in `patches/phase05-mini-config/` for the iGPUs on the mini-* nodes — distinct from gpu-1's NVIDIA stack.
