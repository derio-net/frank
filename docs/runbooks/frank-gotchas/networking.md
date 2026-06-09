# Frank Gotchas — Networking

Long-form companion to the **Networking** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## mosh `--ssh=CMD` argv ordering trap

`mosh --ssh=CMD` appends the positional `[user@]host` as a separate argv token — so `mosh --ssh="ssh user@IP" IP` becomes `ssh user@IP IP mosh-server…`, and SSH treats the second `IP` as the remote command: `bash: IP: command not found`.

Correct shape: put flags only in `--ssh` and put `user@host` in the positional:

```bash
mosh --ssh="ssh -i ~/.ssh/<key>" --server="mosh-server new -p 60000:60015" agent@IP
```

The LB-port-range `--server` pin is also mandatory — without it, `mosh-server` roams the full 60000–61000 default range and most ports aren't forwarded by the Service. Use the per-shell wrappers in `apps/*/client-setup/laptop/` to avoid repeating this.

## Cilium 1.17 FQDN policies need DNS-proxy initialization

Cilium 1.17 FQDN policies fail with "FQDN regex compilation LRU not yet initialized" if no endpoint on the node has previously triggered DNS proxy initialization. Workaround: restart Cilium agent on the node, or use CIDR-based policies until the issue is resolved upstream.

Stale BPF egress rules persist even after deleting the CiliumNetworkPolicy — must also restart the Cilium agent to clear them.

## MixedProtocolLBService — TCP + UDP on a single Cilium L2 LB IP

MixedProtocolLBService — TCP/22 + UDP/60000–60015 on a single Cilium L2 LB IP works on Cilium 1.17 + K8s 1.35. `paperclip-shell` (192.168.55.221) and `ruflo-shell` (192.168.55.222) both expose SSH and Mosh on the same `LoadBalancer` Service via a multi-protocol port list. No feature gate flip, no annotation, no per-protocol service split. The ports are bound on a single EndpointSlice and answered by the same sidecar Pod. Useful when adding any future shell sidecar — don't pay the complexity tax of two Services.

## `lbipam.cilium.io/ips` alone is NOT a sharing directive

Separate Service objects need `lbipam.cilium.io/sharing-key` to share one LB IP. When you can't merge multiple ports into one `Service` (because the upstream Helm chart splits them, e.g. Gitea's `gitea-http` :3000 and `gitea-ssh` :2222), annotating both Services with the same `lbipam.cilium.io/ips: "<addr>"` does NOT cause Cilium L2 IPAM to coordinate the allocation. IPAM treats each annotation as an independent request, gives the IP to whichever Service it processes first, and leaves the other at `EXTERNAL-IP <pending>` indefinitely with no error event.

The fix is to *also* add `lbipam.cilium.io/sharing-key: "<arbitrary-string>"` (any value, identical across the Services that should share). Cilium documents this as the only mechanism for cross-Service IP sharing when port sets don't conflict.

The Gitea SSH LB stayed pending for 41 days because the chart's split into two Services hid the failure — pipelines clone via the in-cluster ClusterIP so nothing inside the cluster noticed; only operator workstations needing `git@host:repo.git` were affected, and they had quietly switched to HTTPS.

Always check `kubectl get svc -A | grep pending` after deploying any chart that splits one logical service across multiple `Service` objects on a shared LB IP.

Order of preference for "two ports, one IP":
- (a) one Service with both ports if the chart allows it (MixedProtocolLBService gotcha above)
- (b) two Services with matching `sharing-key`
- (c) accept two distinct LB IPs

## Caddy JSON access logs put the vhost in `request.host`, not `_msg`

Hop's Caddy ships JSON access logs to Frank's VictoriaLogs. Every access-log line shares the same `_msg` value — literally `"handled request"`. The requested host lives in a structured field, `request.host`. This trips anyone who reaches for the obvious substring filter:

```logsql
# WRONG — matches zero rows, always. _msg is the constant "handled request".
_time:1d kubernetes.host:hop-1 AND _msg:"blog.derio.net"

# RIGHT — filter the structured field.
_time:1d kubernetes.host:hop-1 AND request.host:"blog.derio.net"
```

The failure is silent: a zero-match filter returns `0`, which reads like "no traffic" rather than "wrong field." It bit the AI digest twice — `surge.py._hour_count` filtered `_msg:"blog.derio.net"` and so could never detect a blog surge, and `facts.build_for_digest` omitted any host filter at all, counting *every* Hop vhost.

