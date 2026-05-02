# Ruflo — Client Setup

Operator-side configs for connecting to the **ruflo-shell** sidecar at `192.168.55.222`.

Cluster-side manifests live in `../../manifests/`. This directory captures everything *outside* the cluster you need to actually use the pod day-to-day.

```
client-setup/laptop/
├── ssh-config.snippet  → append to ~/.ssh/config
├── mosh-wrapper.sh     → e.g. ~/bin/ruflo-mosh, made executable
└── README.md           ← this file
```

## SSH

```bash
cat ssh-config.snippet >> ~/.ssh/config       # then edit the IdentityFile path
ssh ruflo                                     # uses the Host alias above
```

## Mosh

```bash
install -m 0755 mosh-wrapper.sh ~/bin/ruflo-mosh
ruflo-mosh                                    # opens a mosh session into the sidecar
```

The wrapper pins mosh-server to UDP 60016–60031 — the same range the LoadBalancer Service publishes. The default range (60000–61000) would wander outside the published ports and the session would silently fail to handshake.

## SSH key rotation

Public keys live in the `ruflo-shell-ssh-keys` Secret, mounted read-only into the container at `/etc/ssh-keys`. Same SOPS-bootstrap pattern as `secure-agent-pod`'s `agent-ssh-keys` Secret — see `secrets/ruflo/README.md` for the rotation procedure. (ESO via Infisical was on the original plan; we mirror the existing SOPS pattern instead because the analogous shell-pod secret on `secure-agent-pod` is also SOPS-bootstrap.)
