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

<!-- fr:journal kind=finding scope=plan id=p4-r2 created=2026-11-01T09:45:40+00:00 phase=4 state=open review_scope=in -->
### p4-r2 · finding [open] (reviewer: in scope) · required_ci_contexts gitea-actions/* can never be met: frank is not mirrored and its CI is GitHub Actions check-runs (phase 4)

<!-- fr:journal kind=finding scope=plan id=p4-r3 created=2026-11-01T09:45:44+00:00 phase=4 state=open review_scope=in -->
### p4-r3 · finding [open] (reviewer: in scope) · console can create service-account-token Secrets in upgrade-sessions and mint permanent session-SA tokens (phase 4)

<!-- fr:journal kind=finding scope=plan id=p4-r4 created=2026-11-01T09:45:49+00:00 phase=4 state=open review_scope=in -->
### p4-r4 · finding [open] (reviewer: in scope) · R24 Omni running version not delivered: omni-status emptyDir has no writer and no later step owns the sidecar (phase 4)

<!-- fr:journal kind=finding scope=plan id=p4-r5 created=2026-11-01T09:45:54+00:00 phase=4 state=open review_scope=in -->
### p4-r5 · finding [open] (reviewer: in scope) · phase 7 lacks manual-op blocks for digest pin, bot logins, SESSION_IMAGE, console-ns secrets, console mirror+webhook; session PEM namespace wrong (phase 4)

<!-- fr:journal kind=finding scope=plan id=p4-r6 created=2026-11-01T09:45:58+00:00 phase=4 state=open review_scope=in -->
### p4-r6 · finding [open] (reviewer: in scope) · ClusterRole grants apps/* and watch the console never uses; test pins the over-grant (phase 4)

<!-- fr:journal kind=finding scope=plan id=p4-r7 created=2026-11-01T09:46:03+00:00 phase=4 state=open review_scope=in -->
### p4-r7 · finding [open] (reviewer: in scope) · admission-policy tests are substring checks, not CEL evaluation against good/hostile pods (phase 4)

<!-- fr:journal kind=finding scope=plan id=p4-r8 created=2026-11-01T09:46:08+00:00 phase=4 state=open review_scope=in -->
### p4-r8 · finding [open] (reviewer: in scope) · state PVC/namespace have Prune=false but not Delete=false; Application deletion loses the audit trail (phase 4)

<!-- fr:journal kind=finding scope=plan id=p4-r9 created=2026-11-01T09:46:13+00:00 phase=4 state=open review_scope=in -->
### p4-r9 · finding [open] (reviewer: in scope) · console SA token (with write rights) is automounted into the tailscale sidecar (phase 4)

<!-- fr:journal kind=finding scope=plan id=p4-r10 created=2026-11-01T09:46:17+00:00 phase=4 state=open review_scope=out -->
### p4-r10 · finding [open] (reviewer: out of scope) · admission policy allows any upgrade-session tag; bind the exact digest once SESSION_IMAGE is pinned (phase 4)

<!-- fr:journal kind=discovery scope=plan id=p4-review-fixes-notes created=2026-11-01T09:57:34+00:00 phase=4 -->
### p4-review-fixes-notes · discovery · Review fixes p4-r1..r9: what is unverified or owed (phase 4)

(1) Admission CEL evaluated with cel-python 0.5.0 in a scratch Python 3.12 venv (does not build on 3.14); test_life_admission_cel.py skips where celpy is absent and manual op life-admission-dry-run is the server-side check. cel-python turns bools into ints inside macros over nested maps, so the harness counts an evaluation error as a denial (as the API server does) and the privileged check is written == false. (2) frank's required check is the job name tripwires (Repo Tripwires, the only workflow with no pull_request paths filter); verify the exact check-run name on a real PR in phase 7. (3) omni-status writes omnictl's raw get sysversion -o json (console accepts spec.backendversion); omnictl on PATH and OMNICONFIG support in the upgrade-session image are unverified. Its image tag is PENDING-PHASE-7: the pod is NotReady until life-console-pins replaces it, which must happen before merging frank. (4) /sync-runbook is OWED: the new life-main-ruleset and life-console-*/life-admission-dry-run blocks are in _prose.md but docs/runbooks/manual-operations.yaml was not regenerated. (5) r6: ClusterRole is get/list on pods, nodes, applications, rollouts, vulnerabilityreports only (grepped internal/live/live.go). (6) r8 and r9 share one commit. (7) The record file was already resolved, so these notes went through fr journal add.

