# Frank Cluster — Deployment Phases

## Machine Reference

| Machine ID | Hostname | IP | Role | Zone |
|-----------|----------|-----|------|------|
| `ce4d0d52-6c10-bdc9-746c-88aedd67681b` | mini-1 | 192.168.55.21 | control-plane | core |
| `6ea7c1c6-6ba6-b59d-c77a-88aedd676447` | mini-2 | 192.168.55.22 | control-plane | core |
| `d1f01c97-d17e-e3ef-12ee-88aedd6768b6` | mini-3 | 192.168.55.23 | control-plane | core |
| `03ff0210-04e0-05b0-ab06-300700080009` | gpu-1 | 192.168.55.31 | worker | ai-compute |
| `03de0294-0480-05ab-3106-410700080009` | pc-1 | 192.168.55.71 | worker | edge |
| `30303031-3030-3030-3662-353662376100` | raspi-1 | 192.168.55.41 | worker | edge |
| `30303031-3030-3030-3337-613762353000` | raspi-2 | 192.168.55.42 | worker | edge |

## Environment Setup

```bash
source .env          # kubectl, talosctl (KUBECONFIG + TALOSCONFIG)
source .env_devops   # omnictl (OMNI_ENDPOINT + OMNI_SERVICE_ACCOUNT_KEY)
```

## Phases

| Phase | Directory | Tools | Status |
|-------|-----------|-------|--------|
| [Phase 1: Node Config](phase1-node-config/) | `patches/phase1-node-config/` | omnictl | DONE |
| [Phase 2: Cilium CNI](phase2-cilium/) | `patches/phase2-cilium/` | omnictl + helm | DONE |
| [Phase 3: Longhorn Storage](phase3-longhorn/) | `patches/phase3-longhorn/` | omnictl + talosctl + helm | DONE |
| [Phase 4: GPU Stack](phase4-gpu/) | `patches/phase4-gpu/` | omnictl + helm | TODO |

## Rollback

Each phase README includes its own rollback instructions.
