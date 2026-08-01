# Phase 13 — Kubernetes API Server Authentication

Configures kube-apiserver to accept Authentik OIDC tokens for kubectl authentication.
Applied to all control-plane nodes via Omni.

## Files

- `authn-config.yaml` — reviewable Kubernetes structured-authentication source
- `omni-configpatch.yaml` — authoritative Omni ConfigPatch that writes and mounts
  the authentication file, then enables `--authentication-config`

## Application

Apply `omni-configpatch.yaml` via Omni to the control-plane machine set. The patch
triggers a rolling restart of kube-apiserver on all control-plane nodes.
