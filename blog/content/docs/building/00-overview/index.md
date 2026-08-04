---
title: "Frank, the Talos Cluster: Overview & Roadmap"
date: 2026-03-06
draft: false
tags: ["overview", "roadmap"]
summary: "The index to Frank, the Talos Cluster — an AI-hybrid Kubernetes homelab. Technology roadmap, capabilities, cluster state, and the commands to check any of it."
weight: 1
reader_goal: "Understand Frank's capability layers and how they map to hardware zones"
diataxis: reference
last_updated: 2026-08-01
---

The **Frank, the Talos Cluster** series is a walkthrough of building an AI-hybrid Kubernetes homelab from scratch, one layer per post. This post is not part of that walkthrough. It is the index to it: the roadmap, the capability map, the hardware, and a set of commands for checking whether any of it is still true.

## Roadmap

{{< roadmap >}}

## Technology → Capability Map

| Technology | Capabilities Unlocked |
|------------|----------------------|
| **Talos Linux + Omni** | Immutable OS, declarative machine config, secure bootstrap |
| **Cilium (eBPF)** | Kube-proxy replacement, L2 LoadBalancer, Hubble UI (`192.168.55.202`) |
| **Longhorn** | Distributed block storage, GPU-local StorageClass, 3-replica {{< abbr "HA" >}}, UI (`192.168.55.201`) |
| **ArgoCD** | GitOps, App-of-Apps, self-healing, drift detection |
| **NVIDIA GPU Operator** | GPU scheduling, AI/ML workloads, container toolkit |
| **Intel GPU {{< abbr "DRA" >}} Driver** | iGPU sharing via DRA, namespace-scoped GPU access |
| **OpenRGB** | LED control from K8s (just for fun) |
| **VictoriaMetrics + Grafana** | Cluster-wide metrics, alerting, dashboards, Grafana UI (`192.168.55.203`) |
| **VictoriaLogs + Fluent Bit** | Centralised log aggregation and querying |
| **Longhorn Backup + Cloudflare R2** | {{< abbr "PVC" >}} backup/restore, daily + weekly schedules, offsite storage |
| **Infisical + External Secrets Operator** | Secret management with audit trail, ExternalSecret → K8s Secret sync (`192.168.55.204`) |
| **Ollama** | Local {{< abbr "LLM" >}} inference on gpu-1's RTX 5070 Ti (16GB). Six base models as of 2026-07-29: Mistral Small 3.2 24B (default), Gemma 4 12B and Qwen2.5-VL 7B (multimodal), Qwen2.5-Coder 14B, Qwen3 14B (reasoning), Qwen3.6 35B-A3B (MoE, partial CPU offload). Lineup lives in `apps/litellm/values.yaml` |
| **LiteLLM** | Unified OpenAI-compatible gateway, virtual keys, spend tracking (`192.168.55.206`). Local-only since 2026-06-04 — no free-tier cloud aliases |
| **Sympozium** | Kubernetes-native agentic control plane — agent=Pod, policy={{< abbr "CRD" >}}, execution=Job (`192.168.55.207`) |
| **cert-manager** | Automated {{< abbr "TLS" >}} certificate lifecycle for webhooks and internal services |
| **Authentik** | Unified {{< abbr "SSO" >}} — {{< abbr "OIDC" >}} for ArgoCD, Grafana, Infisical; forward-auth proxy for 18 routes incl. Longhorn, Hubble, Tekton Dashboard (`192.168.55.211`) |
| **vCluster** | Virtual K8s clusters inside Frank — disposable sandboxes with own API server, resource quotas, network policies |
| **Paperclip** | AI agent orchestrator — virtual companies with org charts, budgets, and delegation chains; complements Sympozium (`192.168.55.212`) |
| **ComfyUI** | Diffusion model serving — video (LTX-2.3), image (SDXL), audio (Stable Audio), node-based workflow editor (`192.168.55.213`) |
| **GPU Switcher** | Custom Go dashboard for GPU time-sharing — one-click switching between Ollama and ComfyUI (`192.168.55.214`) |
| **Hop (Hetzner Edge)** | Public-facing single-node Talos cluster — Headscale mesh, Caddy reverse proxy, blog hosting, split-DNS |
| **Headscale + Tailscale** | WireGuard mesh networking — remote homelab access from any device, MagicDNS for split-DNS |
| **Caddy** | Automatic TLS (Cloudflare DNS challenge), public/mesh routing, path rewriting |
| **Secure Agent Pod** | Hardened non-root coding agent workstation — Cilium egress, dropped capabilities, VibeKanban orchestration, SSH (`192.168.55.215`) + UI (`192.168.55.218`) |
| **Argo Rollouts** | Progressive delivery — canary (Cilium traffic splitting + VictoriaMetrics analysis) and blue-green (preview + atomic cutover) |
| **n8n** | Per-user workflow automation — 400+ integrations, visual node editor, webhook triggers, Authentik forward-auth (`192.168.55.216`) |
| **Blackbox Exporter + Pushgateway** | Feature-level health monitoring — HTTP endpoint probes, cron heartbeat ingestion, Grafana alerting to Telegram |
| **Health Bridge** | Grafana alert → GitHub Project lifecycle state bridge — automatic degraded/dead/healthy transitions, issue comments, bug issue creation |
| **Traefik (in-cluster)** | In-cluster ingress controller, wildcard TLS (`*.cluster.derio.net`), {{< abbr "ACME" >}} via Cloudflare DNS-01, Authentik forward-auth (`192.168.55.220`) |
| **{{< abbr "VK" >}} Remote (self-hosted)** | Self-hosted VibeKanban kanban API — PostgreSQL 16, ElectricSQL real-time sync, Rust/Axum server (`vk.cluster.derio.net`). Local {{< abbr "JWT" >}} auth behind an IP allowlist, no forward-auth |
| **VK Relay** | WebSocket relay sidecar tunneling browser API calls to local VK agent server via yamux multiplexing, {{< abbr "SPAKE2" >}} pairing, Ed25519 request signing |
| **gethomepage.dev** | Cluster dashboard at `master.cluster.derio.net` — service catalog with HTTP health indicators, custom bookmarks |
| **Gitea** | Self-hosted git forge with GitHub pull-mirror, Authentik OIDC SSO (`192.168.55.209`) |
| **Tekton** | K8s-native CI/CD pipelines — webhook-driven clone, test, build, sign, report status on pc-1 |
| **Zot** | {{< abbr "OCI" >}} container/artifact registry with cert-manager TLS and cosign image signing (`192.168.55.210`) |
| **agent-images** | Shared base image + per-pod children repo — `agent-base` toolchain + `secure-agent-kali` / `vk-local` children, matrix CI, cross-repo `repository_dispatch`, lockstep bumper PR |
| **Ruflo (claude-flow + ruvocal)** | Swarm-style AI orchestrator — hybrid pod (ruvocal {{< abbr "SSR" >}} + agent-shell-base sidecar), LiteLLM-only egress, SSH+Mosh shell on `192.168.55.222`, web UI at `ruflo.cluster.derio.net` |
| **The Frank Papers** | Third blog series — research-grade landscape reviews framed as decisions; dossier gate (`validate-dossier.py` + pre-commit hook), Mermaid Frank theme, five `papers/` shortcodes, render-time cross-series backlinks. **Prologue published 2026-05-18:** [Why Run Your Own Cluster in 2026?](/docs/papers/00-why-homelab-in-2026) |
| **GoatCounter** | Cookieless blog analytics — public beacon via Hop's Caddy at `counter.derio.net`, mesh-only admin at `counter.cluster.derio.net` with Authentik forward-auth (`192.168.55.224`) |
| **CrowdSec + caddy-crowdsec-bouncer** | Edge HTTP security — agent tails Caddy logs on Hop, Caddy bouncer enforces decisions locally without round-tripping to Frank |
| **Falco (modern_ebpf) + Falcosidekick** | Container runtime security on Talos — Loki output to VictoriaLogs (Loki push protocol) + direct Telegram for `priority:critical` |
| **alert-agent** | Autonomous `claude` agent on multi-agent-shell — daily blog digest, Grafana-alert triage, traffic-surge detection, inbound Telegram Q&A. HTTP-only, no kube credential; deterministic facts from a `frank-facts` CLI. Replaced the FastAPI `ai-alert-helper` on 2026-06-16 |
| **AWX** | Ansible automation controller — the imperative arm reaching non-Talos home-lab hosts over SSH; operator + `AWX` {{< abbr "CR" >}} (two-layer reconcile), native OIDC SSO via Authentik, Gitea-backed Job Templates |
| **hermes (Nous Research)** | Terminal-native agent CLI in a dedicated `agent-shell-base` pod on gpu-1 — {{< abbr "BYOK" >}} to LiteLLM (provider pinned via `config.yaml` mapping), profile.d shim defeating the sshd env-scrub, SSH+Mosh on `192.168.55.226` |
| **metrics-server** | Aggregated resource Metrics API (`metrics.k8s.io`) on Talos — restores `kubectl top nodes/pods` and unblocks CPU/memory {{< abbr "HPA" >}}; `--kubelet-insecure-tls` for self-signed kubelet certs. Custom/external metrics deferred to a VM-backed prometheus-adapter |

