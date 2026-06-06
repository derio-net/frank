# The Frank Papers — Paper 20: Edge Clusters & Public Exposure

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Complete (2026-05-22) — Paper 20 draft on branch paper-20; PR open for human review.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 02, 04,
06, 07, 09, 10, 11, 14, 17 published or in flight.

Paper 20 is the last Paper to land in the Phase-1 publish order: 2400–4200
words, the standard skeleton (§1 capability → §2 landscape → §3 architecture
per vendor → §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap),
the edge-cluster companion to the public exposure layer Frank now runs in
production. The question is not *can the internet reach my services* (every
tunnel does that), it is *what edge do you put between a residential ISP
and the cluster, and what does a separate VPS cluster actually buy that a
tunnel doesn't?*

The capability question is: *your home cluster is behind a residential
ISP — CG-NAT possible, dynamic IPv4, no inbound 80/443. The internet wants
to reach a subset of its services (a blog, a status page, a remote-access
control plane). What sits at the edge, who terminates TLS, and where does
the auth boundary live?* The vendor space splits along two axes: whether
you run an edge node at all (zero-infra tunnels vs. a real VPS) and
whether the data plane is mesh-overlay or hub-and-spoke. Five candidates
make the landscape, with **Hetzner CX23 + Talos + Headscale mesh + Caddy
reverse proxy** as Frank's case study — a separate single-node Talos
cluster called Hop, sitting at €5/month and terminating its own TLS via
Cloudflare DNS-01.

The scars are the point. The hostPort + RollingUpdate deadlock that
guarantees a single-node edge cluster will wedge on any port-binding
chart unless every Deployment opts into `strategy: Recreate`. The
Headplane v0.5 ConfigMap requirement, after the upstream rewrite quietly
forfeited env-var configuration. The Tailscale DaemonSet kernel-mode +
hostNetwork + privileged trio required so the reverse proxy can see mesh
source IPs at all. The `talosctl apply-config --config-patch` patching-
the-base-file pitfall that ate a Talos config rebase. The Cilium 1.17
FQDN DNS-proxy init lesson — borrowed from Frank because Hop doesn't run
Cilium, but informs the §6 decision on whether you want CNI complexity at
the edge in the first place. These aren't decorations on the §5 narrative —
they're why the §6 decision tree has the leaves it does.

## Phase 1: Dossier construction

Five vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on the absence of an apples-to-apples
"homelab edge-cost benchmark" (Cloudflare Tunnel steady-state latency vs.
mesh-overlay-to-VPS at residential-ISP scale, with TLS termination
location priced in), and the counter-argument that for a homelab serving
one blog and one status page, Cloudflare Tunnel is free, requires zero
edge infrastructure, gives a free TLS cert, and the €5/month VPS is
pretextual. Parallel subagents per vendor are appropriate — one each for
Cloudflare Tunnel, Tailscale Funnel, ngrok, Headscale + tiny VPS (Frank's
choice), and full multi-region cluster (Rancher Fleet across cloud + on-
prem) — with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"Cloudflare Tunnel is free,
requires zero edge infrastructure, and has a free TLS cert built in —
why does Frank run a separate VPS at €5/month?"* Same shape as Paper 09's
"SOPS+age in Git is enough for solo devs" applied to the edge-exposure
capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language (tunnel-back-to-origin vs mesh-overlay vs dedicated-edge-cluster)
- §4 What scale changes (300–600 words) + benchmark callouts (tunnel concurrency at free tier, mesh peer-count fan-out, single-node blast radius when the edge IS the cluster)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (hostPort + RollingUpdate deadlock, Headplane v0.5 config.yaml, Tailscale DaemonSet kernel-mode for source-IP visibility)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank standing at a coastline with a lighthouse and a
small remote outpost in the distance, weighing whether to bridge the
channel by tunnel or by ferry. Thoughtful expression, thin black tie,
round reading glasses. The visual metaphor is *the channel between
private and public, and whether you cross it with someone else's tunnel
or your own boat*. Mermaid diagrams: §1 stack position, §2 landscape
(quadrantChart) + capability matrix, §3 three-to-five architecture
flowcharts, §6 decision tree. Optional Caddy access-log screenshot or
Headscale netmap screenshot captured live from Hop. Cluster-side captures
may be deferred with `-TODO.png` placeholders.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 17-public-edge and
Operating 11-public-edge, update README if relevant, set plan status to
Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