Live evidence (2026-05-25): the unfiltered edge total was **15,717 requests/day** across all Hop vhosts (Headscale, Headplane, landing, ACME, bots, probes, blog), while `request.host:"blog.derio.net"` was a small fraction of that. Always scope edge queries to the node with `kubernetes.host:hop-1`, then group or filter on `request.host` for a specific vhost:

```logsql
_time:1d kubernetes.host:hop-1 AND _msg:"handled request" | stats by (request.host) count()
```

## gpu-1 NIC link-flap → Cilium datapath collapse → simultaneous SSH drops on all gpu-1 pods (2026-06-08)

**Symptom.** Two unrelated SSH sessions — to `hermes-agent-shell` (LB `192.168.55.226`) and `secure-agent-pod` (LB `192.168.55.215`) — dropped at the *same instant* with `Shared connection to <ip> closed` and exit code **255**. Both pods are on **gpu-1**.

**Misleading "alive" signals.** Both pods were `Running` with `0` restarts; `kubectl exec` into them worked fine; the node was `Ready`; gpu-1 had ~105 GB free RAM. None of the usual Frank failure modes (Longhorn IM leak, `claude install` OOM that kills sshd, memory wedge) applied. The trap: `exec` rides API-server → kubelet → CRI (the node's kubelet stream) and does **not** traverse the Cilium pod datapath, whereas SSH-via-LoadBalancer **does**. So a pod can look perfectly healthy to the control plane while its pod networking is severed.

**Root cause.** gpu-1's onboard Realtek 2.5GbE NIC (`r8169 0000:03:00.0`, `enp3s0`) was physically link-flapping:

```
12:06:43 r8169 enp3s0: Link is Up - 2.5Gbps   → talos assigns 192.168.55.31/24 + default route
12:06:53 r8169 enp3s0: Link is Down           → talos REMOVES 192.168.55.31/24
12:06:56 Up   12:06:57 Down   12:07:02 Up   12:07:03 Down   ...   (every 1-10s)
```

Every link-down strips `192.168.55.31/24` from `enp3s0` — which is Cilium's **direct-routing device**. With the device IP gone, the Cilium agent on gpu-1 cannot (re)initialize its datapath and loops every 10s:

```
level=error msg="Unable to write node config header"
  error="...node_config.h: IPv4 direct routing device IP not found" subsys=datapath-loader
level=warn  msg="Failed to initialize datapath, retrying later" retry-delay=10s
# plus: L2-announce lease renewals fail with TLS handshake timeout to 127.0.0.1:7445 (KubePrism)
```

With the datapath unprogrammed, **all pod traffic to/from gpu-1 dies** — every TCP connection to a gpu-1-hosted pod resets, so every SSH session into a gpu-1 pod drops together. The Cilium errors are a **symptom**; the disease is the physical link. `talosctl` and `kubectl exec` against gpu-1 also flake intermittently during the storm (`connection reset by peer` to apid).

**Trigger.** A **power outage the previous night** (~03:57Z, matching the first `enp3s0` flap and the Cilium agent's "8h ago" restart). The ungraceful power-cycle left the cable/connector marginally seated on a chassis that has **only one NIC port** (no host-side failover). Fine at idle, dropping under 2.5G renegotiation churn. It then escalated from intermittent (over ~8h) to a continuous storm.

**Scope confirmation.** gpu-1 only — `node_network_carrier_changes_total{device="enp3s0"}` over the incident was **76 on gpu-1**, **0 elsewhere**; mini-1 had 3 carrier changes across its entire 97-day uptime, pc-1 had 0. Not the switch, not the LAN.

**Diagnosis commands.**

```bash
source .env
# physical layer — the actual flap
talosctl -n 192.168.55.31 dmesg | grep 'enp3s0: Link is' | tail
# the symptom — Cilium datapath loop
kubectl logs -n kube-system <cilium-pod-on-gpu-1> --since=5m | grep -Ei 'direct routing|datapath|node config'
# prove pod is alive (exec bypasses the datapath) while SSH (via LB) is dead
kubectl exec -n hermes-agent-shell deploy/hermes-agent-shell -- uptime
# scope: carrier changes per node from metrics
curl -sG 'http://<vmsingle>:8428/api/v1/query' \
  --data-urlencode 'query=increase(node_network_carrier_changes_total{device="enp3s0"}[12h])'
```

**Recovery.** Nothing in software — Cilium retries every 10s and self-heals the instant the link is *stably* up. **Do not drain gpu-1**: it is the only GPU node (ollama/litellm/comfyui live there) and both agent pods are hard-pinned (`nodeSelector: kubernetes.io/hostname: gpu-1`), so they'd go `Pending`, not migrate. Fix is physical:

1. **Reseat (or replace) the Ethernet cable; move the *switch-end* port** (host has one port only). Reseating resolved the 2026-06-08 incident — link went quiet, Cilium reloaded the BPF datapath onto `enp3s0` (`cil_from_netdev`/`cil_to_netdev`) within seconds, `cilium-dbg status --brief` → `OK`. Reconnect SSH afterward.
2. **It recurred after the cable reseat → durable driver/power mitigation.** The reseat only downgraded the continuous storm to intermittent flapping (recurred 2026-06-08 13:18/13:30/13:49/20:45, caught by the `layer-1-nic-link-flap` alert). `r8169` flapping is classically PCIe **ASPM** / **EEE** instability that survives reboots (unlike a reseat). The durable fix is prepped as an Omni ConfigPatch: **`patches/phase04-gpu/403-gpu1-pcie-aspm.yaml`** (`machine.install.extraKernelArgs: [pcie_aspm=off]`, gpu-1 machine UUID). Apply in a maintenance window — it reboots the only GPU node:
   ```bash
   omnictl apply -f patches/phase04-gpu/403-gpu1-pcie-aspm.yaml
   talosctl -n 192.168.55.31 read /proc/cmdline | grep -o 'pcie_aspm=off'   # verify after reboot
   # then watch the flap counter go quiet:
   # increase(node_network_carrier_changes_total{instance="192.168.55.31:9100",device="enp3s0"}[30m])
   ```
   If `pcie_aspm=off` doesn't hold, escalate: switch-end cable + different switch port → cap the link to 1G (2.5G negotiation) → NIC replacement (one chassis port, no host-side failover).

**Likely the real cause of the long-standing gpu-1 flakiness.** The `gpu-1.md` gotcha "`kubectl port-forward` flakes regularly with CNI-netns errors on gpu-1 pods only" is very plausibly chronic low-grade link instability on this same NIC, now gone acute. Re-attribute once a durable fix (cable + ASPM) is proven to hold.

### Why none of the existing alerts fired (monitoring gap)

The data was captured perfectly (`node_network_carrier_changes_total` = 76 on gpu-1), but **no alert fired**, because every host/network rule is a binary *down-state* threshold with `for: 5m`:

| Rule | Expr | Why it stayed silent |
|------|------|----------------------|
| Layer 1 Hardware Node NotReady | `kube_node_status_condition{condition="Ready",status="false"}` `for: 5m` | Node never sustained NotReady — kubelet posted `Ready` during each up-window; the 40s node-monitor-grace never elapsed continuously. |
| Layer 3 Cilium Agent Down | `kube_pod_status_ready{pod=~"cilium-.*",condition="true"}` `for: 5m` | The Cilium pod stayed `Running`/`Ready` the whole time — it was *alive and retrying*, not down. Pod-readiness ≠ datapath-healthy. |
| Endpoint Down | `probe_success{probe_group="feature_health"}` `for: 5m` | Blackbox feature-health probes; intermittent up-windows let probes succeed within any 5m, so nothing sustained. |

Two structural blind spots:
- **"Alive but flapping" ≠ "down."** A fast flap is up-on-average and never sustains a 5m down-state, so binary `== false` / `for: 5m` rules are blind to it *by construction*. The correct signal is a **rate of change**, not a state threshold.
- **Scrape aliasing.** `changes(node_network_up{device="enp3s0"}[12h])` registered only **1** — the ~30s scrape sampled "up" most times and missed the sub-10s flaps. The kernel **counter** `node_network_carrier_changes_total` caught all 76. Alert on the counter's rate, never on the up/down gauge.

**The fix** — the `layer-1-nic-link-flap` rule (`apps/grafana-alerting/manifests/alert-rules-cm.yaml`, added in the 2026-06-08 `obs--nic-link-flap-alert` plan) fires on flap *rate* regardless of state-sustain or scrape interval:

```
increase(node_network_carrier_changes_total{device=~"en.*|eth.*"}[30m]) > 6
# folder feature-health, severity warning, github_issue frank-ops#1 → Telegram + Health Bridge
# annotations template {{ $labels.instance }} / {{ $labels.device }} (the metric has
# instance+device, NOT node); for: 0m (the 30m window is the smoothing).
```

The 30m window catches *sustained* flapping (≥6 changes/30m) while staying reboot/replug-safe: `increase()` is counter-reset-aware, so a reboot (~1 boot link-up) and a cable replug (≤2) stay under the threshold. A node-down alert would also help if it triggered faster, but the flap-rate rule is the precise catch — it fires once flapping is sustained, well before a full storm severs connectivity. (A *truly* sparse fault — one flap per ~10 min — stays under threshold by design; no rate threshold can catch that without also flagging routine reboots.)
