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
