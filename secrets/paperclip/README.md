# SOPS-encrypted bootstrap secrets for paperclip

Apply with: `sops --decrypt <file> | kubectl apply -f -`

Currently this directory holds:

- `paperclip-shell-ssh-keys.yaml` *(to be created on first deploy — see below)* — Secret in `paperclip-system` mounted read-only into the `paperclip-shell` container at `/etc/ssh-keys`. Same shape as `secrets/secure-agent-pod/`'s `agent-ssh-keys` and `secrets/ruflo/`'s `ruflo-shell-ssh-keys`.

## Why SOPS not ESO

The original Phase 2 plan called for an `ExternalSecret` reading SSH public keys from Infisical. Frank's existing pattern for SSH host/user keys is SOPS-bootstrap — `secure-agent-pod`'s `agent-ssh-keys` is a SOPS Secret applied out-of-band, and the sibling `ruflo` work picked up the same convention (`secrets/ruflo/`). We mirror that pattern here so the Deployment can reference a stable Secret name without bootstrapping ESO state.

## On first deploy

```bash
# 1. Generate a fresh keypair on your laptop (or reuse the one already
#    paired with secure-agent-pod / ruflo so a single private key opens
#    every shell sidecar).
ssh-keygen -t ed25519 -f ~/.ssh/paperclip -C "operator@paperclip"

# 2. Build a Secret manifest
kubectl create secret generic paperclip-shell-ssh-keys \
  --namespace=paperclip-system \
  --from-file=authorized_keys=<(cat ~/.ssh/id_rsa_raspi.pub) \
  --dry-run=client -o yaml > /tmp/paperclip-shell-ssh-keys.yaml

# 3. SOPS-encrypt + commit. `sops --encrypt` resolves recipients from
#    the repo-root .sops.yaml `path_regex` rules — no need to plumb the
#    age key by hand.
mv /tmp/paperclip-shell-ssh-keys.yaml secrets/paperclip/paperclip-shell-ssh-keys.yaml
sops --encrypt --in-place secrets/paperclip/paperclip-shell-ssh-keys.yaml
git add secrets/paperclip/paperclip-shell-ssh-keys.yaml

# 4. Apply once (subsequent rotations: re-encrypt + re-apply)
sops --decrypt secrets/paperclip/paperclip-shell-ssh-keys.yaml | kubectl apply -f -
```

The Deployment (`apps/paperclip/manifests/deployment.yaml`) marks the volume `optional: true`, so the pod still boots if the Secret is missing — sshd just won't accept any keys until the bootstrap runs.
