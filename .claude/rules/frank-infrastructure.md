## Frank Cluster Nodes

| Host | IP | Role | Zone | Key Hardware |
|------|-----|------|------|-------------|
| mini-1 | 192.168.55.21 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| mini-2 | 192.168.55.22 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| mini-3 | 192.168.55.23 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| gpu-1 | 192.168.55.31 | worker | AI Compute | i9, 128GB, RTX 5070 |
| pc-1 | 192.168.55.71 | worker | Edge | 64GB, general purpose |
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
| Authentik | 192.168.55.211 | Cilium L2 LoadBalancer (port 9000) |
| Paperclip | 192.168.55.212 | Cilium L2 LoadBalancer (port 3100) |
| ComfyUI | 192.168.55.213 | Cilium L2 LoadBalancer (port 8188) |
| GPU Switcher | 192.168.55.214 | Cilium L2 LoadBalancer (port 8080) |
| Kali Workstation | 192.168.55.215 | Cilium L2 LoadBalancer (port 22/SSH) |
