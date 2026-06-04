# SOPS-encrypted bootstrap secrets for hermes-agent-shell

Apply with: `sops --decrypt <file> | kubectl apply -f -`

This directory holds:

- `hermes-agent-shell-ssh-keys.yaml` *(created during the Phase 1 bootstrap —
  see below)* — Secret in `hermes-agent-shell` mounted read-only into the
  `hermes` container at `/etc/ssh-keys`. Same shape as
  `secrets/secure-agent-pod/`'s `agent-ssh-keys`,
  `secrets/paperclip/`'s `paperclip-shell-ssh-keys`, and
  `secrets/ruflo/`'s `ruflo-shell-ssh-keys`.

## Why SOPS not ESO

Frank's pattern for SSH user keys is SOPS-bootstrap applied out-of-band —
`secure-agent-pod`'s `agent-ssh-keys`, plus the `paperclip` / `ruflo` shells all
follow it. SOPS-encrypted secrets must NOT be ArgoCD-managed; the Deployment
references a stable Secret name and marks the volume `optional: true` so the pod
still boots if the Secret is missing — sshd just won't accept any keys until the
bootstrap runs.

## On first deploy (Phase 1)

```bash
# 1. Reuse the operator key already paired with the other shells (so one private
#    key opens every shell sidecar), or generate a fresh keypair. You only need
#    the PUBLIC key here.
#    ssh-keygen -t ed25519 -f ~/.ssh/hermes -C "operator@hermes"

# 2. Build a Secret manifest (namespace hermes-agent-shell, key authorized_keys).
kubectl create secret generic hermes-agent-shell-ssh-keys \
  --namespace=hermes-agent-shell \
  --from-file=authorized_keys=<path-to-operator.pub> \
  --dry-run=client -o yaml \
  > secrets/hermes-agent-shell/hermes-agent-shell-ssh-keys.yaml

# 3. SOPS-encrypt in place + commit. Recipients resolve from the repo-root
#    .sops.yaml path_regex (encrypted_regex ^(data|stringData)$).
sops --encrypt --in-place secrets/hermes-agent-shell/hermes-agent-shell-ssh-keys.yaml
git add secrets/hermes-agent-shell/hermes-agent-shell-ssh-keys.yaml

# 4. Apply ONCE — but only after the namespace exists. The hermes-agent-shell
#    namespace is created by ArgoCD when the app first syncs (Phase 2), so apply
#    this secret after that sync (Phase 2 / T2). Subsequent rotations: re-encrypt
#    + re-apply, then restart the pod (cont-init.d/30-authorized-keys copies the
#    key only at boot).
sops --decrypt secrets/hermes-agent-shell/hermes-agent-shell-ssh-keys.yaml | kubectl apply -f -
```

## LiteLLM virtual key (the other Phase 1 bootstrap)

`OPENAI_API_KEY` is sourced via ESO from Infisical entry `HERMES_LITELLM_KEY`
(see `apps/hermes-agent-shell/manifests/externalsecret-llm.yaml`). Mint a
dedicated LiteLLM virtual key for the hermes agent and store it in Infisical as
`HERMES_LITELLM_KEY` — that is a separate `# manual-operation` (see the plan and
`docs/runbooks/manual-operations.yaml`), not a SOPS secret in this directory.
