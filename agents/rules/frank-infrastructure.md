## Frank Cluster Nodes

| Host | IP | Role | Zone | Key Hardware |
|------|-----|------|------|-------------|
| mini-1 | 192.168.55.21 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| mini-2 | 192.168.55.22 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| mini-3 | 192.168.55.23 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| gpu-1 | 192.168.55.31 | worker | AI Compute | i9, 128GB, RTX 5070 Ti (16GB GDDR7) |
| pc-1 | 192.168.55.71 | worker | Edge | 32GB, general purpose (Z77/i5-3570K, 2013 BIOS — see `docs/investigations/2026-05-11--hw--pc-1-reboot-investigation.md`) |
| raspi-1 | 192.168.55.41 | worker | Edge | RPi 4, low-power |
| raspi-2 | 192.168.55.42 | worker | Edge | RPi 4, low-power |

## Frank Cluster Services

| Service | IP | Exposed Via |
|---------|-----|-------------|
| ArgoCD | 192.168.55.200 | Cilium L2 LoadBalancer |
| Longhorn UI | 192.168.55.201 | Cilium L2 LoadBalancer |
| Hubble UI | 192.168.55.202 | Cilium L2 LoadBalancer |
| Grafana | 192.168.55.203 | Cilium L2 LoadBalancer |
| Infisical | 192.168.55.204 | Cilium L2 LoadBalancer |
| LiteLLM Gateway | 192.168.55.206 | Cilium L2 LoadBalancer |
| Sympozium Web UI | 192.168.55.207 | Cilium L2 LoadBalancer |
| Gitea | 192.168.55.209 | Cilium L2 LoadBalancer (port 3000 HTTP, 2222 SSH) |
| Zot OCI Registry | 192.168.55.210 | Cilium L2 LoadBalancer (port 5000 HTTPS) |
| Authentik | 192.168.55.211 | Cilium L2 LoadBalancer (port 9000) |
| Paperclip | 192.168.55.212 | Cilium L2 LoadBalancer (port 3100) |
| ComfyUI | 192.168.55.213 | Cilium L2 LoadBalancer (port 8188) |
| GPU Switcher | 192.168.55.214 | Cilium L2 LoadBalancer (port 8080) |
| Secure Agent Pod (SSH) | 192.168.55.215 | Cilium L2 LoadBalancer (port 22/SSH) |
| n8n-01 | 192.168.55.216 | Cilium L2 LoadBalancer (port 5678) |
| Tekton Dashboard | 192.168.55.217 | Cilium L2 LoadBalancer (port 9097) |
| Secure Agent Pod (VibeKanban) | 192.168.55.218 | Cilium L2 LoadBalancer (port 8081) |
| Secure Agent Pod (Mosh) | 192.168.55.219 | Cilium L2 LoadBalancer (UDP 60000-60015) |
| Traefik Ingress | 192.168.55.220 | Cilium L2 LoadBalancer |
| Paperclip Shell (SSH+Mosh) | 192.168.55.221 | Cilium L2 LoadBalancer (port 22/SSH, UDP 60000-60015/Mosh) |
| Ruflo Web UI | (via Traefik) | IngressRoute (ruflo.cluster.derio.net) |
| Ruflo Shell (SSH+Mosh) | 192.168.55.222 | Cilium L2 LoadBalancer (port 22/SSH, UDP 60016-60031/Mosh) |
| GitHub webhook receiver (Tekton github-listener) | 192.168.55.223 | Cilium L2 LoadBalancer (port 8080) |
| GoatCounter | 192.168.55.224 | Cilium L2 LoadBalancer (port 8080, public ingest via Hop) |
| VictoriaLogs (LB) | 192.168.55.225 | Cilium L2 LoadBalancer (port 9428, cross-cluster ingest from Hop) |
| Homepage | (via Traefik) | IngressRoute (master.cluster.derio.net) |
