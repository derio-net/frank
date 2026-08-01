# Journal: 2026-08-01-authentik-outpost-canonical-host

<!-- fr:journal kind=repro scope=debug id=cluster-forward-auth-redirects-legacy-host created=2026-08-01T16:25:44 phase=4 -->
### cluster-forward-auth-redirects-legacy-host · repro · Cluster forward-auth redirects to legacy Authentik host (phase 4)

After PR #743 deployed, a browser request to https://grafana.cluster.derio.net entered the Grafana (cluster) proxy provider but redirected to https://auth.frank.derio.net/if/flow/default-authentication-flow/. This violates Phase 4's no-non-Omni-frank redirect gate even though the Authentik server and worker deployments both expose AUTHENTIK_HOST=https://auth.cluster.derio.net.

<!-- fr:journal kind=root-cause scope=debug id=embedded-outpost-host-is-persisted created=2026-08-01T16:25:49 phase=4 -->
### embedded-outpost-host-is-persisted · root-cause · Embedded outpost retains a database-backed authentik_host (phase 4)

Live ORM inspection showed the embedded outpost config still has authentik_host=https://auth.frank.derio.net. Traefik's middleware correctly calls the in-cluster authentik-server Service and the Grafana (cluster) provider correctly owns https://grafana.cluster.derio.net. Updating the pod-level AUTHENTIK_HOST rolls Authentik but does not rewrite the persisted Outpost.config value used to construct browser redirects.

<!-- fr:journal kind=finding scope=debug id=embedded-outpost-host-declared created=2026-08-01T16:31:25 phase=4 state=fixed -->
### embedded-outpost-host-declared · finding [fixed] · Cluster blueprint declares the embedded outpost browser host (phase 4)

Added an authentik_outposts.outpost entry identified by name that sets only config.authentik_host and config.authentik_host_browser to https://auth.cluster.derio.net. The providers relation is deliberately omitted, so Authentik state=present reconciliation leaves all existing outpost provider assignments unchanged. The failing regression now passes; focused suite 6 passed and full suite 369 passed, 1 xfailed.