<!-- fr:journal kind=decision scope=plan id=p4-r2-checks-shape created=2026-11-01T10:14:34+00:00 phase=4 -->
### p4-r2-checks-shape · decision · required_ci_checks pins each check to its workflow file; token permissions (phase 4)

update-policy.yaml required_ci_checks is a list of {workflow, name}; tested that the file exists, a job renders that check-run name, it runs on pull_request and is not path-filtered or conditional. Console App permissions checks:read + actions:write (write includes read; the generator cannot list actions twice) are in the generator and in P7.T1.S2. Workflow permissions: every frank workflow already limited its token except agent-config.yml, which inherited the default; I added permissions: contents: read there (it only checks out and runs a script). A test now requires every workflow to set permissions and none to grant checks: write.

<!-- fr:journal kind=review scope=plan id=p4-review created=2026-11-01T10:28:24+00:00 phase=4 -->
### p4-review · review · Phase 4 independent review: 10 findings (9 in, 1 out) (phase 4)

Reviewer raised p4-r1..p4-r10, incl. two criticals at the frank/console contract boundary (SOCKS proxy unsupported; CI source assumed Gitea). Both fixed on both sides; spec corrected. All 9 in-scope findings fixed with tests (260 passed, 2 skipped + 30 CEL tests in a scratch venv). p4-r10 out of scope until SESSION_IMAGE is pinned in phase 7.

<!-- fr:journal kind=finding scope=plan id=p4-r1-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r1 -->
### p4-r1-resolved · finding [fixed] · resolves p4-r1: Hop kubeconfig relies on proxy-url socks5 but the console kube client ignores proxy-url and has no Proxy func (phase 4)

Hop kubeconfig keeps proxy-url socks5://localhost:1055; console (cluster-update-fr@ce85584) now supports socks5 proxy-url; frank test pins the shared mechanism and the sidecar's SOCKS5 port.

<!-- fr:journal kind=finding scope=plan id=p4-r2-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r2 -->
### p4-r2-resolved · finding [fixed] · resolves p4-r2: required_ci_contexts gitea-actions/* can never be met: frank is not mirrored and its CI is GitHub Actions check-runs (phase 4)

Spec corrected: frank's CI gate is GitHub check-runs; update-policy declares ci_source github-checks and required_ci_checks [{workflow: .github/workflows/repo-tripwires.yml, name: tripwires}] (verified on PR #906); every workflow declares permissions, none grants checks:write; console binds checks to the declared workflow file.

<!-- fr:journal kind=finding scope=plan id=p4-r3-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r3 -->
### p4-r3-resolved · finding [fixed] · resolves p4-r3: console can create service-account-token Secrets in upgrade-sessions and mint permanent session-SA tokens (phase 4)

ValidatingAdmissionPolicy on secrets for the console SA: Opaque only, us- prefix, managed-by label, no service-account.name annotation; CEL evaluated with cel-python.

<!-- fr:journal kind=finding scope=plan id=p4-r4-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r4 -->
### p4-r4-resolved · finding [fixed] · resolves p4-r4: R24 Omni running version not delivered: omni-status emptyDir has no writer and no later step owns the sidecar (phase 4)

omni-status sidecar (upgrade-session image, Reader SA, own emptyDir) writes the version file the console reads; image pinned in phase 7 step life-console-pins.

