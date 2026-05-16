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

## Ollama "system memory" errors mean container cgroup RAM, not VRAM

When Ollama returns `model requires more system memory (X GiB) than is available (Y MiB)`, "system memory" means container RAM, not GPU VRAM. With `OLLAMA_KEEP_ALIVE=24h` page cache from previously-loaded models pins the cgroup near its `resources.limits.memory` ceiling, so a 15 GB model can fail to load even when `nvidia-smi` shows ~15 GB of VRAM free and the host has 60 GB of RAM idle — the gpu-1 container was simply at 31/32 GiB.

Diagnose by comparing `cat /sys/fs/cgroup/memory.{current,max}` (the real constraint) against `nvidia-smi --query-gpu=memory.free` (often misleadingly empty for this error). Reducing `num_ctx` via a derived Modelfile does **not** help — the bottleneck is at-load working buffers, not steady-state KV cache, so the error message is identical at 32K and 8K context.

Fix on Frank was bumping `apps/ollama/values.yaml` `resources.limits.memory` from 32Gi → 64Gi to comfortably fit the 5-model lineup with 24h keepalive.

## Intel GPU Resource Driver (separate from gpu-1)

Uses a vendored chart with K8s 1.35 DRA patches. Lives in `patches/phase05-mini-config/` for the iGPUs on the mini-* nodes — distinct from gpu-1's NVIDIA stack.