## Cluster State

Four zones, lettered A to D. **Zone A** is management and has no row here on purpose: it lives outside the cluster, so it has no node to appear as. The other three are the cluster.

| Node | Zone | Role | Hardware |
|------|------|------|----------|
| mini-1/2/3 | B — Core HA | Control-plane + Worker | Intel Ultra 5, 64GB RAM, 1TB NVMe, Arc iGPU |
| gpu-1 | C — AI Compute | Worker | i9, 128GB RAM, RTX 5070 Ti (16GB GDDR7), 2x4TB SSD |
| pc-1 | D — Edge | Worker | Legacy desktop, 64GB SSD + 3x HDD |
| raspi-1/2 | D — Edge | Worker | Raspberry Pi 4, 32GB SD |

## Verify this page against a live cluster

Everything in the Technology → Capability Map arrives as an ArgoCD Application, so the table is checkable rather than a claim you have to take on trust. The `kubectl` lines below want a kubeconfig for a cluster; the `grep` lines want a clone of [derio-net/frank](https://github.com/derio-net/frank) and run from its root.

**Every number below was captured on 2026-07-29** and will have moved since. The command is the durable part; the digits are a sample so you can tell whether you typed it right. Start with the count:

```console
$ kubectl -n argocd get applications --no-headers | wc -l
      69
```

Sixty-eight of those are templated by the App-of-Apps. The sixty-ninth is `root` itself, applied by hand once at bootstrap, because at that moment nothing exists yet to apply it:

```console
$ grep -l 'kind: Application' apps/root/templates/*.yaml | wc -l
      68
```

That arithmetic is the whole GitOps claim in one line. When the two numbers stop agreeing, something on the cluster was made outside git.

Existing and converged are different questions, so ask the second one separately:

```console
$ kubectl -n argocd get applications \
    -o jsonpath='{range .items[*]}{.status.sync.status}{" "}{.status.health.status}{"\n"}{end}' \
  | sort | uniq -c | sort -rn
  62 Synced Healthy
   5 OutOfSync Healthy
   1 Synced Suspended
   1 OutOfSync Missing
```

Sixty-two green out of sixty-nine, on an ordinary afternoon. `Suspended` is a canary parked at a manual promotion gate — Argo Rollouts doing its job, not a fault. `OutOfSync` is live state disagreeing with git. Neither is an emergency, and a cluster reporting all green all the time is usually one nobody is asking hard questions of.

The roadmap at the top is numbered by published post. The layer codes that plan filenames and commit messages use are a separate registry:

```console
$ grep -c '^  - code:' docs/layers.yaml
22
```

Twenty-one numbered capability layers, plus `repo` for meta-work that is not a cluster capability at all. The two sequences match through Layer 17 and diverge after it, because layers stopped shipping in the order they were planned. If you are looking for the post that covers a layer, follow the roadmap; if you are looking for the plan that built it, follow the code.

## Missteps

Three forks where the obvious choice was the wrong one.

| The fork | Why the obvious branch was wrong | What Frank does now | Evidence |
|----------|----------------------------------|---------------------|----------|
| **Maintain the index by hand, or derive it from the pages** | Hand-maintained indexes drift silently — nothing fails when you forget, and reordering means editing every entry | Layer registry in `docs/layers.yaml`; `{{</* roadmap */>}}` and `{{</* series-index */>}}` derive their cards from page frontmatter | `d7678b9e`, `cfb7dd1e` |
| **One series or two** | Build narrative and runbook have different readers and different half-lives. A build post is a dated story and should age; a runbook has to stay true | Split into `building/` and `operating/`, cross-linked at render time | `7f5ff73f`, `fc274975` |
| **`relref` or a plain path for cross-post links** | `relref` validates targets at build time, but a missing `/docs/` prefix is not a warning — it is `REF_NOT_FOUND` and a dead `build-pages` job | Prefix every `relref` with the full section path; escape any shortcode you are only quoting as `{{</*` … `*/>}}` | `2840cce7` |