<!-- fr:journal kind=finding scope=plan id=p4-r5-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r5 -->
### p4-r5-resolved · finding [fixed] · resolves p4-r5: phase 7 lacks manual-op blocks for digest pin, bot logins, SESSION_IMAGE, console-ns secrets, console mirror+webhook; session PEM namespace wrong (phase 4)

Phase 7 gained life-console-pins/-trust/-secrets/-mirror/life-admission-dry-run blocks; session App PEM namespace corrected to cluster-update-fr.

<!-- fr:journal kind=finding scope=plan id=p4-r6-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r6 -->
### p4-r6-resolved · finding [fixed] · resolves p4-r6: ClusterRole grants apps/* and watch the console never uses; test pins the over-grant (phase 4)

ClusterRole reduced to what the console reads; test updated.

<!-- fr:journal kind=finding scope=plan id=p4-r7-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r7 -->
### p4-r7-resolved · finding [fixed] · resolves p4-r7: admission-policy tests are substring checks, not CEL evaluation against good/hostile pods (phase 4)

Admission CEL evaluated with a real CEL engine against legitimate pods of all five types and hostile pods/Secrets (30 passing); phase 7 adds a server-side dry run.

<!-- fr:journal kind=finding scope=plan id=p4-r8-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r8 -->
### p4-r8-resolved · finding [fixed] · resolves p4-r8: state PVC/namespace have Prune=false but not Delete=false; Application deletion loses the audit trail (phase 4)

State PVC and namespace carry Prune=false,Delete=false.

<!-- fr:journal kind=finding scope=plan id=p4-r9-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=fixed resolves=p4-r9 -->
### p4-r9-resolved · finding [fixed] · resolves p4-r9: console SA token (with write rights) is automounted into the tailscale sidecar (phase 4)

Pod-level token automount off; projected SA token mounted only in the console container.

<!-- fr:journal kind=finding scope=plan id=p4-r10-resolved created=2026-11-01T10:28:24+00:00 phase=4 state=open resolves=p4-r10 out_of_scope=true -->
### p4-r10-resolved · finding [out-of-scope] · resolves p4-r10: admission policy allows any upgrade-session tag; bind the exact digest once SESSION_IMAGE is pinned (phase 4)

Not caused by this change: the admission policy cannot name the exact session image digest until phase 7 publishes and pins it; bind it via paramRef then.

<!-- fr:journal kind=discovery scope=plan id=p5-tests-evidence-unattributed created=2026-11-01T12:15:23+00:00 phase=5 -->
### p5-tests-evidence-unattributed · discovery · Phase 5 suite ran green but fr could not attribute the log to the resumed executor (phase 5)

