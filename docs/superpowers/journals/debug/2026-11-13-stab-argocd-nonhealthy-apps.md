<!-- fr:journal-schema=4 -->
# Journal: 2026-11-13-stab-argocd-nonhealthy-apps

<!-- fr:journal kind=repro scope=debug id=ea2755d72123 created=2026-11-13T22:58:46+00:00 -->
### ea2755d72123 · repro · Non-healthy ArgoCD apps on Frank

Triage report found paperclip (sync fails image: Required value since 2026-09-12), argocd-extras Degraded (repo-runs-fr ES), cnc-prod (PreSync deadlock), and churn on infisical/staging-gate/cnc-staging-host. Live paperclip Deployment still runs paperclip:sha-8e6edcd + paperclip-shell + hermes-init; git wants single container sha-d554c47.

<!-- fr:journal kind=root-cause scope=debug id=3b9471b89b64 created=2026-11-13T22:58:49+00:00 -->
### 3b9471b89b64 · root-cause · paperclip: stale hand-apply field manager; backlog includes an IMAGE bump

Same shape as frank#827. NOT repaired: pending sync moves image sha-8e6edcd -> sha-d554c47 (Drizzle migrations auto-run on boot; snapshot the Postgres PVC first), removes the paperclip-shell sidecar and hermes-init, adds PAPERCLIP_ANNOUNCEMENTS_ENABLED=false, a Service LB change, and leaves 8 prune:false orphans. Operator decision per brief.

<!-- fr:journal kind=root-cause scope=debug id=738c81ada986 created=2026-11-13T22:58:53+00:00 -->
### 738c81ada986 · root-cause · cnc-prod: PreSync hook mounts a PVC only the Sync phase creates

snapshot-pvc.yaml was a plain resource in the same app; PreSync runs first so the pod stayed Pending. Moved the PVC to cnc-prod-db (wave 0), not a hook (hook resources are deleted before recreate and would wipe dumps).

<!-- fr:journal kind=finding scope=debug id=8371feab59e9 created=2026-11-13T22:58:56+00:00 state=fixed -->
### 8371feab59e9 · finding [fixed] · argocd-extras, cnc-prod, infisical, staging-gate, cnc-staging-host fixed in git

runs-fr is public (git ls-remote anonymous OK), so repo-runs-fr ES, its ClusterGenerator and manual op cicd-staging-gate-argocd-runs-fr-repo-key are removed; test_presync_hook_pvc_exists_before_hook.py pins the PVC fix; infisical ignores /metadata/annotations/updatedAt; staging-gate notify timeout 2m0s; cnc-staging-host ES remoteRef defaults explicit. kubectl diff --server-side is empty even on the OLD manifests (ESO webhook defaults on dry-run), so Synced-after-merge is unproven until ArgoCD reconciles.

<!-- fr:journal kind=finding scope=debug id=ef707b2f6c9c created=2026-11-13T22:58:59+00:00 state=open -->
### ef707b2f6c9c · finding [open] · runs-fr-staging: prerequisites present, vCluster not registered

Pod resource.exclusions for https://staging.vcluster-staging.svc:443 is live in argocd-cm (since 2026-09-20, controller restarted 2026-09-22 after). Only cluster-cnc-staging is registered. Operator runs manual op cicd-staging-gate-register-vcluster.

<!-- fr:journal kind=review scope=debug id=753cc33cae32 created=2026-11-13T23:36:27+00:00 -->
### 753cc33cae32 · review · Self review

No review findings; full suite 2284 pass. Remaining failure test_every_rendered_image_resolves is main's #971 digest drift (4 agent-images digests), unrelated.
