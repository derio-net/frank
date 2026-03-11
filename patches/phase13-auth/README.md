# Phase 13 — Authentication OIDC API Server Patch

Configures kube-apiserver to accept Authentik OIDC tokens for kubectl authentication.
Applied to all control-plane nodes via Omni.

## Files

- `oidc-apiserver.yaml` — kube-apiserver OIDC flags (issuer, client ID, claims)

## Application

Apply via Omni to the control-plane machine set. The patch triggers a rolling restart
of kube-apiserver on all control-plane nodes.