The executor (resumed via SendMessage) ran the suite with a plain > redirect after its last code commit 2fdf6cac: 636 passed, 2 skipped (CEL tests: 31 pass in a 3.12 venv). fr refused the evidence twice ('no command of the unit's holder wrote it'), most likely because a resumed subagent's later turns are not in the transcript fr reads. The record omits tests per fr's own guidance; deliver runs the full suite independently.

<!-- fr:journal kind=decision scope=plan id=p5-github-egress-residual created=2026-11-01T12:15:28+00:00 phase=5 -->
### p5-github-egress-residual · decision · Residual exfiltration via api.github.com with a planted token (phase 5)

Session egress allows api.github.com (commits through the contents API / GraphQL, PRs, reads of frank).
Cilium filters by name only: without TLS interception it cannot see paths or which repository a request
names, so an agent holding ANY other token (planted in untrusted data, or brought by a steered agent) could
write data to another repository through that API. github.com, gist/raw/upload hosts and claude.ai were
removed (p5-sec-3), so this is the one remaining path. Mitigations: the session App token is scoped to
derio-net/frank with contents+pull_requests only; the session is short-lived (idle timeout, max lifetime,
hard ceiling) and its pod and Secrets are deleted at the end; the transcript is scrubbed (two layers);
the operator is attached to every session. Also note frank itself is PUBLIC: anything pushed to a session
branch is world-readable, so even the in-scope token is an exfiltration path the network cannot close.
The brief templates and AGENTS.md state this in a Security note.

<!-- fr:journal kind=decision scope=plan id=p5-session-egress-allowlist created=2026-11-01T12:15:28+00:00 phase=5 -->
### p5-session-egress-allowlist · decision · Session egress is generated; target services are a smoke-check allowlist on pod ports (phase 5)

apps/upgrade-sessions/manifests/networkpolicies.yaml is generated by scripts/life_sessions.py (--write).
Default-deny (ingress and egress) plus an egressDeny on TCP 22 for every session; one egress policy per
type. Common to all: kube-dns with DNS rules answering ONLY the allowed names and their resolv.conf
search-domain forms (no `*`: a DNS proxy that answers everything is a tunnel), the documented hosts in
HOST_REASONS on 443, the kube API (6443), the console session API (cluster-update-fr :8081) and Gitea
HTTP (:3000). frank-os adds omni.frank.derio.net:443 and the seven node /32s on 50000; hop-os adds
headscale (443 + 3478/udp), derp*.tailscale.com and blog.derio.net (its public smoke target).
Target services (p5-sec-1): exactly the host:port pairs of the smoke files of the apps the type verifies
(VERIFIES table), minus NEVER_NAMESPACES (infisical, authentik, secure-agent-pod, hermes-agent-shell, agents,
cluster-update-fr, kube-system, longhorn-system, monitoring, retrieval, upgrade-sessions) and NEVER_PORTS
(22, 3306, 5432, 6379, 27017). Because Cilium matches the POD port after service translation, each target is
resolved to its backend port from the app's render into scripts/tests/fixtures/life/session-target-ports.yaml
(--resolve-ports; a slow test re-renders). Edit a smoke file and the drift test asks for --write.
UNVERIFIED on a cluster: DNS rules + toFQDNs on Cilium 1.17 (see the FQDN-LRU networking gotcha),
egressDeny precedence, and that the session image carries tailscale for hop-os at all.

<!-- fr:journal kind=discovery scope=plan id=p5-longhorn-snapshot-scope created=2026-11-01T12:15:28+00:00 phase=5 -->
### p5-longhorn-snapshot-scope · discovery · Longhorn Snapshot CRs live in longhorn-system, so the snapshot grant cannot be per app (phase 5)

snapshots.longhorn.io objects are created in longhorn-system whatever namespace owns the volume (the
paperclip runbook recipe), so upgrade-session-stateful gets create/get/list on them THERE, for any volume.
It holds no delete/update/restore, so the worst case is disk use. The per-app-namespace Roles grant get/list
on PVCs (to find the volume) and create on volumesnapshots.snapshot.storage.k8s.io, which is inert today:
Frank has no CSI snapshot controller or CRDs. If one is installed later, the per-app path becomes the
scoped one and the longhorn-system grant can go. Hop's stateful apps get no Frank-side grant (static
Hetzner PVs).

<!-- fr:journal kind=finding scope=plan id=p5-console-pod-env-mismatch created=2026-11-01T12:15:28+00:00 phase=5 state=open review_scope=out -->
### p5-console-pod-env-mismatch · finding [open] (reviewer: out of scope) · Console session pod env does not match the upgrade-session image interface (phase 5)

