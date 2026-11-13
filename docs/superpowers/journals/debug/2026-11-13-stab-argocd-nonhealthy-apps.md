<!-- fr:journal-schema=4 -->
# Journal: 2026-11-13-stab-argocd-nonhealthy-apps

<!-- fr:journal kind=repro scope=debug id=ea2755d72123 created=2026-11-13T22:58:46+00:00 -->
### ea2755d72123 · repro · Non-healthy ArgoCD apps on Frank

Triage report found paperclip (sync fails image: Required value since 2026-09-12), argocd-extras Degraded (repo-runs-fr ES), cnc-prod (PreSync deadlock), and churn on infisical/staging-gate/cnc-staging-host. Live paperclip Deployment still runs paperclip:sha-8e6edcd + paperclip-shell + hermes-init; git wants single container sha-d554c47.

<!-- fr:journal kind=root-cause scope=debug id=3b9471b89b64 created=2026-11-13T22:58:49+00:00 -->
### 3b9471b89b64 · root-cause · paperclip: stale hand-apply field manager; backlog includes an IMAGE bump

Same shape as frank#827. NOT repaired: pending sync moves image sha-8e6edcd -> sha-d554c47 (Drizzle migrations auto-run on boot; snapshot the Postgres PVC first), removes the paperclip-shell sidecar and hermes-init, adds PAPERCLIP_ANNOUNCEMENTS_ENABLED=false, a Service LB change, and leaves 8 prune:false orphans. Operator decision per brief.
