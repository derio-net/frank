---
paper: 20-edge-clusters-public-exposure
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Cloudflare Tunnel (cloudflared)
  positioning: "Outbound-initiated tunnel from origin to Cloudflare edge — no inbound ports, no static IP, free TLS via Cloudflare's CA. The dominant 'no edge node' option for homelabs behind residential ISPs."
  primary_url: "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/"
- name: Tailscale Funnel
  positioning: "Public exposure layered on top of the Tailscale mesh — your tailnet node becomes reachable from the open internet on a Tailscale-issued subdomain, TLS terminated by the Tailscale daemon on the device itself."
  primary_url: "https://tailscale.com/kb/1223/funnel"
- name: ngrok
  positioning: "Universal-gateway tunnel: outbound-initiated, ephemeral or reserved domain, paid plans for stable URLs, custom domains, and OAuth gating. Originally a dev-tunnel, now an 'API gateway' brand."
  primary_url: "https://ngrok.com/docs/universal-gateway/"
- name: Headscale + tiny VPS (Frank's pick — Hop)
  positioning: "Self-hosted Tailscale coordination on a public VPS that doubles as the reverse proxy and TLS terminator — full data-plane ownership, your own DNS, your own TLS keys. Hop is a single-node Talos cluster on Hetzner CX23 (~€5/month)."
  primary_url: "https://github.com/juanfont/headscale"
- name: Full multi-region cluster (Rancher Fleet across cloud + on-prem)
  positioning: "Enterprise heavyweight — one logical fleet spanning home cluster and one-or-more cloud regions, managed centrally, with the cloud region acting as the public-traffic landing pad."
  primary_url: "https://fleet.rancher.io/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Cloudflare Tunnel — Connect networks (developer docs)"
  type: vendor-docs
  url: "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/"
  quoted_passages:
    - "cloudflared initiates an outbound connection through your firewall from the origin to the Cloudflare global network."
    - "Once the connection is established, traffic flows in both directions over the tunnel between your origin and Cloudflare."
    - "configure your firewall to allow only these outbound connections and block all inbound traffic, effectively blocking access to your origin from anything other than Cloudflare."
  relevance: "Vendor's authoritative statement of the outbound-tunnel architecture: the cloudflared daemon dials out to Cloudflare's edge, Cloudflare's edge terminates TLS and serves the public hostname, and the origin needs zero inbound firewall holes. This is the load-bearing claim that distinguishes Cloudflare Tunnel from every 'run your own edge node' option in §3 and underwrites the §2 quadrant axis 'who owns the edge node'."

- title: "How Tailscale Works (Tailscale engineering blog)"
  type: vendor-docs
  url: "https://tailscale.com/blog/how-tailscale-works"
  quoted_passages:
    - "The node contacts the coordination server and leaves its public key and a note about where that node can currently be found, and what domain it's in."
    - "Remember that Tailscale private keys never leave the node where they were generated; that means there is never a way for a DERP server to decrypt your traffic."
    - "Tailscale uses several very advanced techniques, based on the Internet STUN and ICE standards, to make these connections work even though you wouldn't think it should be possible."
  relevance: "The canonical architectural writeup of Tailscale's three-part design: coordination server (control plane), DERP relays (fallback data plane when NAT traversal fails), and direct WireGuard tunnels between peers. Grounds the §3 mesh-overlay architecture for both Tailscale Funnel and Frank's Headscale + Hop setup, and justifies the §2 claim that 'mesh-overlay vs hub-and-spoke' is a real architectural axis, not a marketing distinction."

- title: "Tailscale Funnel docs"
  type: vendor-docs
  url: "https://tailscale.com/kb/1223/funnel"
  quoted_passages:
    - "Tailscale Funnel lets you route traffic from the broader internet to a local service running on a device in your Tailscale network (known as a tailnet)."
    - "The Tailscale server running on your device receives the encrypted request from the TCP proxy. It then terminates the TLS connection and passes the decrypted request to the local service you exposed through Funnel."
  relevance: "Vendor docs for the 'public exposure via the mesh' pattern — TLS is terminated on the device itself, not on Tailscale's edge, which is the architectural twin of Frank's choice but with Tailscale's coordination server instead of Frank's self-hosted Headscale. Source for the §3 mesh-overlay-as-edge architecture and the §6 decision-tree branch 'are you OK with vendor-controlled coordination?'."

- title: "Headscale README (juanfont/headscale on GitHub)"
  type: vendor-docs
  url: "https://github.com/juanfont/headscale"
  quoted_passages:
    - "An open source, self-hosted implementation of the Tailscale control server."
    - "Headscale aims to implement a self-hosted, open source alternative to the Tailscale control server."
    - "The control server works as an exchange point of Wireguard public keys for the nodes in the Tailscale network."
  relevance: "Definitive description of what Headscale actually is: a drop-in replacement for the Tailscale control server, which is the *coordination* layer (key exchange, ACLs, DNS) — not the data plane. The Tailscale clients themselves are unchanged. This is the load-bearing claim behind Frank's §5 architecture: Headscale on Hop is the control plane, the Tailscale DaemonSet on every Frank node is the data plane, and the WireGuard tunnels they establish are peer-to-peer."

- title: "Talos Linux on Hetzner Cloud (Sidero Labs docs)"
  type: vendor-docs
  url: "https://docs.siderolabs.com/talos/v1.10/platform-specific-installations/cloud-platforms/hetzner"
  quoted_passages:
    - "Hetzner Cloud provides Talos as Public ISO with the schematic id `ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515`"
    - "Once shutdown, simply create an image (snapshot) from the console. You can now use this snapshot to run Talos on the cloud."
    - "Bootstrap `etcd` on the first control plane node with: `talosctl --talosconfig talosconfig bootstrap`"
  relevance: "Vendor's own deployment guide for the exact path Frank takes to stand up Hop. Justifies the §5 narrative claim that 'Hop is a real Talos cluster, not a Helm chart on an Ubuntu droplet' — same OS, same image-factory pipeline, same `talosctl bootstrap` flow as Frank. The only architectural difference is the control plane: standalone talosctl with a combined patch file instead of Omni (Omni isn't reachable from a Hetzner public IP)."

- title: "awesome-tunneling — community catalogue of self-hosted exposure tools (anderspitman/awesome-tunneling)"
  type: postmortem
  url: "https://github.com/anderspitman/awesome-tunneling"
  quoted_passages:
    - "exposing a local webserver via a public domain name, with automatic HTTPS, even if behind a NAT or other restricted network."
    - "map X domain/subdomain to Y port on Z client, and proxy all connections to that domain."
  relevance: "A community-maintained catalogue of every tunneling tool the self-hosting world has invented, organised around the exact problem class Frank's Hop cluster solves: 'expose a local web service to the internet from behind NAT, with HTTPS'. The 'dream' section reads like the problem statement Frank wrote for itself in §1 — a useful sanity check that Paper 20's capability framing matches the practitioner consensus rather than a Frank-specific abstraction."

- title: "How NAT traversal works (Tailscale engineering blog)"
  type: paper
  url: "https://tailscale.com/blog/how-nat-traversal-works"
  quoted_passages:
    - "STUN relies on a simple observation: when you talk to a server on the internet from a NATed client, the server sees the public `ip:port` that your NAT device created for you."
    - "Both endpoints must attempt communication at roughly the same time, so that all the intermediate firewalls open up while both peers are still around."
    - "The algorithm is: try everything at once, and pick the best thing that works."
  relevance: "The closest thing the mesh-overlay world has to a foundational paper — a long-form technical writeup of STUN, UDP hole punching, and ICE as applied to WireGuard mesh VPNs. Grounds the §3 mesh-overlay architecture in actual NAT-traversal mechanics rather than hand-wavy 'it just works' marketing, and explains why the residential-ISP edge problem is hard enough to justify a dedicated paper category in the first place."

- title: "Cloudflare network — sub-50ms latency to 95% of internet users (cloudflare.com/network)"
  type: benchmark
  url: "https://www.cloudflare.com/network/"
  quoted_passages:
    - "Sub-50ms to 95% of users — 95% of the world's Internet-connected population is within 50 milliseconds of a Cloudflare data center — most are within 20ms."
    - "One of the world's largest networks — running every service in every data center for unmatched performance, security, and reliability."
  relevance: "Vendor-published latency claim that anchors the §4 'what scale changes' discussion — Cloudflare Tunnel's edge is closer to most users than any one-VPS edge can ever be, and the latency tax of running through a single Hetzner Falkenstein PoP is real. Sets the baseline against which Hop's single-region edge has to justify itself: own the data plane, accept the latency floor of one geographic location."

- title: "Frank — Hop cluster gotchas (hostPort + RollingUpdate, Headplane v0.5 ConfigMap, Tailscale DaemonSet kernel-mode, talosctl apply-config base-file pitfall)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/hop-gotchas.md"
  quoted_passages:
    - "Deployments using `hostPort` (e.g., Caddy on 80/443, Headscale STUN on 3478/UDP) must use `strategy: Recreate` — `RollingUpdate` deadlocks on a single-node cluster because the new pod can't bind ports while the old pod still holds them"
    - "Headplane v0.5+ requires a `config.yaml` ConfigMap — env vars alone are insufficient"
    - "Tailscale DaemonSet must run in kernel mode (`TS_USERSPACE=false`, `privileged: true`) for Caddy to see mesh source IPs"
    - "`talosctl apply-config --config-patch` patches the base file, not the running config — all patches must be combined in one invocation"
  relevance: "Frank's own dated postmortem registry for everything that broke on Hop in the first three weeks of operation. Each one-liner is the scar of a real outage or wasted day; each maps directly to a property of the 'separate single-node edge cluster' architecture rather than a Caddy or Headscale bug. Source for the §5 scar callouts and the §6 decision-tree branch on 'are you willing to run a single-node cluster as critical infrastructure?'."

- title: "inlets.dev — Self-hosted HTTP and TCP tunnels"
  type: vendor-docs
  url: "https://inlets.dev/"
  quoted_passages:
    - "Self-hosted HTTP and TCP tunnels with full control and privacy. Expose endpoints publicly, or tunnel customer services back to your SaaS."
    - "inlets exposes HTTP and TCP services without dragging whole subnets, hosts or teams into a VPN."
    - "inlets focuses on exposing specific services, self-hosting the data plane, and avoiding SaaS tunnel limits."
  relevance: "A fourth-vendor perspective: a tool that sits between Cloudflare Tunnel (zero infra) and Headscale (full mesh) — you still need a VPS, but you run only the tunnel daemon on it, not a coordination server or a cluster. Underwrites the §2 capability matrix row 'data-plane ownership' and provides the bridge in the §6 decision tree between the 'tunnel SaaS' branch and the 'edge cluster' branch."

- title: "Rancher Fleet — Multi-cluster GitOps engine (docs)"
  type: vendor-docs
  url: "https://fleet.rancher.io/0.15/"
  quoted_passages:
    - "Fleet is a container management and deployment engine designed to offer users more control on the local cluster and constant monitoring through GitOps."
    - "Fleet is fundamentally a set of Kubernetes custom resource definitions (CRDs) and controllers that manage GitOps for a single Kubernetes cluster or a large scale deployment of Kubernetes clusters."
  relevance: "The enterprise heavyweight in the §2 landscape: instead of treating the edge cluster as a separate platform with its own ArgoCD (Frank's choice), Fleet promises one logical GitOps surface spanning hub + edge + cloud. Justifies the §6 decision-tree branch 'managing one cluster or ten?' — Fleet starts paying for itself somewhere north of the Frank+Hop two-cluster mark, and below that it's overhead."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "clusters/hop/apps/caddy/manifests/"
  date: 2026-05-22
  demonstrates: "How a single Caddy Deployment on hostPort becomes the TLS terminator + reverse proxy for every Hop-served domain (headscale, headplane, blog, landing). Cloudflare DNS-01 challenge handles the Let's Encrypt issuance because there's no inbound HTTP-01 path through residential ISPs (also true here — Caddy is the only thing reachable on 80/443). Strategy must be Recreate; RollingUpdate deadlocks on the single-node cluster because the new pod can't bind hostPort 80/443 while the old one still holds them."

- kind: yaml
  path_or_url: "clusters/hop/apps/headscale/manifests/"
  date: 2026-05-22
  demonstrates: "How a separate-cluster mesh-overlay edge is assembled from primitives: Headscale as the coordination server, Tailscale DaemonSet running in kernel mode (TS_USERSPACE=false, privileged: true, hostNetwork: true) as the node-level tailnet client, MagicDNS split-DNS via Headscale's `extra_records` for mesh-only services (headplane.hop, entry.hop). Kernel-mode is non-negotiable: without it, Caddy sees every mesh request as coming from 127.0.0.1, which collapses the entire 'mesh-only services' boundary."

- kind: yaml
  path_or_url: "clusters/hop/packer/hetzner-talos.pkr.hcl"
  date: 2026-05-22
  demonstrates: "The Packer template that builds a Hetzner Cloud snapshot from the upstream Talos hcloud-amd64.raw.xz image. This is what makes Hop a real Talos cluster instead of a Helm chart on a generic Ubuntu droplet — same OS, same image-factory pipeline, same declarative-everything posture as Frank. The difference is talosctl standalone with combined patch files (not Omni — Omni isn't reachable from Hetzner)."

- kind: incident
  path_or_url: "agents/rules/hop-gotchas.md"
  date: 2026-05-22
  demonstrates: "The hostPort + RollingUpdate single-node deadlock: every Deployment that binds a hostPort on a single-node edge cluster must use `strategy: Recreate`, or it will wedge on every chart upgrade. This is the single-node-cluster blast radius made concrete — a property of the edge model itself, not a Caddy or Headscale bug. Three different Deployments (Caddy 80/443, Headscale STUN 3478/UDP, the early Headplane attempt) hit it in the first week."

- kind: incident
  path_or_url: "agents/rules/hop-gotchas.md"
  date: 2026-05-22
  demonstrates: "The Headplane v0.5+ silent env-var deprecation: the upstream rewrite at v0.5 quietly stopped accepting env-var configuration. A ConfigMap-mounted `config.yaml` with `config_path` pointing at the Headscale config and `config_strict: true` is now required. Non-strict mode works but logs scary warnings and forfeits upstream support. Cost ~half a day of 'why is Headplane in CrashLoopBackOff with no useful log line' before the upstream issue tracker yielded the answer."

- kind: incident
  path_or_url: "agents/rules/hop-gotchas.md"
  date: 2026-05-22
  demonstrates: "The `talosctl apply-config --config-patch` patches-the-base-file pitfall: `--config-patch` patches the on-disk base file in the talosconfig directory, NOT the running config in the cluster. All patches must be combined in one invocation. On Hop's combined-patch workflow this is load-bearing — a missed patch silently loses the change at the next reboot, and the only signal is 'the thing I patched yesterday is gone now'."

## Diagrams planned
- landscape:
    x_axis: "Zero infrastructure ↔ Own the edge node"
    y_axis: "Hub-and-spoke tunnel ↔ Mesh overlay"
    vendors_plotted: ["Cloudflare Tunnel", "ngrok", "Tailscale Funnel", "Headscale + tiny VPS (Hop)", "Multi-region cluster (Fleet)"]
- architecture_comparison:
    vendors: ["Cloudflare Tunnel (tunnel-back-to-origin shape)", "Tailscale Funnel + ngrok (mesh-overlay-as-edge shape)", "Headscale + Hop (dedicated-edge-cluster shape)"]
    note: "Exactly 3 architecture flowcharts in §3 — one per shape. 4th-5th vendors (ngrok, Fleet) get a one-sentence mention inside the matching shape."
- decision_tree:
    leaves: 4
    description: "Question: what sits at the edge between your residential ISP and the internet? Branches on (1) is it just one static blog or also auth-sensitive traffic, (2) is the edge node also load-bearing for the mesh control plane, (3) one cluster or many. Terminates in: Cloudflare Tunnel (zero infra, one blog), Tailscale Funnel (SaaS coordination, mesh OK), Headscale + tiny VPS (Frank's pick — own the data plane, one home cluster), Multi-region Fleet (north of 3 clusters, professional ops team)."

## Named gaps (≥1)
- "No public benchmark of 'Cloudflare Tunnel vs Headscale-mesh-to-tiny-VPS' steady-state latency and per-request cost exists at homelab scale. Vendor benchmarks measure SaaS-scale flows (Cloudflare's edge-to-edge p99) or enterprise-mesh-scale flows (Tailscale's DERP-vs-direct percentages on >100-node tailnets) — neither maps to the homelab case of 1 origin, 1 edge, 10 destinations, with the TLS-termination location and the auth-boundary location both treated as first-class variables. Without that benchmark, the 'edge tax' of running a separate VPS cluster is a feeling, not a number."

## Counter-arguments considered (≥1)
- "Cloudflare Tunnel is free, requires zero edge infrastructure, has a free TLS cert built in, sails through CG-NAT, and gets you a public URL in five minutes — why does Frank run a separate VPS at €5/month? The honest answers, in order of weight: (1) Cloudflare sees all traffic and decrypts TLS at their edge, which is a real property worth pricing in — the threat model of 'I trust Cloudflare with my blog' is fine, the threat model of 'I trust Cloudflare with my Headscale coordination traffic and my agent SSH sessions' is a different conversation; (2) the Hop cluster IS the Headscale coordination plane — pushing it behind Cloudflare Tunnel would re-create the chicken-and-egg of 'the mesh control plane depends on the mesh data plane'; (3) running an edge cluster teaches things Cloudflare's UI never can — Talos on Hetzner, Packer image builds, single-node-cluster blast radius, hostPort + RollingUpdate deadlocks, Tailscale DaemonSet kernel-mode requirements. Counter wins for the team whose only public surface is a static blog and a Headscale-replacement-as-SaaS choice; for Frank, owning the full data plane is the point."