cluster-update-fr internal/session/launch.go sets HOME=/home/agent, CREDENTIALS_DIR=/run/credentials,
TALOSCTL_VERSION and KUBECTL_VERSION; the image (agent-images#171, p5-session-image-interface) expects
HOME /home/claude and selects clients from UPGRADE_TALOS_MINOR / UPGRADE_K8S_MINOR. The entrypoint's
selection therefore never runs. Frank's briefs run use-versions explicitly from TALOSCTL_VERSION /
KUBECTL_VERSION, so the session works if use-versions accepts those minors, but HOME and the mount paths
must agree. Relay to cluster-update-fr and agent-images. Frank also refuses `command:` on session pods now.

<!-- fr:journal kind=finding scope=plan id=p5-console-scrub-adjacent-github-token created=2026-11-01T12:15:28+00:00 phase=5 state=open review_scope=out -->
### p5-console-scrub-adjacent-github-token · finding [open] (reviewer: out of scope) · Console scrubber leaks the body of a second GitHub token adjacent with no separator (phase 5)

The RE2 pattern ((?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}) consumes the next token's 'ghs' prefix
("...A1b2ghs_Z9y8..."), so the second token's 36-char body survives (its prefix is gone, so no later pass
matches it). frank's life_scrub.py stops before the adjacent prefix with a lookahead
(test_adjacent_tokens_are_both_redacted). Relay: add an adjacent-no-separator github-token case to
testdata/scrub/cases.json and fix the console's pattern (bounded {36} plus a code-side boundary check).

<!-- fr:journal kind=finding scope=plan id=p5-session-network-scope-per-type created=2026-11-01T12:15:28+00:00 phase=5 state=open review_scope=out -->
### p5-session-network-scope-per-type · finding [open] (reviewer: out of scope) · Session target-service egress is per type, not per app (phase 5)

Session pods carry fr.run/id and cluster-update.fr/type but no app label, so a static policy cannot tell
a paperclip session from a zot session: every stateful session reaches the union of all stateful apps'
smoke targets. If the console labels pods cluster-update.fr/app=<app> (and the admission policy pins it),
scripts/life_sessions.py can generate one policy per app. Relay to cluster-update-fr.

<!-- fr:journal kind=finding scope=plan id=p5-staging-gate-generators-baseline created=2026-11-01T12:15:28+00:00 phase=5 state=fixed review_scope=in -->
### p5-staging-gate-generators-baseline · finding [fixed] (reviewer: in scope) · test_staging_gate_manifests failed on this branch's three new ClusterGenerators (phase 5)

test_no_unintended_cluster_generator_is_added reported github-app-cluster-update-console,
github-app-cluster-update-session and github-app-renovate (added by phases 2 and 4). Fixed in 2fdf6cac
(p5-staging-gate): all three are declared in BASELINE_GENERATORS with a reason each. The check itself is
unchanged (any other new generator still fails; github-app-derio must stay unscoped). The file is now
in the phase tests_log.

<!-- fr:journal kind=discovery scope=plan id=p5-scrub-shared-fixtures created=2026-11-01T12:15:28+00:00 phase=5 -->
### p5-scrub-shared-fixtures · discovery · life_scrub.py shares the console's fixtures; frank-only additions to relay (phase 5)

scripts/tests/fixtures/life/scrub-cases.json is a byte copy of derio-net/cluster-update-fr
testdata/scrub/cases.json at cc4bb5c; every shared pattern, benign and literal case passes. frank-local
cases in test_life_scrub.py: adjacent tokens with no separator, delimiters inside values, next-line YAML,
unterminated quotes, base64 at alignments 0/1/2, wrapped base64 (64/76/40 cols, CRLF, space/tab indent),
double base64, URL/JSON-escaped literals, reference-shaped values ({{ .x }}, ${X}, $(cmd)). frank-only
behaviour: references are never secrets; repository mode (the CI guard only) exempts secret NAMES
(no digits, flow collections parsed element by element, p5-sec-2). For the console plan: consider the
adjacency case and the reference exemption.

<!-- fr:journal kind=discovery scope=plan id=p5-cel-runs-in-ci created=2026-11-01T12:15:28+00:00 phase=5 -->
### p5-cel-runs-in-ci · discovery · cel-python joined the dev group for Python < 3.14; the CEL tests fail in CI without it (phase 5)

