# Journal: 2026-08-01-structured-auth-machine-files

<!-- fr:journal kind=repro scope=debug id=dual-issuer-quorum-loss created=2026-08-01T07:57:32 phase=2 -->
### dual-issuer-quorum-loss · repro · Dual-issuer ConfigPatch takes control-plane quorum down (phase 2)

Applying patches/phase13-auth/omni-configpatch.yaml caused all control planes to reboot. Rollback SHA a32a343379b5fa9ed405c52229665332672e000c was re-applied. mini-1 serves the API with etcd readiness failing; mini-2 and mini-3 remain below kubelet/etcd startup while legacy desired state is restored in Omni.

<!-- fr:journal kind=root-cause scope=debug id=machine-files-create-outside-var created=2026-08-01T07:57:43 phase=2 -->
### machine-files-create-outside-var · root-cause · Talos rejects create operation outside /var (phase 2)

Talos v1.12.6 boot logs show writeUserFiles failed with: create operation not allowed outside of /var: /etc/kubernetes/authn-config.yaml. The Phase 1 ConfigPatch used machine.files op: create for that /etc path. This blocks boot before kubelet, trustd, and etcd. Omni legacy rollback is desired but mini-2 and mini-3 cannot converge without recovery authority.

<!-- fr:journal kind=hypothesis scope=debug id=stale-mini-config-status-hash created=2026-08-01T08:56:35 phase=2 -->
### stale-mini-config-status-hash · hypothesis · Unchanged ConfigPatch reapply left mini control planes stale (phase 2)

mini-2 and mini-3 reached configuptodate=true after their first recovery marker apply, then returned to Config Outdated when the six-resource recovery file re-applied those same marker specs unchanged. Hypothesis: Omni 1.5 advanced resource bookkeeping without a generated config hash change. Test by changing only the two marker contents to force a harmless real desired hash.

<!-- fr:journal kind=finding scope=debug id=stale-mini-config-status-hash-fixed created=2026-08-01T09:00:41 phase=2 state=fixed -->
### stale-mini-config-status-hash-fixed · finding [fixed] · Forced real hash change cleared stale Omni status (phase 2)

Changing only the mini-2 and mini-3 /var recovery marker contents caused Omni 1.5 to re-apply their desired configs. The strict gate reached 7/7 ready, configuptodate=true, configapplystatus=APPLIED. This confirms unchanged ConfigPatch reapplication caused the stale status.

<!-- fr:journal kind=finding scope=debug id=clean-legacy-recovery-complete created=2026-08-01T09:12:24 phase=2 state=fixed -->
### clean-legacy-recovery-complete · finding [fixed] · Cluster recovered to clean legacy desired state (phase 2)

Deleted all six temporary 999-recovery-* ConfigPatches. After Omni serialized the cleanup, all seven machines remained ready, configuptodate=true, and configapplystatus=APPLIED for six consecutive 10-second samples. All seven Kubernetes nodes are Ready, all three API servers use legacy OIDC, and /readyz passes.

<!-- fr:journal kind=ruled-out scope=debug id=config-flags-only-gate created=2026-08-01T09:12:48 phase=2 -->
### config-flags-only-gate · ruled-out · Config flags alone do not prove recovery (phase 2)

The first cleanup completion gate required ready/configuptodate/configapplystatus but omitted Omni stage. It produced six stable samples while raspi-1 remained stage 7 REBOOTING and Kubernetes NotReady. Supersede clean-legacy-recovery-complete; recovery now additionally requires stage 4 for all seven machines.

<!-- fr:journal kind=finding scope=debug id=stage-aware-clean-recovery-complete created=2026-08-01T09:14:45 phase=2 state=fixed -->
### stage-aware-clean-recovery-complete · finding [fixed] · Verified clean legacy recovery with stage-aware gate (phase 2)

All temporary recovery ConfigPatches are absent. All seven Omni machines remained stage 4 Running, ready=true, configuptodate=true, and configapplystatus=APPLIED for six consecutive 10-second samples. Final independent checks: Omni RUNNING Ready 7/7; Kubernetes nodes Ready 7/7; API servers Running/Ready 3/3 with legacy OIDC and no structured-auth flag; /readyz passes.

<!-- fr:journal kind=finding scope=debug id=talos-safe-authn-config-fixed created=2026-08-01T09:27:59 phase=2 state=fixed -->
### talos-safe-authn-config-fixed · finding [fixed] · Talos-safe structured-auth delivery fixed and tested (phase 2)

Updated the ConfigPatch to write /var/lib/kubernetes/authn-config.yaml with mode 0644 and mount it read-only at /etc/kubernetes/authn-config.yaml inside kube-apiserver. Added regression assertions for distinct host/container paths and non-root readability. Focused suite: 3 passed. Full scripts/tests suite: 359 passed, 8 skipped. Agent and plan validators passed.

<!-- fr:journal kind=finding scope=debug id=structured-auth-control-plane-rollout-complete created=2026-08-01T13:53:12 phase=2 state=fixed -->
### structured-auth-control-plane-rollout-complete · finding [fixed] · Control-plane-only structured-auth rollout completed (phase 2)

After PRs #741 and #742, Omni ConfigPatch version 9 targeted only frank-control-planes. Omni remained RUNNING Ready 7/7; all three kube-apiserver pods were Running/Ready with exactly one --authentication-config=/etc/kubernetes/authn-config.yaml argument, no legacy --oidc-* arguments, and the /var/lib/kubernetes/authn-config.yaml host file mounted read-only. /readyz and etcd readiness passed. The retained old-issuer token normalized from preferred_username=ak-Kubernetes Agent Access-client_credentials to username=authentik:ak-Kubernetes Agent Access-client_credentials with the same empty claim groups plus TokenReview's system:authenticated group. Omni service-account cluster-admin remained yes. All four worker boot IDs were byte-for-byte unchanged.
