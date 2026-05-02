# SOPS-encrypted bootstrap secrets for ruflo

Apply with: `sops --decrypt <file> | kubectl apply -f -`

Currently this directory holds:

- `ruflo-shell-ssh-keys.yaml` *(to be created on first deploy — see below)* — Secret in `ruflo-system` mounted read-only into the `ruflo-shell` container at `/etc/ssh-keys`. Same shape as `secrets/secure-agent-pod/`'s `agent-ssh-keys` (which is referenced from `apps/secure-agent-pod/manifests/deployment.yaml`).

## Why SOPS not ESO

The original Phase 2 plan called for an `ExternalSecret` reading SSH public keys from Infisical. Frank's existing pattern for SSH host/user keys is SOPS-bootstrap — `secure-agent-pod`'s `agent-ssh-keys` is a SOPS Secret applied out-of-band. We mirror that pattern here so the Deployment can reference a stable Secret name without bootstrapping ESO state.

## On first deploy

```bash
# 1. Generate a fresh keypair on your laptop (or use an existing one)
ssh-keygen -t ed25519 -f ~/.ssh/ruflo -C "operator@ruflo"

# 2. Build a Secret manifest
kubectl create secret generic ruflo-shell-ssh-keys \
  --namespace=ruflo-system \
  --from-file=authorized_keys=<(cat ~/.ssh/ruflo.pub) \
  --dry-run=client -o yaml > /tmp/ruflo-shell-ssh-keys.yaml

# 3. SOPS-encrypt + commit
sops --encrypt --age "$(yq '.creation_rules[0].age' .sops.yaml)" \
  /tmp/ruflo-shell-ssh-keys.yaml > secrets/ruflo/ruflo-shell-ssh-keys.yaml
git add secrets/ruflo/ruflo-shell-ssh-keys.yaml

# 4. Apply once (subsequent rotations: re-encrypt + re-apply)
sops --decrypt secrets/ruflo/ruflo-shell-ssh-keys.yaml | kubectl apply -f -
```

The Deployment (`apps/ruflo/manifests/deployment.yaml`) marks the volume `optional: true`, so the pod still boots if the Secret is missing — sshd just won't accept any keys until the bootstrap runs.