pyproject.toml dev group gains cel-python==0.5.0 for python_version < '3.14' (uv.lock updated). CI runs
3.12, so test_life_admission_cel.py now runs there and raises under CI=true if celpy is missing; the local
3.14 venv skips with a reason. 31 CEL tests pass in a 3.12 venv, including the new no-`command:` pod rule.

<!-- fr:journal kind=discovery scope=plan id=p5-no-pod-template-in-frank created=2026-11-01T12:15:28+00:00 phase=5 -->
### p5-no-pod-template-in-frank · discovery · Frank holds no session pod template; the admission policy enforces args-not-command (phase 5)

The console builds the session pod (launch.go podSpec), so frank cannot "use args not command" in a
template. Instead upgrade-session-pods (apps/cluster-update-fr/manifests/admission-policy.yaml) now refuses
any session container that sets `command:`, and every brief runs use-versions explicitly. upgrade-session
is in the agent-images bump AGENT_IMAGES list.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p5-t1 created=2026-11-01T12:15:28+00:00 phase=5 -->
### no-refactor-p5-t1 · discovery · no-refactor-because P5.T1 (phase 5)

the repeated parts (per-type egress, per-namespace Roles) were generated from one table in scripts/life_sessions.py from the start; the hand-written manifests are four short files with no twin to merge

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p5-t2 created=2026-11-01T12:15:28+00:00 phase=5 -->
### no-refactor-p5-t2 · discovery · no-refactor-because P5.T2 (phase 5)

the briefs are prose; the one shared block (use-versions + the security note) is identical text the console appends per type, and the console does no includes, so it cannot be factored out

<!-- fr:journal kind=discovery scope=plan id=p5-console-contract-tailscale created=2026-11-01T12:16:20+00:00 phase=5 -->
### p5-console-contract-tailscale · discovery · Console contract: SESSION_TAILSCALE_IMAGE + tailscale-authkey for hop-os (phase 5)

cluster-update-fr@d36ea1b: hop-os session pods get a userspace tailscale sidecar (own ts-state emptyDir, uid 65531, SOCKS5 localhost:1055, tag:frank-updater). Frank must set console config SESSION_TAILSCALE_IMAGE to a DIGEST-pinned tailscale image (hop-os refuses to start otherwise) and add key 'tailscale-authkey' (reusable ephemeral pre-tagged key) to the session Secret, kept out of the agent's credential volume; the upgrade-sessions egress policy for hop-os must allow the tailscale sidecar's control/DERP traffic (headscale.hop.derio.net + DERP) and the admission policy must allow that sidecar image. Phase 7 manual-op: pin the digest and add the key.

