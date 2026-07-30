# Journal: 2026-07-30--net--frank-derio-net-retire

<!-- fr:journal kind=finding scope=plan id=oidc-stable-username-prefix created=2026-07-30T21:06:09 phase=1 state=fixed -->
### oidc-stable-username-prefix · finding [fixed] · Legacy username prefix is issuer-derived (phase 1)

Fixed in Phase 1: both authenticators map preferred_username with the explicit neutral authentik: prefix and groups with an empty prefix. The spec, manual gates, and runbook document the one-time username normalization; no RBAC User subjects exist.

<!-- fr:journal kind=finding scope=plan id=talos-authn-file-create created=2026-07-30T21:14:06 phase=1 state=fixed -->
### talos-authn-file-create · finding [fixed] · New Talos file cannot use overwrite (phase 1)

Fixed in Phase 1: the Omni payload and test use op=create for the new authn-config path, matching Talos v1.12 semantics and existing repo machine-file patches.

<!-- fr:journal kind=finding scope=plan id=removed-oidc-patch-doc-refs created=2026-07-30T21:21:41 phase=1 state=fixed -->
### removed-oidc-patch-doc-refs · finding [fixed] · Deleted patch remains named by operational docs (phase 1)

Fixed in Phase 1: the patch README, outage-era Traefik comment, and design now point to the authoritative Omni ConfigPatch.
