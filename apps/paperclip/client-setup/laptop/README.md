# Paperclip — Client Setup

Operator-side configs for connecting to the **paperclip-shell** sidecar at `192.168.55.221`.

The sidecar is co-located with the upstream Paperclip web UI in a single Pod (see `../../manifests/deployment.yaml`). The upstream `paperclip` container is unmodified; the `paperclip-shell` container is a separate sidecar based on `agent-shell-base` that adds SSH+Mosh, a persistent home PVC, and a declarative install-on-boot inventory.

Cluster-side manifests live in `../../manifests/`. This directory captures everything *outside* the cluster you need to actually use the pod day-to-day.

```
client-setup/laptop/
├── ssh-config.snippet  → append to ~/.ssh/config
├── mosh-wrapper.sh     → e.g. ~/bin/paperclip-mosh, made executable
└── README.md           ← this file
```

## SSH

```bash
cat ssh-config.snippet >> ~/.ssh/config       # then edit the IdentityFile path
ssh paperclip                                 # uses the Host alias above
```

## Mosh

```bash
install -m 0755 mosh-wrapper.sh ~/bin/paperclip-mosh
paperclip-mosh                                # opens a mosh session into the sidecar
```

The wrapper pins mosh-server to UDP 60000–60015 — the same range the LoadBalancer Service publishes. The default range (60000–61000) would wander outside the published ports and the session would silently fail to handshake.

## SSH key rotation

Public keys live in the `paperclip-shell-ssh-keys` Secret, mounted read-only into the container at `/etc/ssh-keys`. SOPS-bootstrap pattern — see `secrets/paperclip/README.md` for the rotation procedure. (ESO via Infisical was on the original plan; we mirror the existing SOPS pattern used by `secure-agent-pod`'s `agent-ssh-keys` and `ruflo-shell-ssh-keys` instead.)

## Architecture context

Unlike `secure-agent-pod`, which splits SSH and mosh across two LB IPs (192.168.55.215 + 192.168.55.219), `paperclip-shell` consolidates both onto a single LB IP (192.168.55.221). Same shape as `ruflo-shell` (192.168.55.222).

The sidecar shares the Paperclip data PVC at `/paperclip` (read-write), so the operator can inspect or surgically edit Paperclip's persistent state from the shell. It does **not** share a process namespace with the `paperclip` container — `shareProcessNamespace: true` is incompatible with the `agent-shell-base` s6-overlay v3 init under `runAsNonRoot` (see deployment.yaml comment block for the trace).