<!-- fr:journal kind=finding scope=plan id=p5-r1 created=2026-11-01T12:27:26+00:00 phase=5 state=open review_scope=in -->
### p5-r1 · finding [open] (reviewer: in scope) · admission policy denies the console's real hop-os pod (tailscale initContainer); CEL test uses a hand-made pod (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r2 created=2026-11-01T12:27:31+00:00 phase=5 state=open review_scope=in -->
### p5-r2 · finding [open] (reviewer: in scope) · hop-os contract not wired: no SESSION_TAILSCALE_IMAGE, no tailscale-authkey projection (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r3 created=2026-11-01T12:27:35+00:00 phase=5 state=open review_scope=in -->
### p5-r3 · finding [open] (reviewer: in scope) · hop-os cannot reach Hop Talos API; sessions share hop-scan's tag (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r4 created=2026-11-01T12:27:40+00:00 phase=5 state=open review_scope=out -->
### p5-r4 · finding [open] (reviewer: out of scope) · console sets socks5 HTTPS_PROXY/ALL_PROXY, likely unsupported by talosctl (grpc-go) and Claude Code (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r5 created=2026-11-01T12:27:45+00:00 phase=5 state=open review_scope=in -->
### p5-r5 · finding [open] (reviewer: in scope) · derp*.tailscale.com egress unnecessary and a public-relay exfil channel (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r6 created=2026-11-01T12:27:50+00:00 phase=5 state=open review_scope=in -->
### p5-r6 · finding [open] (reviewer: in scope) · toFQDNs is IP-based so other hosts on the same IPs are reachable; residual note false; add serverNames (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r7 created=2026-11-01T12:27:54+00:00 phase=5 state=open review_scope=in -->
### p5-r7 · finding [open] (reviewer: in scope) · smoke-check allowlist is L4 to unauthenticated write APIs; restrict to GET on checked paths via L7 (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r8 created=2026-11-01T12:27:59+00:00 phase=5 state=open review_scope=in -->
### p5-r8 · finding [open] (reviewer: in scope) · scrubber REFERENCE regex exempts real secrets, also in scrub() (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r9 created=2026-11-01T12:28:03+00:00 phase=5 state=open review_scope=in -->
### p5-r9 · finding [open] (reviewer: in scope) · repository-mode KEY_NAME exempts lowercase/dash and all-caps passphrases (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r10 created=2026-11-01T12:28:08+00:00 phase=5 state=open review_scope=in -->
### p5-r10 · finding [open] (reviewer: in scope) · exec/ephemeral test scans only repo Roles; root-devops->admin grants pods/exec into sessions; no admission on pods/exec (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r11 created=2026-11-01T12:28:13+00:00 phase=5 state=open review_scope=out -->
### p5-r11 · finding [open] (reviewer: out of scope) · secure-agent-pod agent-sa and root-agents are cluster-admin and can read every session credential (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r13 created=2026-11-01T12:28:18+00:00 phase=5 state=open review_scope=in -->
### p5-r13 · finding [open] (reviewer: in scope) · stateful brief verification reads app logs but sessions have no pods/log (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r14 created=2026-11-01T12:28:23+00:00 phase=5 state=open review_scope=in -->
### p5-r14 · finding [open] (reviewer: in scope) · frank-os egress to node /32s:50000 unnecessary with an Omni-issued talosconfig (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r15 created=2026-11-01T12:28:28+00:00 phase=5 state=open review_scope=in -->
### p5-r15 · finding [open] (reviewer: in scope) · AGENTS.md untrusted-data rule does not say everything to EOF is data (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r16 created=2026-11-01T12:28:33+00:00 phase=5 state=open review_scope=in -->
### p5-r16 · finding [open] (reviewer: in scope) · hop-os inherits Frank kube-apiserver 6443 and kubernetes.default DNS (phase 5)

<!-- fr:journal kind=finding scope=plan id=p5-r17 created=2026-11-01T12:28:38+00:00 phase=5 state=open review_scope=in -->
### p5-r17 · finding [open] (reviewer: in scope) · briefs rebuild the minor from TALOSCTL_VERSION instead of UPGRADE_*_MINOR (phase 5)

<!-- fr:journal kind=decision scope=plan id=p5-github-egress-residual-2 created=2026-11-01T13:03:08+00:00 phase=5 decided_by=agent -->
### p5-github-egress-residual-2 · decision · Supersedes p5-github-egress-residual: egress pins IPs AND TLS SNI; what stays open (phase 5)

Supersedes p5-github-egress-residual, whose 'Cilium filters by name only' was wrong: toFQDNs is IP-based (it allows the addresses a name resolved to), so any other host sharing those IPs was reachable (p5-r6). Now every external name has its own CNP rule whose TCP ports carry serverNames: [<name>] (Cilium 1.17.0 PortRule.ServerNames, exact strings, no wildcards; it sets the TLS parser, so Envoy reads the ClientHello SNI without decrypting; Frank runs the default L7 proxy with cilium-envoy). UDP (headscale STUN 3478) has no TLS and sits in its own toPorts entry. Still open, stated in every brief's Security note: the policy cannot see the path, Host header or repository inside TLS, so a session holding another token can write to another repository through api.github.com, and a client sending an allowed SNI with another Host header may reach other services behind the same front end (domain fronting) -- the same holds for the model-provider hosts. Bounds unchanged: session App token scoped to derio-net/frank contents+PRs, short-lived session, scrubbed transcript, attached operator; frank is public. Codex/OpenAI hosts (api.openai.com, auth.openai.com, chatgpt.com) stay allowed for every type: making them opt-in per session needs the console to declare the harness (a pod label the admission policy pins and a per-harness CNP), which it does not do today; relay to cluster-update-fr. UNVERIFIED on the cluster: SNI enforcement through Envoy on toFQDNs rules (life-admission-dry-run's companion check: curl --resolve api.github.com:443:<ip> https://other.host must fail).

