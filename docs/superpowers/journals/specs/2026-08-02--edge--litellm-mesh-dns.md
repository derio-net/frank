# Journal: 2026-08-02--edge--litellm-mesh-dns

<!-- fr:journal kind=discovery scope=spec id=route-exists-dns-missing created=2026-08-02T16:06:41 -->
### route-exists-dns-missing · discovery · Route already exists; only DNS is missing

Live evidence 2026-08-02. `headscale routes list`: 192.168.55.0/24 advertised AND enabled by argonath-w (primary) and argonath-e; both online. All three kid laptops (t490s 100.64.0.9, x1yoga .10, p52 .11) are registered mesh nodes. From hop-1 (Hetzner, off-LAN, --accept-routes): http://192.168.55.206:4000/health/liveliness returns "I'm alive!" and /v1/models returns LiteLLM's OWN 401 (not an Authentik 302). Public ingress litellm.cluster.derio.net returns 302 to auth.cluster.derio.net. Conclusion: routing, ACL, mesh membership and Bearer auth are ALL already in place; the sole gap is that no mesh-resolvable name points at the LiteLLM LB. The issue's claim of 'neither a name nor a route' is half right.

<!-- fr:journal kind=discovery scope=spec id=ownership-verdict created=2026-08-02T16:07:03 -->
### ownership-verdict · discovery · Ownership: frank owns the gap; the other two repos are already done

proxmox-cluster (argonath-{e,w}): advertises 192.168.55.0/24 + exit nodes — DONE, verified enabled and online. omada-controller (inter-VLAN routing VLAN10 -> 192.168.55.0/24): DONE, proven by hop-1 reaching 192.168.55.206 across the mesh. derio-net/frank: owns clusters/hop/apps/headscale/manifests/configmap.yaml, which holds Headscale's MagicDNS extra_records and split-DNS — this is the gap. kid-laptops: consumer-side --accept-routes + base URL. Note the non-obvious split: Headscale RUNS on Hop but is GitOps-configured from the frank repo.

<!-- fr:journal kind=discovery scope=spec id=extra-records-precedent created=2026-08-02T16:07:04 -->
### extra-records-precedent · discovery · extra_records precedent proven live (gitea-ssh)

clusters/hop/apps/headscale/manifests/configmap.yaml already carries 'gitea-ssh.cluster.derio.net -> 192.168.55.209' for exactly this reason (Traefik cannot carry SSH, so mesh peers get a name straight to the LB). Verified from the operator's Mac: getent resolves it to 192.168.55.209, while Cloudflare DoH returns NXDOMAIN (status=3) for gitea-ssh/litellm/cluster.derio.net. So *.cluster.derio.net is homelab-DNS-only and the extra_record is what makes such a name work on the mesh. This makes the fix a one-line application of an existing, working pattern rather than a new mechanism.

<!-- fr:journal kind=discovery scope=spec id=headscale-cm-no-autoroll created=2026-08-02T16:07:06 -->
### headscale-cm-no-autoroll · discovery · Headscale CM change will NOT roll the pod — manual restart required

clusters/hop/apps/headscale/manifests/kustomization.yaml lists configmap.yaml under plain 'resources:', NOT configMapGenerator. Per the documented hop gotcha, it CANNOT be hash-generated: headplane is a separate ArgoCD Application that mounts the same headscale-config with config_strict: true, and kustomize cannot rewrite a cross-Application reference. Consequence: ArgoCD will report Synced, the ConfigMap will hold the new record, and headscale will keep serving the OLD DNS map indefinitely. A 'kubectl -n headscale-system rollout restart deploy/headscale' is a REQUIRED deployment step, not an optional nicety.

<!-- fr:journal kind=discovery scope=spec id=snat-confirmed created=2026-08-02T17:06:48 -->
### snat-confirmed · discovery · Mesh traffic passes Traefik ip-allowlist (argonath SNATs)

Tested from hop-1's tailscale pod: 'wget --header=Host: litellm.cluster.derio.net https://192.168.55.220/v1/models' returned 302 to Authentik, NOT 403. Middleware order is ip-allowlist -> security-headers -> authentik-forwardauth, so reaching the 302 proves ip-allowlist ACCEPTED the request. Therefore the subnet router SNATs to its own RFC1918 address (tailscale --snat-subnet-routes defaults true) and the 100.64.0.0/10 gap in ip-allowlist is moot. Phase 2 needs NO change to the ip-allowlist middleware; the only reason the public name fails is the forward-auth middleware, which the new route will simply not carry.

<!-- fr:journal kind=decision scope=spec id=two-records-not-repoint created=2026-08-02T17:06:50 -->
### two-records-not-repoint · decision · Two permanent records rather than repointing one

Operator chose 'Both - LB now, TLS after' with hostname litellm-api. Literal reading (one name repointed .206 -> .220 in phase 2) fails when both phases ship in ONE PR: a record has one value, so the interim never serves and the migration becomes a hard cutover. Resolved by shipping TWO permanent records instead: litellm-lb.cluster.derio.net -> 192.168.55.206 (direct LB, http:4000, the measured-working escape hatch) and litellm-api.cluster.derio.net -> 192.168.55.220 (Traefik, https:443, canonical). Honours the chosen journey (laptops start on http, migrate to https) while removing the coordinated-flip risk. Justified by the travel deadline: -lb depends only on Cilium L2 + the subnet route, whereas -api additionally depends on Traefik, the cert resolver and the middleware chain, so -lb survives a Traefik failure the operator could not debug remotely. Cost is one line of YAML and zero new network access.

<!-- fr:journal kind=review scope=spec id=spec-review-verify-cmds created=2026-08-02T17:09:13 -->
### spec-review-verify-cmds · review · Spec review: two Test Plan commands would have failed on the operator's machine

(1) Both the manual-op verify block and Test Plan step 3 used 'getent hosts'. macOS ships no getent — measured earlier this session, where getent failed and dscacheutil succeeded. The operator drives the Test Plan from the Mac, so every verification step would have errored out. Fixed: dscacheutil for macOS, getent kept for Linux mesh nodes. (2) Test Plan step 3 told the operator to prove public NXDOMAIN with 'dig @1.1.1.1' — but the homelab blocks outbound port 53, so that times out on the LAN and proves nothing (measured: connection timed out for all four names). Fixed: use Cloudflare DoH over HTTPS, which is what actually worked. Both errors came from writing verification steps against the environment I was probing FROM rather than the one the operator would run them IN.

<!-- fr:journal kind=review scope=spec id=spec-review-cert-reuse created=2026-08-02T17:09:15 -->
### spec-review-cert-reuse · review · Spec review: clarified no new ACME order

Reviewed the new IngressRoute against apps/traefik/manifests/ingressroutes.yaml. The existing litellm route declares tls.domains[0].main = '*.cluster.derio.net' with certResolver cloudflare; declaring the same wildcard on the new route makes Traefik reuse the issued certificate rather than order a per-host cert. Called out explicitly in the spec because 'new hostname' otherwise reads as ACME rate-limit exposure, which was a real concern on this repo's public edge. Also confirmed cross-namespace service refs work (traefik-system -> litellm/litellm:4000) since the existing public route already does exactly that.
