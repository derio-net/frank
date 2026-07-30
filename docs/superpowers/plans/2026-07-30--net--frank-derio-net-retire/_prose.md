# Retire frank.derio.net — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-06-01--net--frank-derio-net-retire-design.md`
**Layer:** net · **Repo:** derio-net/frank · **Branch:** `feat/complete-omni-cluster-domain-migration`

## Goal

Make `cluster.derio.net` the sole domain for in-cluster Frank services while keeping `omni.frank.derio.net` as the architectural exception. Migrate Kubernetes OIDC without rejecting active credentials, then remove the emergency `.frank` routes added during the raspi-omni outage.

## Rollout shape

This is three deployment PRs separated by manual evidence gates, followed by one evidence-only closeout PR:

1. Add callbacks and deploy dual-issuer structured authentication.
2. Cut every consumer over while retaining the old issuer and routes for eight hours.
3. Remove the old issuer, providers, routes, references, raspi edge configuration, and DNS.
4. Record post-deploy evidence and complete the net-layer documentation checklist.

Combining these changes would make ArgoCD, Authentik, DNS, and the control plane race toward a state that had never been observed. The staged form gives each cryptographic trust change a tested rollback boundary.

## Non-negotiable invariants

- `omni.frank.derio.net` remains reachable throughout and after the migration.
- `auth.frank.derio.net` discovery/JWKS and its in-cluster compatibility route remain healthy until the eight-hour old-token window closes.
- Structured `AuthenticationConfiguration` and legacy `--oidc-*` flags never coexist on kube-apiserver.
- The Omni service-account administration path is proven before changing kube-apiserver authentication.
- Cluster proxy providers are reused; legacy proxy providers are never rewritten into duplicate cluster objects.
- Headscale keeps the `frank.derio.net` split-DNS suffix for Omni.

## Acceptance rows

- `net-cluster-domain-canonical`
- `net-oidc-cutover-continuity`
- `net-legacy-domain-retired`
- `net-omni-domain-preserved`

## Manual operations

```yaml
# manual-operation
id: net-frank-domain-dual-issuer-rollout
layer: net
app: kube-apiserver
plan: docs/superpowers/plans/2026-07-30--net--frank-derio-net-retire
when: After PR 1 merges and additive Authentik callbacks are live.
why_manual: Omni ConfigPatch application changes kube-apiserver authentication on all three control-plane nodes and requires a live old-token continuity gate.
commands:
  - Verify the Omni service-account kubeconfig has cluster-admin access without Authentik.
  - Mint and retain a temporary old-issuer k8s-agent test credential in a local 0600 file.
  - Run omnictl apply -f patches/phase13-auth/omni-configpatch.yaml.
  - Inspect every kube-apiserver command and readiness endpoint.
verify:
  - All three kube-apiserver pods are Ready and /readyz?verbose passes.
  - Only --authentication-config is present; no --oidc-* flag remains.
  - Old-token TokenReview returns `authentik:<preferred_username>` and the same groups as before rollout.
  - Omni service-account administration still succeeds.
status: pending
```

```yaml
# manual-operation
id: net-frank-domain-overlap-gate
layer: net
app: authentik
plan: docs/superpowers/plans/2026-07-30--net--frank-derio-net-retire
when: After PR 2 merges and all consumers use cluster.derio.net.
why_manual: Browser OIDC round trips and the eight-hour access-token overlap require live credentials and elapsed wall-clock time.
commands:
  - Verify ArgoCD, Grafana, and Infisical OIDC logins on cluster.derio.net.
  - Verify cluster-host forward-auth for Longhorn, Hubble, Sympozium, and n8n.
  - Mint one cluster-issuer token and record T0 for the final old-issuer token.
  - Wait at least eight hours while auth.frank discovery, JWKS, DNS, and ingress remain healthy.
verify:
  - New-token TokenReview succeeds with the expected username and groups.
  - Old-token TokenReview succeeds before T0+8h and fails expired afterward.
  - Omni service-account administration succeeds throughout.
status: pending
```

```yaml
# manual-operation
id: net-frank-domain-final-retirement
layer: net
app: omni-traefik-dns
plan: docs/superpowers/plans/2026-07-30--net--frank-derio-net-retire
when: After PR 3 merges and the old test token is proven expired.
why_manual: Final Omni ConfigPatch application, raspi-omni Ansible configuration, and authoritative DNS changes are outside ArgoCD and can remove the remaining recovery hostname.
commands:
  - Run omnictl apply -f patches/phase13-auth/omni-configpatch.yaml.
  - Apply the Ansible change that leaves raspi-omni Traefik serving only Omni.
  - Remove every non-Omni frank.derio.net DNS record; retain omni.frank.derio.net.
  - Retain the Headscale frank.derio.net split resolver.
verify:
  - kube-apiserver trusts only auth.cluster.derio.net and cluster-token authentication succeeds.
  - Named legacy service hosts return NXDOMAIN or no route from LAN and mesh clients.
  - Omni UI and discovery return 200; unauthenticated :8100 returns 401.
  - raspi-omni Traefik and certificate renewal contain only Omni.
status: pending
```

## Rollback boundaries

- Before PR 2, re-apply the legacy ConfigPatch if dual issuer fails; no consumer has moved.
- During the overlap, revert PR 2 and keep both authenticators/routes; old and new credentials remain accepted.
- After PR 3, restore the old DNS/routes and re-apply the dual-issuer ConfigPatch only if the eight-hour expiry proof or cluster-token verification was wrong.

## Completion

Deployment is complete only when non-Omni `.frank` names are absent from source, ingress, Authentik, raspi-omni, and DNS; all cluster-host login paths work; Omni remains healthy; and all four acceptance rows contain truthful evidence.