<!-- fr:journal kind=discovery scope=plan id=p5-console-pod-env-superseded created=2026-11-01T13:40:12+00:00 phase=5 -->
### p5-console-pod-env-superseded · discovery · Supersedes p5-console-pod-env-mismatch: console and image agree on HOME and the client minors (phase 5)

p5-console-pod-env-mismatch is superseded. cluster-update-fr launch.go (537f208, golden testdata/podspec) now sets HOME=/home/claude and UPGRADE_TALOS_MINOR / UPGRADE_K8S_MINOR, already reduced by minorOf to minors the image ships (talos 1.12-1.14, k8s 1.34-1.37; defaults 1.12 / 1.35), matching the upgrade-session image interface (p5-session-image-interface). TALOSCTL_VERSION / KUBECTL_VERSION remain as informational env only. Frank's briefs and AGENTS.md section 1 now run use-versions --talos "$UPGRADE_TALOS_MINOR" --kubernetes "$UPGRADE_K8S_MINOR" (p5-r17; test_client_selection_uses_the_consoles_minors forbids the old form). The console still mounts credentials at /run/credentials (CREDENTIALS_DIR) and the briefs use $CREDENTIALS_DIR, so they agree. The old finding stays open in the log only as history; nothing is left to relay.

<!-- fr:journal kind=discovery scope=plan id=p5-review-fix-residuals created=2026-11-01T13:41:00+00:00 phase=5 -->
### p5-review-fix-residuals · discovery · p5 review fixes: what stays open and what only the cluster can prove (phase 5)

Residuals after p5-r1..r17. (1) p5-r7: listener-only tcp smoke checks keep plain L4 rules, so those pod ports stay open for any request: zot 5000 (registry, TLS), paperclip 3100, traefik 80, cnc-fru 80, awx metrics 8443, trivy 4954, the vcluster 443s. Giving any of them an http check in its smoke file turns it into an L7 GET-only rule on the next --write. (2) p5-r10: upgrade-session-no-exec also denies root-devops, root-agents and secure-agent-pod's agent-sa (all can exec by RBAC), but a cluster-admin can delete the policy; p5-r11 (cluster-admin agents read session Secrets) stays out of scope. (3) p5-r1: the pod fixtures are byte copies of cluster-update-fr 537f208 testdata/podspec (test_pod_fixtures_are_byte_copies_of_the_consoles_golden_files re-compares when the console worktree exists); the sidecar rule pins the eight TS_* variables exactly once, the loopback binds, and argv tokenized to exactly login-server, hostname frank-upgrade-<fr.run/id> and tag:frank-session, using Kubernetes CEL's ext.strings split (emulated in the offline tests). Only the API server is authoritative: life-admission-dry-run now lists the sidecar and exec cases. (4) Cluster-only proof still owed: Envoy enforcing serverNames on toFQDNs rules, the L7 http rules on the smoke ports (a POST to ollama /api/push must 403), the CONNECT policy, and hop-os reaching hop-1 6443/50000 through the sidecar after life-session-tailscale. (5) p5-r4 (console socks5 proxies, out of scope) stays open; the console now also serves HTTP CONNECT on localhost:1056 for talosctl.
