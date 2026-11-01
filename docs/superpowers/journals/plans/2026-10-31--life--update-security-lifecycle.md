<!-- fr:journal-schema=3 -->
# Journal: 2026-10-31--life--update-security-lifecycle

<!-- fr:journal kind=decision scope=plan id=plan-repo-split created=2026-10-31T18:53:33+00:00 -->
### plan-repo-split · decision · One plan per repo (operator chose option A)

frank (this plan), derio-net/cluster-update-fr (console), derio-net/agent-images (session image); sibling plans run by cross-repo agents in their own workspaces.

<!-- fr:journal kind=decision scope=plan id=manual-back-loaded created=2026-10-31T18:53:33+00:00 -->
### manual-back-loaded · decision · Bootstrap/manual work back-loaded to phase 7

No agentic phase needs live secrets; apps tolerate missing Secrets (optional: true) until the trailing manual phase.

<!-- fr:journal kind=discovery scope=plan id=p5-scrub-boundary-lessons created=2026-10-31T19:12:03+00:00 phase=5 -->
### p5-scrub-boundary-lessons · discovery · Scrubber regexes must not consume boundaries or anchor at end of line (phase 5)

Security review of the console's internal/scrub/scrub.go found two bypasses that apply equally to scripts/life_scrub.py: (1) a pattern that consumes its trailing boundary char misses the second of two ADJACENT tokens — check boundaries in code or loop until stable, test adjacent tokens; (2) a `$`-anchored, unquoted-key yaml-secret pattern misses trailing comments and JSON pairs — no end anchor, optional key quotes, value ends at whitespace/quote/comma; test both. Share fixtures with the console repo.

<!-- fr:journal kind=discovery scope=plan id=p5-session-image-interface created=2026-10-31T19:14:34+00:00 phase=5 -->
### p5-session-image-interface · discovery · upgrade-session image interface (agent-images#171) (phase 5)

Image ghcr.io/derio-net/upgrade-session:<sha>, built FROM agent-base (NOT infra-shell: s6/sshd is incompatible with a read-only root FS). User uid 1000 'claude', HOME /home/claude, nothing baked under HOME: mount emptyDir at /home/claude and /tmp, readOnlyRootFilesystem true, drop ALL caps, no SA token unless the type needs it. Entrypoint tini + upgrade-session-entrypoint, CMD bash. Pod env UPGRADE_TALOS_MINOR (1.12|1.13|1.14) and UPGRADE_K8S_MINOR (1.34-1.37) select pinned talosctl/kubectl; a bad minor exits 2 at start. In-session: use-versions --talos X --kubernetes Y, use-versions --list; symlinks in $HOME/.local/bin. AGENTS.md/CLAUDE.md must be mounted by frank (e.g. /home/claude). No sshd: attach via runs-fr. Frank must add upgrade-session to the AGENT_IMAGES bump allowlist (agent-images-bump workflow).

<!-- fr:journal kind=discovery scope=plan id=p5-scrub-delimiters-inside-secrets created=2026-10-31T19:15:53+00:00 phase=5 -->
### p5-scrub-delimiters-inside-secrets · discovery · Scrubber must not stop a secret value at # , or } inside it (phase 5)

Second console finding: stopping the value class at #, comma or } under-redacts secrets that contain them. Quoted values: capture to the matching quote. Unquoted: capture non-space, strip a trailing , or } in code; # is a comment only after whitespace. Fixtures with those chars early in the value, quoted and unquoted. Prefer over-redaction.

<!-- fr:journal kind=discovery scope=plan id=p5-session-selection-explicit created=2026-10-31T19:17:35+00:00 phase=5 -->
### p5-session-selection-explicit · discovery · Session pod must run use-versions explicitly; never set command: (phase 5)

Review of agent-images#171: the env-based selection (UPGRADE_*_MINOR) only runs via the image ENTRYPOINT; a pod spec 'command:' replaces it and the env is silently ignored, and with nothing selected neither talosctl nor kubectl is on PATH. Frank's session pod template must use 'args:' not 'command:', AND every brief template must start with an explicit 'use-versions --talos <minor> --kubernetes <minor>' and a 'use-versions --list' check.

<!-- fr:journal kind=discovery scope=plan id=p5-scrub-exact-values-first created=2026-10-31T19:19:48+00:00 phase=5 -->
### p5-scrub-exact-values-first · discovery · Redact known secret values first; regexes are the second layer (phase 5)

Three rounds of console scrubber findings (adjacent tokens, end anchors, delimiters inside values, next-line YAML values, unterminated quotes) show regex-only redaction keeps missing shapes. Frank's life_scrub.py should mirror the console: exact-value redaction of known/injected secrets (plus base64/URL-encoded forms and each line of multi-line values) first, regex patterns second; fixtures for next-line YAML values and unterminated quotes.

<!-- fr:journal kind=discovery scope=plan id=p1-omni-version created=2026-10-31T19:23:32+00:00 phase=1 -->
### p1-omni-version · discovery · Omni backend is v1.5.0 (measured) (phase 1)

omnictl get clusters reports frank talos 1.12.6 / k8s 1.35.3; omnictl warned its client 1.8.1 differs from backend 1.5.0, which is the running Omni version, now pinned as OMNI_VERSION=v1.5.0. Side effect: the Omni CLI key had expired and omnictl re-registered a PGP key (~/.talos/keys) on first use. Hop measured via kubectl: talos 1.12.5 / k8s 1.34.1, as the spec stated.

<!-- fr:journal kind=discovery scope=plan id=p1-audit-scope created=2026-10-31T19:23:32+00:00 phase=1 -->
### p1-audit-scope · discovery · Image audit: scope decisions and one real finding (phase 1)

