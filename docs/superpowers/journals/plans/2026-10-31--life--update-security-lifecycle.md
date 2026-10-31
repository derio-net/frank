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