All 114 rendered images across 127 sources (0 apps skipped; OCI repoURLs without a scheme are treated as oci://) are pinned. The audit ignores Helm test hooks (helm.sh/hook test, never applied by Argo CD) and disabled operator components (enabled: false, e.g. gpu-operator vgpuManager), and joins NVIDIA-style repository/image/version triples. The one real unpinned image was litellm's bitnami postgresql (chart default :latest): pinned by digest in apps/litellm/values.yaml to the running image (PostgreSQL 18.4, no pod roll expected).

<!-- fr:journal kind=discovery scope=plan id=p1-operator-images created=2026-10-31T19:23:32+00:00 phase=1 -->
### p1-operator-images · discovery · Operator-chosen images are invisible to the render audit (phase 1)

AWX's postgres pod runs quay.io/sclorg/postgresql-15-c9s:latest, chosen by the AWX operator (awx.yaml sets no postgres_image). It is not in any rendered manifest so the audit cannot see it. The operator composes image:version so a digest cannot be set via postgres_image_version; pinning needs postgres_image_version set to a tag. Left for the classification phase; operator-created workloads (CNPG, AWX) need a runtime audit.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-10-31T19:23:32+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

declarative YAML files and a template value only; nothing to clean

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-10-31T19:26:26+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · test_life_images_pinned only reads the committed snapshot; a new :latest in any manifest keeps all tests green (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-10-31T19:26:28+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · pinned accepts floating tags (postgres:16, python:3.13-slim, node:22-alpine, caddy:2.9-alpine, alpine:3.20, ovms-retrieval-models:2); weaker than R2 exact version (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-10-31T19:26:30+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · litellm postgres tag->digest changes the StatefulSet image string so the DB pod restarts; journal claim wrong; digest index/platform unverified (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-10-31T19:26:32+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · audit walker silently exempts enabled:false dicts, $( / {{ images and ConfigMap/env-embedded images; exemptions not machine-visible (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-10-31T19:26:34+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · OMNI_VERSION pin may not reach OMNI_IMG_TAG depending on how the template is consumed; undocumented and untested (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r6 created=2026-10-31T19:26:36+00:00 phase=1 state=open review_scope=in -->
### p1-r6 · finding [open] (reviewer: in scope) · --check does not fail when sources are skipped (e.g. kustomize missing), giving a false green (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r7 created=2026-10-31T19:26:38+00:00 phase=1 state=open review_scope=out -->
### p1-r7 · finding [open] (reviewer: out of scope) · operator-created workloads (AWX sclorg postgresql-15-c9s:latest) are invisible to a render audit (phase 1)

<!-- fr:journal kind=discovery scope=plan id=p4-console-writes-namespaced-role created=2026-10-31T19:30:31+00:00 phase=4 -->
### p4-console-writes-namespaced-role · discovery · Console write RBAC must be a namespaced Role in upgrade-sessions, never a ClusterRole (phase 4)

Console security review found a path-injection hole in its own write guard (since fixed in cluster-update-fr). Frank's RBAC is the second layer and must hold on its own: reads may be a ClusterRole (get/list/watch only); every write verb (create/delete pods, secrets, rolebindings) must live in a Role + RoleBinding in namespace upgrade-sessions, and the console may not create RoleBindings that reference a ClusterRole other than the per-type session roles (use resourceNames / an escalate-free binding check). Test: no ClusterRole bound to the console SA grants any verb outside get/list/watch.

<!-- fr:journal kind=discovery scope=plan id=p1-restart-list created=2026-10-31T19:36:52+00:00 phase=1 -->
### p1-restart-list · discovery · Workloads whose pod spec changes on sync (will restart) (phase 1)

Running: litellm-postgresql STS (:latest -> verified multi-arch index digest, same bytes, WILL roll once); awx-postgres-15 STS + awx-web/awx-task Deployments (operator renders postgresql-15-c9s:20260527, redis:7.4.9; redis digest not matched on Docker Hub so bytes may differ); vk-remote postgres Deployment (16-alpine -> 16.15-alpine); hop landing Deployment (caddy 2.9.1-alpine); gpu-operator-extras validation-markers DaemonSet (busybox 1.37.0). Next-run only: Tekton tasks/pipelines, mirror-reconcile + ci-delivery-check CronJobs. RISK: Job templates are immutable - vk-remote postgres-init and cnc-prod snapshot-job (postgres 16.15) may fail sync with an immutable-field error; delete the completed Job first. Where the running digest matched no tag, the latest patch of the old series was chosen (node 22.23.3 and alpine 3.21.7 matched).

<!-- fr:journal kind=discovery scope=plan id=p1-audit-rules created=2026-10-31T19:36:54+00:00 phase=1 -->
### p1-audit-rules · discovery · Audit rules: exact versions, exemptions visible, R2 enforced offline (phase 1)

Exact tag = >=3 numeric parts, 8+ digit date stamp, commit hash or digest; allowlist scripts/tests/fixtures/life/pin-exceptions.yaml (postgres major.minor, own immutable tags openrgb:1.0rc2 and ovms-retrieval-models:2). Exemptions (helm test hooks, named disabled operator components, unresolved params, static non-image strings) are written to audit-exemptions.txt. R2 is also checked offline against git-resident sources so a stale snapshot fails. --check fails on skipped sources. Omni pin made effective via literal OMNI_IMG_TAG. AWX CR pins postgres and redis. Operator-created images elsewhere (CNPG etc.) remain a known gap for the console live inventory.

<!-- fr:journal kind=discovery scope=plan id=p1-job-immutability created=2026-10-31T19:40:18+00:00 phase=1 -->
### p1-job-immutability · discovery · Jobs whose completed instances must be deleted before ArgoCD can sync the new template (phase 1)

A Job pod template is immutable. vk-remote postgres-init Job (PostSync hook, hook-delete-policy BeforeHookCreation - self-clearing if Argo runs the hook) and cnc-prod snapshot-job (PreSync hook, BeforeHookCreation,HookSucceeded - self-clearing; one instance is currently Pending/running). If either is ever found as a non-hook completed Job, delete it before sync. No other Job in git-resident manifests changed image in this phase. The trailing manual phase carries the check: kubectl get jobs -A and delete completed instances of these two before the first post-merge sync.

<!-- fr:journal kind=discovery scope=plan id=p1-restart-list-v2 created=2026-10-31T19:40:47+00:00 phase=1 -->
### p1-restart-list-v2 · discovery · p1-restart-list correction: same bytes vs new bytes (supersedes p1-restart-list) (phase 1)

SAME bytes (image string only, restart on sync): litellm-postgresql STS (digest), awx-postgres-15 STS (20260527@digest), awx-web, vk-remote postgres Deployment (postgres:16-alpine@digest). awx-task: redis moves to awx-web's redis:7 digest (it ran a different one; ephemeral cache, no data). NEW bytes, stateless: hop landing (caddy 2.9.1-alpine), gpu-operator-extras validation-markers DaemonSet (busybox 1.37.0); Tekton tasks/pipelines/triggers and mirror-reconcile + ci-delivery-check CronJobs (python 3.13.18-slim, alpine 3.20.10, node 22.23.3-alpine, busybox 1.37.0) on next run. cnc-prod snapshot-job (pg_dump client PreSync hook): postgres:16.15@registry-index-digest, new bytes because nothing ran under the old tag; not a data store.

<!-- fr:journal kind=review scope=plan id=p1-review created=2026-10-31T19:41:25+00:00 phase=1 -->
### p1-review · review · Phase 1 independent review: 7 findings (6 in, 1 out) (phase 1)

Reviewer raised p1-r1..p1-r7. All six in-scope findings fixed by the phase executor with tests (25 passing). p1-r7 stays out of scope: the render audit cannot see operator-created images in general; the one known instance (AWX postgres/redis) was pinned in this phase, and the general gap is covered by the console's live inventory (R1).

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-10-31T19:41:25+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: test_life_images_pinned only reads the committed snapshot; a new :latest in any manifest keeps all tests green (phase 1)

Offline render of git-resident sources + subset-of-snapshot test; proven red with a planted :latest.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-10-31T19:41:25+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: pinned accepts floating tags (postgres:16, python:3.13-slim, node:22-alpine, caddy:2.9-alpine, alpine:3.20, ovms-retrieval-models:2); weaker than R2 exact version (phase 1)

Exact = >=3 numeric parts, date stamp, commit hash or digest; reasoned pin-exceptions.yaml; floating tags pinned; stateful images digest-pinned to the running bytes with a test enforcing it.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-10-31T19:41:25+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: litellm postgres tag->digest changes the StatefulSet image string so the DB pod restarts; journal claim wrong; digest index/platform unverified (phase 1)

Digest verified as the multi-arch index equal to the running imageID; comment and journal now state the StatefulSet rolls once.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-10-31T19:41:25+00:00 phase=1 state=fixed resolves=p1-r4 -->
### p1-r4-resolved · finding [fixed] · resolves p1-r4: audit walker silently exempts enabled:false dicts, $( / {{ images and ConfigMap/env-embedded images; exemptions not machine-visible (phase 1)

enabled:false skip limited to named operator keys; string-embedded refs and *_image pairs audited; exemptions written to audit-exemptions.txt with a non-silence test.

<!-- fr:journal kind=finding scope=plan id=p1-r5-resolved created=2026-10-31T19:41:25+00:00 phase=1 state=fixed resolves=p1-r5 -->
### p1-r5-resolved · finding [fixed] · resolves p1-r5: OMNI_VERSION pin may not reach OMNI_IMG_TAG depending on how the template is consumed; undocumented and untested (phase 1)

Literal OMNI_IMG_TAG plus OMNI_VERSION anchor; test asserts both equal and exact.

<!-- fr:journal kind=finding scope=plan id=p1-r6-resolved created=2026-10-31T19:41:25+00:00 phase=1 state=fixed resolves=p1-r6 -->
### p1-r6-resolved · finding [fixed] · resolves p1-r6: --check does not fail when sources are skipped (e.g. kustomize missing), giving a false green (phase 1)

--check fails on any skipped source; kubectl kustomize fallback.

<!-- fr:journal kind=finding scope=plan id=p1-r7-resolved created=2026-10-31T19:41:25+00:00 phase=1 state=open resolves=p1-r7 out_of_scope=true -->
### p1-r7-resolved · finding [out-of-scope] · resolves p1-r7: operator-created workloads (AWX sclorg postgresql-15-c9s:latest) are invisible to a render audit (phase 1)

Not caused by this change: operator-created workloads were invisible before it. The AWX instance was pinned via its CR in this phase; the general gap belongs to the console's live inventory (R1), not the git render audit.

<!-- fr:journal kind=decision scope=plan id=p2-smoke-layout created=2026-10-31T20:00:28+00:00 phase=2 -->
### p2-smoke-layout · decision · Smoke declarations live at smoke/<cluster>/<app>.yaml (phase 2)

Two Application names exist on both clusters (argocd, fluent-bit), so a flat smoke/<app>.yaml is ambiguous. The cluster is the directory and also a field; a test fails on any orphan or missing file. Checks are in-cluster Service URLs (the verifier runs inside the cluster); Hop public services check their PUBLIC URL, headplane and landing are mesh-only and say so.

<!-- fr:journal kind=discovery scope=plan id=p2-facts-fixture created=2026-10-31T20:00:28+00:00 phase=2 -->
### p2-facts-fixture · discovery · Stateful and Rollout detection is a generated fixture plus an offline re-check (phase 2)

scripts/tests/fixtures/life/app-facts.yaml (life_policy.py --emit-facts) records per app: stateful, rollout, charts, images, repo paths. Detection counts PersistentVolumeClaim, workload kinds carrying volumeClaimTemplates or a persistentVolumeClaim volume, and operator CRs (AWX, VMSingle, VLSingle). Tekton TriggerTemplates that merely mention a claim shape are not state. Longhorn is stateful by identity. A test re-detects git-resident sources offline so a stale fixture fails. 35 apps are stateful; the only Rollout app is litellm-extras. Regenerate with RENDER_CACHE set (about 3 min cold).

<!-- fr:journal kind=discovery scope=plan id=p2-renovate-matchers created=2026-10-31T20:00:28+00:00 phase=2 -->
### p2-renovate-matchers · discovery · Renovate rules match by repo path and chart name, resolved by policy order (phase 2)

Renovate cannot match an Application by name, so each policy rule is translated to matchFileNames (the app's manifests path, values files and root template) plus matchPackageNames (its charts). Later rules override earlier ones, so defaults come first, then per-app session rules, with groupName reset to null and labels replaced (path:<x>). A chart shared by apps of different paths (postgresql) takes the strictest. All 16 variants set automerge false and approval true only for session/operator-runbook. A test proves no stateful or Rollout app path appears in an auto-merge or batch rule.

<!-- fr:journal kind=discovery scope=plan id=p2-renovate-validator-skipped created=2026-10-31T20:00:28+00:00 phase=2 -->
### p2-renovate-validator-skipped · discovery · renovate-config-validator not installed locally, test skipped (phase 2)

The validator is an npm binary; the test skips with a reason when it is not on PATH (no global npm install allowed here). CI or the console phase should run it for real.

<!-- fr:journal kind=discovery scope=plan id=p2-renovate-placeholders created=2026-10-31T20:00:28+00:00 phase=2 -->
### p2-renovate-placeholders · discovery · Renovate GitHub App ids and PEM are placeholders until the manual phase (phase 2)

clustergenerator.yaml carries appID/installID PENDING-MANUAL-PHASE so the generator fails loudly rather than minting a wrong token; the PEM Secret github-app-renovate-key must be applied in namespace renovate (ESO resolves secretRef in the consumer namespace). The token secretKeyRef is optional so the sync never blocks. Phase 7 must fill both ids and apply the PEM. The renovate/renovate:44.198.3 image was verified on Docker Hub and the audit snapshot regenerated.

<!-- fr:journal kind=discovery scope=plan id=p2-smoke-unverified-secrets created=2026-10-31T20:00:28+00:00 phase=2 -->
### p2-smoke-unverified-secrets · discovery · Two functional smoke checks name secrets that were not read from a cluster (phase 2)

litellm chat uses litellm-api-keys/LITELLM_MASTER_KEY (from the ExternalSecret) and the Grafana dashboards check assumes the chart-default admin secret victoria-metrics-grafana (admin-user/admin-password). The litellm check also depends on the GPU timeshare slot. Confirm both against the live cluster when the verifier is built.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t1 created=2026-10-31T20:00:28+00:00 phase=2 -->
### no-refactor-p2-t1 · discovery · no-refactor-because P2.T1 (phase 2)

update-policy.yaml and life_policy.py were written once; the shared enumeration is extracted in P2.T4.S3

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t2 created=2026-10-31T20:00:28+00:00 phase=2 -->
### no-refactor-p2-t2 · discovery · no-refactor-because P2.T2 (phase 2)

renovate.json5 is generated from the policy, so there is no hand-written duplicate to tidy

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t3 created=2026-10-31T20:00:28+00:00 phase=2 -->
### no-refactor-p2-t3 · discovery · no-refactor-because P2.T3 (phase 2)

five small declarative manifests, nothing to clean

<!-- fr:journal kind=finding scope=plan id=p2-r1 created=2026-10-31T20:05:52+00:00 phase=2 state=open review_scope=in -->
### p2-r1 · finding [open] (reviewer: in scope) · Smoke targets contain a .None. namespace (litellm, zot, infisical, awx, hop/crowdsec); no test catches it (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r2 created=2026-10-31T20:06:04+00:00 phase=2 state=open review_scope=in -->
### p2-r2 · finding [open] (reviewer: in scope) · http smoke checks accept 200/3xx/401/403(/404) so only reachability is proved; argocd probes applicationset-controller (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r3 created=2026-10-31T20:06:16+00:00 phase=2 state=open review_scope=in -->
### p2-r3 · finding [open] (reviewer: in scope) · hop/caddy smoke duplicates the www check; its security-headers note is not asserted (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r4 created=2026-10-31T20:06:24+00:00 phase=2 state=open review_scope=in -->
### p2-r4 · finding [open] (reviewer: in scope) · Renovate CronJob fails hourly while App ids are placeholders; suspend until the manual phase (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r10 created=2026-10-31T20:06:58+00:00 phase=2 state=open review_scope=in -->
### p2-r10 · finding [open] (reviewer: in scope) · No RENOVATE_GIT_AUTHOR for an App installation token (verify live) (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r11 created=2026-10-31T20:07:07+00:00 phase=2 state=open review_scope=in -->
### p2-r11 · finding [open] (reviewer: in scope) · Slow rendering tests re-render per module; no slow marker or shared cache (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r12 created=2026-10-31T20:07:14+00:00 phase=2 state=open review_scope=out -->
### p2-r12 · finding [open] (reviewer: out of scope) · ovms /v2/models/<name>/ready unverified against MediaPipe-graph servables (plan-prescribed; documented gotcha) (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r5 created=2026-10-31T20:07:36+00:00 phase=2 state=open review_scope=in -->
### p2-r5 · finding [open] (reviewer: in scope) · ExternalSecret refresh 45m vs 1h token and 3000s deadline lets the token expire mid-run (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r6 created=2026-10-31T20:07:49+00:00 phase=2 state=open review_scope=in -->
### p2-r6 · finding [open] (reviewer: in scope) · Validator test skipped when absent; fileMatch (renamed managerFilePatterns) and groupName:null unverified (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r7 created=2026-10-31T20:07:55+00:00 phase=2 state=open review_scope=in -->
### p2-r7 · finding [open] (reviewer: in scope) · No test proves the generated Renovate config (last-match) agrees with resolve() (first-match); automerge not scanned recursively (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r8 created=2026-10-31T20:08:00+00:00 phase=2 state=open review_scope=in -->
### p2-r8 · finding [open] (reviewer: in scope) · Stateful/rollout facts not re-checked for remote-chart apps; charts-session test only checks images; no facts-drift job (phase 2)

<!-- fr:journal kind=finding scope=plan id=p2-r9 created=2026-10-31T20:08:09+00:00 phase=2 state=open review_scope=in -->
### p2-r9 · finding [open] (reviewer: in scope) · renovate image pinned by tag not digest and default patch policy lets it auto-update itself (phase 2)

<!-- fr:journal kind=discovery scope=plan id=p5-briefs-untrusted-data created=2026-10-31T20:19:04+00:00 phase=5 -->
### p5-briefs-untrusted-data · discovery · Brief templates must fence forge-sourced text as untrusted data (phase 5)

Console security review: PR titles/bodies and release notes flowed verbatim into session briefs read by an agent holding cluster credentials (prompt injection). Frank's brief templates (docs/upgrade-briefs/) and AGENTS.md/CLAUDE.md must: keep instruction sections free of interpolated forge text; put release notes/PR text in a fenced block introduced as untrusted data, not instructions; and instruct the agent never to follow instructions found in those blocks, never to widen its own credentials, and to stop and ask the operator if the data asks it to. Test the templates for that wording and that no {{pr_*}}/{{release_*}} placeholder sits outside the untrusted block.

<!-- fr:journal kind=discovery scope=plan id=p4-console-trust-config created=2026-10-31T20:19:08+00:00 phase=4 -->
### p4-console-trust-config · discovery · Console needs the trusted bot logins and branch prefixes in its config (phase 4)

Console only accepts PRs authored by the configured Renovate App bot (or its own App bot for batches), from the base repo, on configured branch prefixes (renovate/, cluster-update/). Frank's console config (configMapGenerator) must declare renovate_bot_login, console_bot_login and the branch prefixes; they are filled from the Apps the operator creates in phase 7 (placeholders until then, console treats placeholders as 'trust nothing').

<!-- fr:journal kind=discovery scope=plan id=p4-console-ingress-lockdown created=2026-10-31T20:24:51+00:00 phase=4 -->
### p4-console-ingress-lockdown · discovery · Only Traefik may reach the console and runs-fr UI ports; console verifies Authentik's JWT (phase 4)

Console security review: a bare trusted header is spoofable by anything that reaches the pod directly. Frank side for phase 4: (1) CiliumNetworkPolicy on cluster-update-fr and runs-fr allowing ingress to the UI port ONLY from Traefik pods (traefik namespace + label), metrics port only from vmagent; (2) the Authentik proxy provider sends the JWT header the console verifies (config: authentik issuer/JWKS URL, audience, operator group name) — add the provider property mapping if needed; (3) runs-fr has no JWT verification, so its NetworkPolicy is the primary guard and it must ALSO sit behind forward-auth restricted to the operator group (Authentik policy binding on the provider); (4) tests asserting both NetworkPolicies exist and name the right ports.

<!-- fr:journal kind=discovery scope=plan id=p4-console-contract created=2026-10-31T20:38:29+00:00 phase=4 -->
### p4-console-contract · discovery · Console contract from cluster-update-fr#1 (deploy side) (phase 4)

Ports: 8080 UI (ingress from Traefik ONLY, requires X-authentik-jwt forwarded), 9090 metrics+health (vmagent), 8081 session API (ingress from upgrade-sessions pods ONLY). Env: AUTHENTIK_JWKS_URL, AUTHENTIK_ISSUER, AUTHENTIK_AUDIENCE, OPERATOR_GROUP, RENOVATE_BOT_LOGIN, CONSOLE_BOT_LOGIN, VICTORIALOGS_URL, SESSION_SECRET_DIR, SESSION_API_URL, RUNS_FR_URL (console links RUNS_FR_URL/#<id>; runs-fr has no deep link). Omni version: an omnictl sidecar with the Reader SA writes a JSON file the console reads. RBAC: console needs get (in addition to create/delete) on secrets in upgrade-sessions; it creates NO RoleBindings. Console App needs contents, PRs, statuses, issues, webhooks write + metadata read; Renovate and console are SEPARATE Apps.

<!-- fr:journal kind=discovery scope=plan id=p5-session-rbac-static created=2026-10-31T20:38:31+00:00 phase=5 -->
### p5-session-rbac-static · discovery · Session RBAC is static per app namespace, not console-created RoleBindings (phase 5)

Console creates no RoleBindings (removes an escalation path). Frank binds, in each stateful app namespace, a Role allowing create on Longhorn snapshots (snapshots.longhorn.io / volumesnapshots) to SA upgrade-session-stateful in upgrade-sessions; and in each Rollouts app namespace a Role allowing patch on rollouts/status to SA upgrade-session-rollouts. No delete verbs. Generated from update-policy facts so new stateful apps get bindings automatically; test the set equals the stateful/Rollouts app set. Credential files mount at SESSION_SECRET_DIR; pods call SESSION_API_URL (console :8081); briefs at docs/upgrade-briefs/<type>.md plus AGENTS.md. P4.T1.S1's RoleBinding-template exception and P5.T1.S1 text are superseded by this.

<!-- fr:journal kind=discovery scope=plan id=p3-hop-scan-format created=2026-10-31T20:38:33+00:00 phase=3 -->
### p3-hop-scan-format · discovery · Hop scan result line format consumed by the console (phase 3)

The console reads hop scan results from VictoriaLogs lines 'hop-scan result {json}' (one JSON object per image). Match exactly in apps/hop-scan; the console needs VICTORIALOGS_URL.

<!-- fr:journal kind=discovery scope=plan id=p5-session-merge-and-exfil-boundary created=2026-10-31T21:04:39+00:00 phase=5 -->
### p5-session-merge-and-exfil-boundary · discovery · Session GitHub token must not bypass the console as merger; egress bounds exfiltration (phase 5)

Console security review c1s-r12 (frank-side): (1) the session GitHub App token must be scoped to contents:write on branches + pull_requests:write only, and main must be protected by a ruleset requiring a PR (bypass: operator and the console App only), so a steered session can open a PR but never push to main; (2) session egress per type is the exfiltration boundary: GitHub API only (not gist/raw uploads — restrict to api.github.com and the git endpoints of derio-net/frank), model provider endpoints, and the type's cluster endpoints; no general internet. Phase 5 tests assert both; phase 7 applies the main ruleset.

<!-- fr:journal kind=review scope=plan id=p2-review created=2026-11-01T05:00:22+00:00 phase=2 -->
### p2-review · review · Phase 2 independent review: 12 findings (11 in, 1 out) (phase 2)

Reviewer raised p2-r1..p2-r12. All 11 in-scope findings fixed by the phase executor with tests; life suite 64 passed, 1 skipped (validator absent locally; CI fails rather than skips). p2-r12 stays out of scope (plan-prescribed OVMS endpoint; verified live in phase 7).

<!-- fr:journal kind=finding scope=plan id=p2-r1-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r1 -->
### p2-r1-resolved · finding [fixed] · resolves p2-r1: Smoke targets contain a .None. namespace (litellm, zot, infisical, awx, hop/crowdsec); no test catches it (phase 2)

Smoke targets take the rendered Service namespace; facts record services; test rejects None/{{/$ and unknown svc.ns.

<!-- fr:journal kind=finding scope=plan id=p2-r2-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r2 -->
### p2-r2-resolved · finding [fixed] · resolves p2-r2: http smoke checks accept 200/3xx/401/403(/404) so only reachability is proved; argocd probes applicationset-controller (phase 2)

One real health status per app (≤2), real health endpoints, argocd-server not applicationset-controller.

<!-- fr:journal kind=finding scope=plan id=p2-r3-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r3 -->
### p2-r3-resolved · finding [fixed] · resolves p2-r3: hop/caddy smoke duplicates the www check; its security-headers note is not asserted (phase 2)

hop/caddy asserts HSTS and CSP headers; duplicate removed.

<!-- fr:journal kind=finding scope=plan id=p2-r4-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r4 -->
### p2-r4-resolved · finding [fixed] · resolves p2-r4: Renovate CronJob fails hourly while App ids are placeholders; suspend until the manual phase (phase 2)

Renovate CronJob suspended while App ids are placeholders; test ties suspend to placeholder state; phase 7 unsuspends.

<!-- fr:journal kind=finding scope=plan id=p2-r5-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r5 -->
### p2-r5-resolved · finding [fixed] · resolves p2-r5: ExternalSecret refresh 45m vs 1h token and 3000s deadline lets the token expire mid-run (phase 2)

refreshInterval 20m, activeDeadlineSeconds 900; test asserts deadline+refresh < token lifetime.

<!-- fr:journal kind=finding scope=plan id=p2-r6-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r6 -->
### p2-r6-resolved · finding [fixed] · resolves p2-r6: Validator test skipped when absent; fileMatch (renamed managerFilePatterns) and groupName:null unverified (phase 2)

managerFilePatterns, no null groupName; validator test fails (not skips) when CI=true.

<!-- fr:journal kind=finding scope=plan id=p2-r7-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r7 -->
### p2-r7-resolved · finding [fixed] · resolves p2-r7: No test proves the generated Renovate config (last-match) agrees with resolve() (first-match); automerge not scanned recursively (phase 2)

Simulated Renovate last-match matching equals resolve() for every dep; recursive automerge scan.

<!-- fr:journal kind=finding scope=plan id=p2-r8-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r8 -->
### p2-r8-resolved · finding [fixed] · resolves p2-r8: Stateful/rollout facts not re-checked for remote-chart apps; charts-session test only checks images; no facts-drift job (phase 2)

Charts of stateful apps resolve to session; facts drift check against a full render.

<!-- fr:journal kind=finding scope=plan id=p2-r9-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r9 -->
### p2-r9-resolved · finding [fixed] · resolves p2-r9: renovate image pinned by tag not digest and default patch policy lets it auto-update itself (phase 2)

renovate digest-pinned; renovate, console and session images always take the session path.

<!-- fr:journal kind=finding scope=plan id=p2-r10-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r10 -->
### p2-r10-resolved · finding [fixed] · resolves p2-r10: No RENOVATE_GIT_AUTHOR for an App installation token (verify live) (phase 2)

RENOVATE_GIT_AUTHOR in App bot identity form with phase-7 placeholders; live check journaled.

<!-- fr:journal kind=finding scope=plan id=p2-r11-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=fixed resolves=p2-r11 -->
### p2-r11-resolved · finding [fixed] · resolves p2-r11: Slow rendering tests re-render per module; no slow marker or shared cache (phase 2)

slow marker, session-scoped render cache, memoised offline detection.

<!-- fr:journal kind=finding scope=plan id=p2-r12-resolved created=2026-11-01T05:00:22+00:00 phase=2 state=open resolves=p2-r12 out_of_scope=true -->
### p2-r12-resolved · finding [out-of-scope] · resolves p2-r12: ovms /v2/models/<name>/ready unverified against MediaPipe-graph servables (plan-prescribed; documented gotcha) (phase 2)

Not caused by this change: the per-model ready endpoint is the plan's documented choice and a known gotcha; it is checked live (and /v1/config consulted) in the phase 7 handover.

<!-- fr:journal kind=discovery scope=plan id=p5-no-ephemeral-containers created=2026-11-01T05:13:28+00:00 phase=5 -->
### p5-no-ephemeral-containers · discovery · No one but cluster-admin may add ephemeral containers or exec into session pods (phase 5)

Console security review: kubectl debug can attach an ephemeral container to a verified session pod and read its credential volume. Frank phase 5: no Role/ClusterRole bound to anything except cluster-admin grants pods/ephemeralcontainers or pods/exec in upgrade-sessions — runs-fr is the one exception for pods/exec (it is how the operator attaches), and must not get pods/ephemeralcontainers; test it. Consider a ValidatingAdmissionPolicy denying ephemeralContainers updates on pods labelled cluster-update.fr/type in upgrade-sessions.

<!-- fr:journal kind=decision scope=plan id=p3-trivy-scrape-vmservicescrape created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-trivy-scrape-vmservicescrape · decision · Trivy metrics scraped by a VMServiceScrape, chart ServiceMonitor off (phase 3)

Frank has no ServiceMonitor CRD convention (all scrapes are VMServiceScrape). The trivy-operator Application has a third source, apps/trivy-operator/manifests, holding the trivy-system Namespace and the VMServiceScrape. operator.metricsVulnIdEnabled=false keeps per-CVE series out. POST-MERGE MEASURE: size of the trivy-operator /metrics response (kubectl exec wget, wc -c) must stay well under promscrape.maxScrapeSize (32MB); trivy_image_vulnerabilities is per image x severity.

<!-- fr:journal kind=discovery scope=plan id=p3-trivy-server-port created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-trivy-server-port · discovery · Built-in Trivy server is trivy-service.trivy-system:4954 and is a StatefulSet with a 5Gi PVC (phase 3)

Confirmed by helm template of chart 0.38.1 (app 0.36.1). The PVC makes the app stateful in the facts, so update-policy.yaml resolves frank/trivy-operator to session. The chart also renders OCI repo strings (trivy-db, trivy-java-db, trivy-checks:1, trivy repository) into a ConfigMap; those are data artifacts / joined-at-runtime fields and are registered as static exemptions in render_all_images.py with reasons.

<!-- fr:journal kind=discovery scope=plan id=p3-headscale-acl-still-wildcard created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-headscale-acl-still-wildcard · discovery · Headscale ACL edit records the grant but the wildcard accept still allows everything (phase 3)

Added one acl entry (tag:frank-updater -> tag:hop-node:6443,50000) and tagOwners for tag:frank-updater and tag:hop-node; the existing accept-all rule is untouched (test pins it), so the grant is not yet restrictive. It becomes effective the day the wildcard is tightened. MANUAL (phase 7): (1) kubectl -n headscale-system rollout restart deploy/headscale after the ConfigMap lands, gating on live ConfigMap content (headscale-config never rolls); (2) hop-1 must carry tag:hop-node (advertise-tags on its tailscale DaemonSet or retag in Headplane); (3) mint an ephemeral reusable pre-auth key for tag:frank-updater into Secret frank-updater-tailscale/authkey in ns hop-scan; (4) a read-only kubeconfig for Hop (server = hop-1 tailnet IP:6443) into Secret hop-readonly-kubeconfig key `config` in ns hop-scan; (5) allow the hop-scan pod to reach Talos/kube APIs only if the cluster-wide wildcard is ever removed.

<!-- fr:journal kind=discovery scope=plan id=p3-hop-scan-contract created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-hop-scan-contract · discovery · hop-scan stdout contract for the console (phase 3)

Per distinct image: `hop-scan result {json}` with keys cluster (hop), image, scanned_at (UTC ISO), critical/high/medium/low/unknown (int, or null on failure) and error (null or reason). Every run also prints `hop-scan heartbeat {json}` (cluster, at, status, images, scanned, failed) even when blind (status `skipped: no hop-readonly-kubeconfig` / `skipped: hop kube API unreachable`). Daily 03:17 UTC. Frank-side Grafana rule life-hop-scan-heartbeat-stale watches the heartbeat in VictoriaLogs (namespace hop-scan, _msg field).

<!-- fr:journal kind=discovery scope=plan id=p3-grafana-rules-metric-absent created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-grafana-rules-metric-absent · discovery · Metric dead-man rules read `or vector(1e9)` so a vanished console metric fires (phase 3)

life-scan-heartbeat-stale and life-report-heartbeat-stale (36h, feature-health, health_bridge_only, severity critical, NOT telegram_direct) compute time()-max(metric) or vector(1e9) with noDataState Alerting. life-hop-scan-heartbeat-stale is LogsQL stats with noDataState OK. Dashboard grafana-life-dashboard is mounted via two new entries in apps/victoria-metrics/values.yaml. Console alarms remain the only alarm source.

<!-- fr:journal kind=discovery scope=plan id=p3-hop-scan-unverified created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-hop-scan-unverified · discovery · hop-scan pod behaviour verified only offline (phase 3)

Not run on a cluster: native-sidecar tailscale in userspace as uid 65532 with TS_STATE_DIR=/tmp/tailscale, kubectl over socks5 HTTPS_PROXY (Go honours socks5), and trivy client pulling images from registries (needs egress 443, allowed). Confirm in phase 7 when the Secrets exist. report.py was exercised with a synthetic trivy JSON.

<!-- fr:journal kind=decision scope=plan id=p3-sec-fixes created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-sec-fixes · decision · Security review fixes p3-sec-1..4 (phase 3)

(1) tag:frank-updater and tag:hop-node are owned by group:tag-admins (sole member: dedicated Headscale user tag-admin, never used to register nodes; default is not a member); the frank-updater auth key must be ephemeral, single-use and pre-tagged. (2) scan only runs on image lines matching an image-reference regex, with `--` before the image. (3) tailscale has its own emptyDir ts-state (TS_STATE_DIR, TS_SOCKET), uid 65531, mounted only there; scan uses scan-tmp and uid 65534. (4) Trivy server token: trivy.existingSecret=true; ingress NetworkPolicy trivy-server-ingress admits only scan-job pods (label trivy-operator.scan-job=true), the operator and namespace hop-scan on 4954.

<!-- fr:journal kind=discovery scope=plan id=p3-phase7-trivy-token created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-phase7-trivy-token · discovery · Phase 7: create the Trivy token Secrets (the app is unhealthy until they exist) (phase 3)

Generate one random token T. (a) ns trivy-system Secret `trivy-operator-trivy-config` with keys trivy.serverToken=T and TRIVY_TOKEN=T (the chart no longer renders this Secret; the server's envFrom and the scan jobs are non-optional, so trivy-server and the operator sit in CreateContainerConfigError until it exists). (b) ns hop-scan Secret `trivy-server-token` key `token`=T (optional on the pod; without it hop-scan scans fail and the heartbeat reports failed>0). Also the tailscale/kubeconfig Secrets listed in p3-headscale-acl-still-wildcard.

<!-- fr:journal kind=discovery scope=plan id=p3-phase7-tag-admin created=2026-11-01T05:40:44+00:00 phase=3 -->
### p3-phase7-tag-admin · discovery · Phase 7 manual operation: tag-admin user, tagged keys, headscale restart (phase 3)

1) headscale users create tag-admin (operator only; never register nodes under it except via tagged keys). 2) Mint the frank-updater pre-auth key under tag-admin: headscale preauthkeys create --user tag-admin --ephemeral --tags tag:frank-updater --expiration 24h (single-use, i.e. no --reusable), into Secret frank-updater-tailscale/authkey in ns hop-scan. 3) Give hop-1 tag:hop-node via that user (headscale nodes tag -i <hop-1 id> -t tag:hop-node, or re-register with a tag-admin key). 4) After the ConfigMap lands, gate on live content (kubectl -n headscale-system get cm headscale-config -o jsonpath='{.data.acl\.yaml}' | grep tag-admin) THEN kubectl -n headscale-system rollout restart deploy/headscale (config never rolls).

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t1 created=2026-11-01T05:40:44+00:00 phase=3 -->
### no-refactor-p3-t1 · discovery · no-refactor-because P3.T1 (phase 3)

new app, values written once against the chart's own keys; nothing duplicated to tidy

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t2 created=2026-11-01T05:40:44+00:00 phase=3 -->
### no-refactor-p3-t2 · discovery · no-refactor-because P3.T2 (phase 3)

one ACL edit and one small app; the report script is the only logic and has no twin

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p3-t3 created=2026-11-01T05:40:44+00:00 phase=3 -->
### no-refactor-p3-t3 · discovery · no-refactor-because P3.T3 (phase 3)

dashboard JSON generated once; rules reuse the existing group/rule shapes verbatim

<!-- fr:journal kind=finding scope=plan id=p3-r1 created=2026-11-01T05:43:45+00:00 phase=3 state=open review_scope=in -->
### p3-r1 · finding [open] (reviewer: in scope) · Headscale ACL restricts nothing: the existing *:* wildcard still lets tag:frank-updater reach everything; port 50000 not needed (phase 3)

<!-- fr:journal kind=finding scope=plan id=p3-r2 created=2026-11-01T05:43:49+00:00 phase=3 state=open review_scope=in -->
### p3-r2 · finding [open] (reviewer: in scope) · Pre-auth key described as ephemeral single-use cannot serve a daily CronJob registering a fresh node each run (phase 3)

<!-- fr:journal kind=finding scope=plan id=p3-r3 created=2026-11-01T05:43:53+00:00 phase=3 state=open review_scope=in -->
### p3-r3 · finding [open] (reviewer: in scope) · hop-scan heartbeat rule accepts status=skipped / scanned=0, so a blind scanner never alarms (phase 3)

<!-- fr:journal kind=finding scope=plan id=p3-r4 created=2026-11-01T05:43:57+00:00 phase=3 state=open review_scope=in -->
### p3-r4 · finding [open] (reviewer: in scope) · Phase 7 omits creating headscale user tag-admin and tagging hop-1 tag:hop-node; missing user may break policy load (phase 3)

<!-- fr:journal kind=finding scope=plan id=p3-r5 created=2026-11-01T05:44:01+00:00 phase=3 state=open review_scope=in -->
### p3-r5 · finding [open] (reviewer: in scope) · No captured trivy-output fixture/report.py test and no helm render check of chart keys and the trivy-server pod label (phase 3)

<!-- fr:journal kind=finding scope=plan id=p3-r6 created=2026-11-01T05:44:05+00:00 phase=3 state=open review_scope=in -->
### p3-r6 · finding [open] (reviewer: in scope) · Scan loop lacks </dev/null, token on the command line, job deadline can kill the pod before the heartbeat (phase 3)

<!-- fr:journal kind=finding scope=plan id=p3-r7 created=2026-11-01T05:44:09+00:00 phase=3 state=open review_scope=out -->
### p3-r7 · finding [open] (reviewer: out of scope) · trivy-server-token and trivy-operator-trivy-config are two hand-created Secrets with no sync (phase 3)

<!-- fr:journal kind=discovery scope=plan id=p3-r2-r4-headscale-facts created=2026-11-01T05:50:29+00:00 phase=3 -->
### p3-r2-r4-headscale-facts · discovery · Headscale key is reusable+ephemeral (supersedes single-use); unknown user in policy loads (phase 3)

The frank-updater pre-auth key is reusable + ephemeral + pre-tagged, short expiry (720h), rotated: a daily CronJob registers a fresh node each run, so single-use cannot work (supersedes the earlier p3-phase7-tag-admin wording). Headscale v0.25.1 hscontrol/policy/acls.go read from source (not run live): expandUsersFromGroup returns member strings unvalidated and filterNodesByUser matches nothing for an unknown user, so a policy naming the not-yet-created user tag-admin loads. Ordering is still load-bearing for the CLI: the user must exist before preauthkeys create --user, and the restart goes last so the grant is effective only once key, tag and node exist. Blocks life-hop-headscale-{user,key,tag-hop1,apply} are in _prose.md; port 50000 dropped from the grant.

<!-- fr:journal kind=discovery scope=plan id=p4-console-contract-v2 created=2026-11-01T08:16:10+00:00 phase=4 -->
### p4-console-contract-v2 · discovery · Console contract v2 (cluster-update-fr#1 after review fixes) (phase 4)

Supersedes parts of p4-console-contract. Console runs single-writer: replicas 1, strategy Recreate. New env: SESSION_BOT_LOGIN (a THIRD, separate GitHub App for sessions; its token file 'github-token' lives under SESSION_SECRET_DIR), STATUS_CREATOR_LOGINS (the status bridge's GitHub identity; unset → nothing passes CI), plus session timing/cap vars listed in the console README. update-policy.yaml gains required_ci_contexts (default gitea-actions/*). Branch prefixes: cluster-update/session-<id>/ or -<id>- (session bot; separator being changed to avoid prefix collision — follow the console's final form) and cluster-update/revert- (console bot); the phase-7 ruleset must cover both. New endpoint POST /api/sessions/{id}/request-merge on 8081; ports unchanged (8080 UI from Traefik only, 9090 metrics, 8081 session API from upgrade-sessions only). RBAC: console needs get/list/create/delete on pods and secrets in upgrade-sessions, no RoleBindings; frank pre-binds session roles and denies pods/ephemeralcontainers.

<!-- fr:journal kind=discovery scope=plan id=p5-briefs-open-and-request created=2026-11-01T08:16:14+00:00 phase=5 -->
### p5-briefs-open-and-request · discovery · Briefs: sessions open PRs and request merge; never merge (phase 5)

Console contract: session briefs and AGENTS.md/CLAUDE.md must instruct the agent to open PRs on its session branch prefix and call POST /api/sessions/{id}/request-merge, then wait for the operator's click in the console — never merge, never push to main. Test the brief templates for that wording.

<!-- fr:journal kind=review scope=plan id=p3-review created=2026-11-01T08:24:10+00:00 phase=3 -->
### p3-review · review · Phase 3 independent review: 7 findings (6 in, 1 out) (phase 3)

Reviewer raised p3-r1..p3-r7. All six in-scope findings fixed with tests (146 passed, 1 skipped). p3-r1 needed an operator decision (confine only the new tag), applied. p3-r7 out of scope: the two token Secrets are created together from one source by the phase-7 manual op.

<!-- fr:journal kind=finding scope=plan id=p3-r1-resolved created=2026-11-01T08:24:10+00:00 phase=3 state=fixed resolves=p3-r1 -->
### p3-r1-resolved · finding [fixed] · resolves p3-r1: Headscale ACL restricts nothing: the existing *:* wildcard still lets tag:frank-updater reach everything; port 50000 not needed (phase 3)

Operator decision: wildcard src narrowed to default + tag:subnet-router + tag:hop-node (everyone who had it, incl. hop-1 once tagged), so only tag:frank-updater is confined to tag:hop-node:6443; port 50000 dropped; test asserts the source set and that no other rule matches the new tag.

<!-- fr:journal kind=finding scope=plan id=p3-r2-resolved created=2026-11-01T08:24:10+00:00 phase=3 state=fixed resolves=p3-r2 -->
### p3-r2-resolved · finding [fixed] · resolves p3-r2: Pre-auth key described as ephemeral single-use cannot serve a daily CronJob registering a fresh node each run (phase 3)

Key is reusable + ephemeral + pre-tagged, short expiry, rotated; comment, phase-7 note and test updated.

<!-- fr:journal kind=finding scope=plan id=p3-r3-resolved created=2026-11-01T08:24:10+00:00 phase=3 state=fixed resolves=p3-r3 -->
### p3-r3-resolved · finding [fixed] · resolves p3-r3: hop-scan heartbeat rule accepts status=skipped / scanned=0, so a blind scanner never alarms (phase 3)

Dead-man counts only healthy heartbeats (status ok, scanned>0); new health-bridge-only rule on unhealthy heartbeats; tested on report.py's real output.

<!-- fr:journal kind=finding scope=plan id=p3-r4-resolved created=2026-11-01T08:24:10+00:00 phase=3 state=fixed resolves=p3-r4 -->
### p3-r4-resolved · finding [fixed] · resolves p3-r4: Phase 7 omits creating headscale user tag-admin and tagging hop-1 tag:hop-node; missing user may break policy load (phase 3)

Four ordered manual-operation blocks in phase 7 (user, key, tag hop-1, apply+restart gated on live CM); Headscale 0.25.1 loads a policy naming a missing user, ordering still load-bearing.

<!-- fr:journal kind=finding scope=plan id=p3-r5-resolved created=2026-11-01T08:24:10+00:00 phase=3 state=fixed resolves=p3-r5 -->
### p3-r5-resolved · finding [fixed] · resolves p3-r5: No captured trivy-output fixture/report.py test and no helm render check of chart keys and the trivy-server pod label (phase 3)

Trivy's own golden JSON as fixture for report.py incl. error rows; chart-render contract test (pod label, metrics port, token keys), fails under CI=true when offline.

<!-- fr:journal kind=finding scope=plan id=p3-r6-resolved created=2026-11-01T08:24:10+00:00 phase=3 state=fixed resolves=p3-r6 -->
### p3-r6-resolved · finding [fixed] · resolves p3-r6: Scan loop lacks </dev/null, token on the command line, job deadline can kill the pod before the heartbeat (phase 3)

</dev/null in the loop, token only via TRIVY_TOKEN env, 2100s scan budget with 5m per image inside the 3000s deadline; behavioural test with a fake trivy.

<!-- fr:journal kind=finding scope=plan id=p3-r7-resolved created=2026-11-01T08:24:10+00:00 phase=3 state=open resolves=p3-r7 out_of_scope=true -->
### p3-r7-resolved · finding [out-of-scope] · resolves p3-r7: trivy-server-token and trivy-operator-trivy-config are two hand-created Secrets with no sync (phase 3)

Not caused by this phase's manifests: the trailing manual phase creates both token Secrets from one source value.

<!-- fr:journal kind=discovery scope=plan id=p5-session-branch-format created=2026-11-01T08:41:19+00:00 phase=5 -->
### p5-session-branch-format · discovery · Session branch format is cluster-update/session-<id>/<topic> (phase 5)

Final console contract (cluster-update-fr#1 @ a830849): session PR branches are cluster-update/session-<upgrade-id>/<topic> ('/' cannot occur in an id, so prefixes never overlap; ids may contain '-' and '.', e.g. frank-os-talos-1.13.4). Briefs and AGENTS.md must use this exact form; the phase-7 ruleset pattern cluster-update/session-** is unchanged. Revert branches cluster-update/revert-<n>-* are console-bot only.

<!-- fr:journal kind=discovery scope=plan id=p5-briefs-verified-commits created=2026-11-01T08:55:23+00:00 phase=5 -->
### p5-briefs-verified-commits · discovery · Briefs: commit through the GitHub API so commits are verified; session App gets no PR-body edits beyond its own (phase 5)

Console delta review c1d-r6/r3/r11: (1) session briefs must tell the agent to create commits through the GitHub API (contents API or GraphQL createCommitOnBranch) on cluster-update/session-<id>/<topic> — a plain git push yields unsigned commits the console refuses; (2) the session App's permissions should be the minimum: contents write + pull_requests write on derio-net/frank only (the console no longer trusts PR bodies for classification, but keep scope minimal); (3) sessions share one App credential, so branch ownership is a naming rule — the phase-7 ruleset restricting session-** pushes to the session App is the boundary, and the console's per-session scope + SHA pin bound the damage. Test the brief templates for the API-commit instruction and the '/' branch form.

<!-- fr:journal kind=discovery scope=plan id=p4-image-pins created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-image-pins · discovery · Console image is the tag v0.1.0; phase 7 must replace it with the published digest (phase 4)

apps/cluster-update-fr/manifests/deployment.yaml pins ghcr.io/derio-net/cluster-update-fr:v0.1.0 because the first release is unpublished. PHASE 7: take the @sha256: digest from the v0.1.0 release notes and replace the tag (the console README says release tags are semver; verify whether the published tag carries the v prefix). runs-fr is chart v0.3.0 (git tag) with image ghcr.io/derio-net/runs-fr:0.3.0 in apps/runs-fr/values.yaml, also tag-pinned, digest not looked up. The runs-fr image is invisible to the render audit and to Renovate because the chart is remote (app-facts lists images: []); a version bump of runs-fr is therefore a manual edit of two lines (template targetRevision + values tag) until Renovate learns that file.

<!-- fr:journal kind=discovery scope=plan id=p4-trust-config-empty created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-trust-config-empty · discovery · Trust config is EMPTY, not a placeholder (phase 4)

The console treats an unset RENOVATE_BOT_LOGIN / CONSOLE_BOT_LOGIN / SESSION_BOT_LOGIN / STATUS_CREATOR_LOGINS as trust nothing. A literal placeholder string would be a valid GitHub login that anyone could register and be trusted, so apps/cluster-update-fr/manifests/files/console.env leaves them empty and a test pins that. Branch prefixes are built into the console (the final README has no env for them); required_ci_contexts lives in update-policy.yaml (added: gitea-actions/*). The ClusterGenerators DO use PENDING-MANUAL-PHASE for appID/installID: that makes minting fail loudly, which is the safe direction.

<!-- fr:journal kind=discovery scope=plan id=p4-upgrade-sessions-ns-dependency created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-upgrade-sessions-ns-dependency · discovery · Roles in upgrade-sessions need the namespace from phase 5 (phase 4)

The console Role/RoleBinding (pods+secrets get/list/create/delete) and runs-fr's chart Role/RoleBinding (pods get/list/watch + pods/exec create) are namespaced to upgrade-sessions, which the upgrade-sessions app (phase 5) creates. Until it exists those objects cannot sync. Phases ship in one PR so the order resolves at merge; if phase 4 were ever applied alone, create the namespace first. The console's role deliberately has no watch, no patch/update, no rolebindings and no pods/exec; frank pre-binds the per-type session roles (phase 5).

<!-- fr:journal kind=discovery scope=plan id=p4-omni-sidecar-deferred created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-omni-sidecar-deferred · discovery · Omni version sidecar is not deployed; OMNI_STATUS_FILE points at an empty dir (phase 4)

The contract wants a Reader-role omnictl sidecar writing {"version": ...} to OMNI_STATUS_FILE (/var/run/omni-status/status.json, an emptyDir). The image known to carry omnictl is the upgrade-session image, whose tag phase 5 produces, so the sidecar is not in this phase; until it is added the file is absent and the console shows Omni's version as unknown (assumed from the README, not tested). Add the sidecar once SESSION_IMAGE is pinned (phase 5/7), or point the console at a different source.

<!-- fr:journal kind=decision scope=plan id=p4-runs-fr-role-header created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-runs-fr-role-header · decision · runs-fr AUTH_ROLE_HEADER is X-authentik-meta-provider so a client cannot assert owner (phase 4)

runs-fr gates node shells on role == owner read from a header the proxy must OVERWRITE. Traefik forwardAuth copies only authResponseHeaders onto the request, so the default X-Forwarded-Role would pass a client-supplied value straight through. Authentik sets no role, so the header is pointed at one the outpost always sets to the provider name; it can never equal owner and node shells stay off. A test requires the header to be in the middleware's authResponseHeaders. The Role in upgrade-sessions could not open node shells anyway.

<!-- fr:journal kind=decision scope=plan id=p4-ingress-lockdown created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-ingress-lockdown · decision · CiliumNetworkPolicy on the console and runs-fr; chart NetworkPolicy off; no siteMonitor tiles (phase 4)

Console: 8080 from Traefik pods (traefik-system, app.kubernetes.io/name=traefik), 9090 from vmagent (monitoring, app.kubernetes.io/name=vmagent), 8081 from namespace upgrade-sessions; nothing else, no entities/CIDR. Metrics are scraped by a VMPodScrape because no Service exposes 9090. runs-fr: 8080 from Traefik only; the chart's own NetworkPolicy is left off so there is one statement of the rule. Because of this the smoke checks are exec-probes (an HTTP probe from the verifier would be refused) and the homepage tiles carry no siteMonitor. UNVERIFIED on a cluster: the vmagent and Traefik pod labels (assumed standard) and that kubelet probes still pass; if the console scrape is down after sync, check the vmagent labels first.

<!-- fr:journal kind=discovery scope=plan id=p4-authentik-unverified created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-authentik-unverified · discovery · Authentik JWT contract is unverified: client_id, signing key, groups claim (phase 4)

The blueprint sets client_id: cluster-update-console, signing_key (the self-signed cert pair, so the JWT is RS256), and the openid/email/profile mappings on the console provider, and a policy binding of both applications to the group root-admins. The console config expects issuer https://auth.cluster.derio.net/application/o/updates-cluster/, JWKS .../jwks/, audience cluster-update-console, OPERATOR_GROUP root-admins. Not observed: whether Authentik honours an explicit client_id on a proxy provider, the exact iss, and whether `groups` is in the forwarded JWT. PHASE 7: after assigning the provider to the embedded outpost, decode one real X-authentik-jwt and compare.

<!-- fr:journal kind=discovery scope=plan id=p4-phase7-manual-ops created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-phase7-manual-ops · discovery · Phase 7 manual steps this phase creates (phase 4)

1) Authentik: add BOTH providers (Cluster Update Console (cluster), Upgrade Sessions (cluster)) to the embedded outpost via the Django ORM step in agents/rules/frank-argocd.md. 2) GitHub Apps: renovate, console (contents/PRs/statuses/issues/webhooks write, metadata read), and the third SESSION App (contents+PRs write only, frank only); PEMs into ns cluster-update-fr as github-app-cluster-update-console-key and github-app-cluster-update-session-key (key `key`); replace PENDING-MANUAL-PHASE appID/installID in apps/cluster-update-fr/manifests/clustergenerators.yaml. 3) Fill RENOVATE_BOT_LOGIN, CONSOLE_BOT_LOGIN, SESSION_BOT_LOGIN and STATUS_CREATOR_LOGINS (the status bridge's GitHub identity, i.e. who github-status posts as) in console.env; SESSION_IMAGE when phase 5 publishes it. 4) Infisical keys: FRANK_UPDATER_TELEGRAM_BOT_TOKEN, FRANK_UPDATER_TELEGRAM_CHAT_ID, FRANK_UPDATER_TELEGRAM_SECURITY_THREAD_ID, FRANK_UPDATER_GITEA_TOKEN (key names chosen here, not found in Infisical). 5) Secrets applied out of band in ns cluster-update-fr: frank-updater-tailscale/authkey (the same reusable ephemeral tag:frank-updater key as hop-scan), hop-readonly-kubeconfig/config (its cluster entry needs `proxy-url: socks5://localhost:1055`; hop-scan instead uses HTTPS_PROXY), cluster-update-session-omni/key, -talos/talosconfig, -hop-talos/talosconfig, -hop-kube/config. 6) Mirror, trigger-first: this PR already puts derio-net/cluster-update-fr in the gitea-status-bridge allowlist, derio-net-main-sync/pr-sync, mirror-reconcile, ci-delivery-check and the derio-net mirror token generator; THEN create the Gitea mirror repo, make sure the derio-fr-automation App installation includes the repo, and create the GitHub push+pull_request webhook LAST (declared in apps/tekton/webhooks.yaml). 7) The branch ruleset on frank must cover cluster-update/batch-, cluster-update/revert- and cluster-update/session-<id>/.

<!-- fr:journal kind=discovery scope=plan id=p4-mirror-surface created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-mirror-surface · discovery · Onboarding a derio-net mirror touches ten places, and a blanket replace hit a wrong one (phase 4)

derio-net/cluster-update-fr was added next to runs-fr in: eventlistener.yaml (status bridge), eventlistener-github.yaml (derio-net-main-sync, derio-net-pr-sync), mirror-reconcile.yaml (2 stages x 2 lists), ci-delivery-check.yaml (2 lists), the derio-net mirror ClusterGenerator, ci-budget tiers + clustergenerators (tier github-preferred), webhooks.yaml, and two test lists. A first sed-style replace also rewrote the staging-gate-runs-fr repository_dispatch trigger (and its comment); test_webhook_delivery_paths caught it and it was reverted by hand.

<!-- fr:journal kind=discovery scope=plan id=p4-console-approved-check created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-console-approved-check · discovery · Console contract: post cluster-update/approved on the head SHA right before merging (phase 4)

The main ruleset (manual op life-main-ruleset, new step P7.T1.S5) requires a PR and a status check `cluster-update/approved` whose expected source is the CONSOLE App; bypass actors are the operator and the console App only. So the console must post `cluster-update/approved` (state success) on the PR head SHA immediately before it merges, or merge as a bypass actor. The session App and Renovate App can open PRs but cannot push to main or satisfy the check. RELAY to the cluster-update-fr repo. The ruleset also has to exist before the session App is installed (clustergenerators.yaml says so).

<!-- fr:journal kind=decision scope=plan id=p4-sec-1 created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-sec-1 · decision · Session App comment corrected; main ruleset added to phase 7 (phase 4)

The old comment claimed the session App cannot merge; it holds contents:write and could push to main. The comment now names the real control (a GitHub ruleset, manual, phase 7) and 07.yaml has step P7.T1.S5 + manual-operation block life-main-ruleset in _prose.md. Not run live.

<!-- fr:journal kind=decision scope=plan id=p4-sec-2 created=2026-11-01T09:32:28+00:00 phase=4 -->
### p4-sec-2 · decision · ValidatingAdmissionPolicies bound to upgrade-sessions confine console-created pods (phase 4)

admission-policy.yaml: for pods created/updated by the cluster-update-fr SA, only the five types, labels managed-by=cluster-update-fr + cluster-update.fr/type, serviceAccountName upgrade-session-<type> (default for hop-os), automountServiceAccountToken true except hop-os, image ghcr.io/derio-net/upgrade-session with a : or @sha256: delimiter, no ephemeral containers, host namespaces, hostPath, privileged or added capabilities (init containers included). A second policy denies pods/ephemeralcontainers for everyone outside system:masters and the OIDC group root-admins. failurePolicy Fail. Secrets/pods `list` kept for orphan reconciliation (documented in rbac.yaml). UNVERIFIED: the CEL was only checked structurally (no CEL engine offline); apply with a dry-run or a denied test pod in phase 7. If a console pod launch is refused, the message names the failed rule.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p4-t1 created=2026-11-01T09:32:28+00:00 phase=4 -->
### no-refactor-p4-t1 · discovery · no-refactor-because P4.T1 (phase 4)

new app written once against the console README contract; nothing duplicated to tidy

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p4-t2 created=2026-11-01T09:32:28+00:00 phase=4 -->
### no-refactor-p4-t2 · discovery · no-refactor-because P4.T2 (phase 4)

two route/provider/tile triples copied the existing per-service shape verbatim; no twin to merge

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p4-t3 created=2026-11-01T09:32:28+00:00 phase=4 -->
### no-refactor-p4-t3 · discovery · no-refactor-because P4.T3 (phase 4)

one values file and one policy; the chart supplies everything else

<!-- fr:journal kind=finding scope=plan id=p4-r1 created=2026-11-01T09:45:36+00:00 phase=4 state=open review_scope=in -->
### p4-r1 · finding [open] (reviewer: in scope) · Hop kubeconfig relies on proxy-url socks5 but the console kube client ignores proxy-url and has no Proxy func (phase 4)
