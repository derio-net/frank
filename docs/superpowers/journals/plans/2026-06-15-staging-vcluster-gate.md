# Journal: 2026-06-15-staging-vcluster-gate

<!-- fr:journal kind=discovery scope=plan id=nrb-p7t1 created=2026-09-14T22:34:25 -->
### nrb-p7t1 · discovery · no-refactor-because P7.T1

One list entry added to an existing exclusion plus a parametrized test; no duplication or structure to improve.

<!-- fr:journal kind=discovery scope=plan id=nrb-p7t2 created=2026-09-14T22:34:34 -->
### nrb-p7t2 · discovery · no-refactor-because P7.T2

Two key renames (server -> name) in two templates; nothing to restructure.

<!-- fr:journal kind=discovery scope=plan id=nrb-p7t3 created=2026-09-14T22:34:41 -->
### nrb-p7t3 · discovery · no-refactor-because P7.T3

A single new ExternalSecret copied from an established pattern; no existing code is reshaped.

<!-- fr:journal kind=discovery scope=plan id=nrb-p8t1 created=2026-09-14T22:34:48 -->
### nrb-p8t1 · discovery · no-refactor-because P8.T1

Schema key swap in a 60-line validator plus data files; the validator is already a flat REQUIRED table.

<!-- fr:journal kind=discovery scope=plan id=nrb-p9t1 created=2026-09-14T22:34:54 -->
### nrb-p9t1 · discovery · no-refactor-because P9.T1

Values addition + one Role; the kubeconfig-fetch step is shared through the refactor done in P8.T2.

<!-- fr:journal kind=discovery scope=plan id=nrb-p9t3 created=2026-09-14T22:35:02 -->
### nrb-p9t3 · discovery · no-refactor-because P9.T3

Adds one finally task and one guard step; no pre-existing duplication introduced.

<!-- fr:journal kind=decision scope=plan id=skeleton-override-2026-06-15-staging-vcluster-gate created=2026-09-14T22:35:04 -->
### skeleton-override-2026-06-15-staging-vcluster-gate · decision · Phase 1 carries no skeleton marker (predates the rule)

Phases 1-6 were executed and completed 2026-06-15, before the skeleton-marker lint existed. The walking-skeleton purpose is already met: CI (repo-tripwires, 776 passed / 1 xfailed on the rebased branch) runs the full tripwire suite on every push, and phases 7-10 extend that suite rather than introduce a new runtime. Re-marking a completed phase would rewrite history, not add a smoke.

<!-- fr:journal kind=discovery scope=plan id=nrb-p10t1 created=2026-09-14T22:35:10 -->
### nrb-p10t1 · discovery · no-refactor-because P10.T1

Trigger, ExternalSecret and declaration each copy an adjacent precedent verbatim in shape; the tripwires own consistency.

<!-- fr:journal kind=discovery scope=plan id=replan-p5t3s3 created=2026-09-14T22:36:41 -->
### replan-p5t3s3 · discovery · P5.T3.S3 replanned into P10.T1

The June EventListener wiring step was deferred (state -) inside agentic phase 5 and never executed. It is removed from phase 5 and re-planned as agentic P10.T1, now safe to do in git because test_webhook_delivery_paths.py and the array-freeze tripwire guard the shared listener.

<!-- fr:journal kind=discovery scope=plan id=nrb-p5t3 created=2026-09-14T22:36:45 -->
### nrb-p5t3 · discovery · no-refactor-because P5.T3

Completed June task authoring one TriggerBinding + TriggerTemplate; its follow-on wiring moved to P10.T1, which carries its own justification.

<!-- fr:journal kind=discovery scope=plan id=nrb-p9t2 created=2026-09-14T22:36:48 -->
### nrb-p9t2 · discovery · no-refactor-because P9.T2

Adds one curl fetch step and a contract key to run-smoke; the shared git plumbing is already extracted by P8.T2.S3.

<!-- fr:journal kind=finding scope=plan id=june-c1-smoke-wait created=2026-09-14T22:38:24 phase=5 state=fixed -->
### june-c1-smoke-wait · finding [fixed] · C1: run-smoke dual-watcher wait -n PID (phase 5)

June milestone review (fresh context). Two background watchers + wait -n raced and could report the wrong verdict. Fixed: deterministic poll loop over .status.succeeded/.status.failed with a timeout.

<!-- fr:journal kind=finding scope=plan id=june-c2-results-path created=2026-09-14T22:38:26 phase=5 state=fixed -->
### june-c2-results-path · finding [fixed] · C2: $(results.{k}.path) is not a Tekton substitution (phase 5)

resolve-contract wrote results through a templated name Tekton never expands, so no result was ever populated. Fixed: one explicit $(results.<name>.path) write per result.

<!-- fr:journal kind=finding scope=plan id=june-c3-sha-tag created=2026-09-14T22:38:28 phase=5 state=fixed -->
### june-c3-sha-tag · finding [fixed] · C3: bare sha vs sha-<commit> image tag (phase 5)

Tasks used the bare sha while the spec and runs-fr build publish sha-<short>, which would ImagePullBackOff. Fixed: sha-$(params.sha) end to end.

<!-- fr:journal kind=finding scope=plan id=june-i4-apk-nonroot created=2026-09-14T22:38:31 phase=5 state=fixed -->
### june-i4-apk-nonroot · finding [fixed] · I4: apk add as nonroot 65532 fails (phase 5)

Steps installed git/yq at runtime as a non-root user, which cannot write the package db. Fixed: alpine/git for git and mikefarah/yq for structured edits (also removed a fragile sed).

<!-- fr:journal kind=decision scope=plan id=b740f189ad2b created=2026-09-14T22:57:40 phase=7 -->
### b740f189ad2b · decision · ArgoCD runs-fr repo credential lives in apps/argocd-extras (phase 7)

Placed the new repo-runs-fr ExternalSecret in apps/argocd-extras/manifests/ (existing Application, already targets ns argocd, already houses exactly this shape of credential — repo-stoa-companies) rather than creating a new apps/staging-gate/argocd/ Application. staging-gate's own Application targets tekton-pipelines only; widening it to argocd would have been unnecessary scope creep. No new ClusterGenerator: github-app-derio's installation already covers all derio-net repos including runs-fr. ESO resolves privateKey.secretRef in the CONSUMING namespace (argocd), so the PEM must also be copied there — manual op cicd-staging-gate-argocd-runs-fr-repo-key.

<!-- fr:journal kind=finding scope=plan id=p7-docstring-ci created=2026-09-14T23:08:25 phase=7 state=fixed -->
### p7-docstring-ci · finding [fixed] · test_staging_gate_manifests.py docstring claims scripts/tests is not run in CI (phase 7)

The module docstring says "LOCAL guards (frank does not run scripts/tests/ in CI)". repo-tripwires.yml has run the suite on every PR since #707, so the claim is stale (copied from an older test).

**Fixed in aa8bdd75.** Confirmed by the phase-7 review. Both test_staging_gate_manifests.py and the older identical sentence in test_argocd_vcluster_pod_exclusion.py now say the tests run in CI. State flipped by hand: `fr journal add` with an existing id is a no-op, and fr has no state-update command.

<!-- fr:journal kind=finding scope=plan id=p7-es-comment-evidence created=2026-09-14T23:08:28 phase=7 state=fixed -->
### p7-es-comment-evidence · finding [fixed] · repo-runs-fr ExternalSecret comment misstates its evidence (phase 7)

It says "verified live: argocd repo list has no runs-fr entry"; the verification was a kubectl listing of argocd repository Secrets. It also says "same pattern as repo-stoa-companies above" although that precedent is a different file.

**Fixed in aa8bdd75.** Confirmed by the phase-7 review. The ExternalSecret comment names externalsecret-repo-stoa-companies.yaml by file and drops the snapshot claim. The test docstring cites the `kubectl -n argocd get secret -l argocd.argoproj.io/secret-type=repository` listing. State flipped by hand (see p7-docstring-ci).

<!-- fr:journal kind=finding scope=plan id=p7-vacuous-argocd-assert created=2026-09-14T23:08:31 phase=7 state=fixed -->
### p7-vacuous-argocd-assert · finding [fixed] · Consumer-namespace test asserts "argocd" in raw, which is always true (phase 7)

test_repo_credential_manifest_documents_the_consumer_namespace_key checks `"argocd" in raw`; the `namespace: argocd` line always satisfies it, so only the manual-op-name half of the assertion can fail.

**Fixed in aa8bdd75.** Confirmed by the phase-7 review. Replaced by test_repo_credential_comment_documents_the_consumer_namespace_pem, which scans comment lines only and requires `github-app-derio-key`, `argocd` and the manual-op id. The YAML body line can no longer satisfy it. State flipped by hand (see p7-docstring-ci).

<!-- fr:journal kind=discovery scope=plan id=p7-suite-baseline created=2026-09-14T23:13:24 phase=7 -->
### p7-suite-baseline · discovery · Tripwire baseline is 933 after the rebase, not 776 (phase 7)

Measured: 776 passed + 1 xfailed was the PRE-rebase count; the 16 main commits pulled in by the 2026-09-14 rebase added 157 tests (933 collected at e582012a). Phase 7 added 8 (6 new in test_staging_gate_manifests.py, +1 parametrized URL case, +1 same-entry test) -> 940 passed + 1 xfailed at b08d0f37, re-run independently by the orchestrator (6m21s). The phase-7 executor reported the right count with a wrong explanation (phase 6 added nothing since the baseline). Use 941 collected as the pre-phase-8 baseline.

<!-- fr:journal kind=finding scope=plan id=p7-review-install-coverage created=2026-09-14T23:21:06 phase=7 state=refuted -->
### p7-review-install-coverage · finding [refuted] · Review: nothing shows the App install covers runs-fr (phase 7)

Refuted with evidence: `gh api orgs/derio-net/installations` shows derio-fr-automation (138773908) repository_selection=all, re-checked 2026-09-14. The reviewer was misled by a stale "10 repos" comment in clustergenerator-github-app.yaml, now corrected. The install check was still added to the manual op verify list, because selection can change later.

<!-- fr:journal kind=finding scope=plan id=p7-review-weak-generator-guard created=2026-09-14T23:21:09 phase=7 state=fixed -->
### p7-review-weak-generator-guard · finding [fixed] · Review: generator guard only rejected names containing runs-fr (phase 7)

Replaced by test_no_unintended_cluster_generator_is_added: the generator set must equal the pre-plan baseline plus exactly github-app-derio-argocd-read, and the shared github-app-derio must stay unscoped.

<!-- fr:journal kind=finding scope=plan id=p7-review-name-rationale created=2026-09-14T23:21:11 phase=7 state=fixed -->
### p7-review-name-rationale · finding [fixed] · Review: name-vs-server rationale was inaccurate (phase 7)

Docstring now says both forms resolve against registered clusters; name is chosen for consistency with cnc-staging.

<!-- fr:journal kind=finding scope=plan id=p7-review-syncwave-comment created=2026-09-14T23:21:13 phase=7 state=fixed -->
### p7-review-syncwave-comment · finding [fixed] · Review: argocd-extras sync-wave comment named only one consumer (phase 7)

Comment now lists repo-stoa-companies for stoa-live-mirror-sync and repo-runs-fr plus its scoped generator for runs-fr-staging.

<!-- fr:journal kind=finding scope=plan id=p7-review-manualop-placeholders created=2026-09-14T23:21:15 phase=7 state=fixed -->
### p7-review-manualop-placeholders · finding [fixed] · Review: manual op shipped placeholders with known values (phase 7)

cicd-staging-gate-argocd-runs-fr-repo-key now commits secrets/github-app/github-app-derio-key-argocd.yaml via decrypt | yq namespace | sops --encrypt from stdin (PEM never on disk decrypted), applies it, force-syncs repo-runs-fr, and verifies install selection, ES SecretSynced and argocd repo list.

<!-- fr:journal kind=finding scope=plan id=p7-review-overprivileged-token created=2026-09-14T23:21:17 phase=7 state=fixed -->
### p7-review-overprivileged-token · finding [fixed] · Review: ArgoCD credential carried the full install privilege (phase 7)

The unscoped github-app-derio token has contents/issues/pull_requests/workflows write on every derio-net repo. Fixed with ClusterGenerator github-app-derio-argocd-read on the same App and install, repositories [runs-fr], permissions {contents: read}; the live ESO v2.1.0 CRD schema accepts both fields.

<!-- fr:journal kind=decision scope=plan id=d-scoped-argocd-read-generator created=2026-09-14T23:21:20 phase=7 -->
### d-scoped-argocd-read-generator · decision · ArgoCD repository credentials use a scoped read-only generator (phase 7)

Supersedes the executor note that reused the unscoped github-app-derio. Placement in apps/argocd-extras stands. One generic generator (github-app-derio-argocd-read) serves every future gated private chart repo by extending its repositories list, rather than one generator per app. No new App, no new PEM; the PEM still has to exist in argocd because ESO resolves secretRef in the consumer namespace.

<!-- fr:journal kind=decision scope=plan id=480ec2b3feb7 created=2026-09-14T23:46:14 phase=8 -->
### 480ec2b3feb7 · decision · P8.T2.S3 REFACTOR: real StepAction, not a ConfigMap (phase 8)

The cluster's Tekton CRD serves StepAction (confirmed 2026-09-14, read-only):
\`KUBECONFIG=.../.talos/Frank_Kubeconfig.yaml kubectl get crd stepactions.tekton.dev\`
returned CREATED-AT with no error, and its served versions are
\`v1alpha1 v1beta1\` (\`kubectl get crd stepactions.tekton.dev -o jsonpath='{.spec.versions[*].name}'\`).
So the extraction is a real \`apps/staging-gate/tekton/stepactions.yaml\`
(\`apiVersion: tekton.dev/v1beta1, kind: StepAction, name: staging-gate-git\`), not the
ConfigMap fallback.

The repeated clone/commit/push script (resolve-contract, staging-gate-bump-staging,
staging-gate-promote) collapses into one StepAction with a \`mode: clone|push\` param plus
\`scratchPath\`/\`message\`/\`path\`. Every fixed piece (image, script, env incl. the
GITHUB_TOKEN secretKeyRef, computeResources, securityContext) lives in the StepAction itself
rather than being passed as params, because a Step referencing a StepAction via \`ref:\` can only
override a narrow field set (name/ref/params/timeout/workingDir/onError/stdout*/stderr*) — env
and script are not among them, so anything that needs to be identical across callers has to be
baked into the StepAction, not threaded through per-call params.

A StepAction has no \`workspaces.*\` variable namespace of its own (unlike a Task/Pipeline), so
every caller passes its own resolved \`$(workspaces.scratch.path)\` in as the \`scratchPath\`
param — substituted at the calling Task's admission time, before the StepAction ever sees it.

Only one test needed updating for the refactor
(\`test_git_pushing_steps_read_the_github_app_token\` in
scripts/tests/test_staging_gate_manifests.py): it now looks for the StepAction first and asserts
on its script/env plus that at least one step calls it in push mode, falling back to the old
inline-script assertion if no StepAction exists. Every other P8.T2.S1 test (retired-ssh-string
scan, promote's write shape, resolve-contract's v2 results, the RBAC role's secret name) is
behaviour-level and needed no change — confirming the plan's prediction.

<!-- fr:journal kind=finding scope=plan id=p8-c1-stepaction-script-params created=2026-09-14T23:59:33 phase=8 state=fixed -->
### p8-c1-stepaction-script-params · finding [fixed] · C1: StepAction script uses $(params.*) — rejected by Tekton v1.6.0 (phase 8)

stepactions.yaml splices $(params.mode/scratchPath/message/path) into the script. v1beta1 stepaction_validation rejects "param substitution in scripts is not allowed", so the StepAction is never admitted and every ref step fails. Also a shell-injection path: message embeds app/sha from the repository_dispatch body inside a pod holding the push token. Fix: pass params through env and read "$VAR". Add an offline tripwire: no StepAction spec.script contains $(params.

**Fixed in 9e364aa1.** StepAction env now carries MODE/SCRATCH/MSG/TARGET; script reads only "$VAR". Re-verified admitted: `kubectl apply --dry-run=server --validate=strict -f apps/staging-gate/tekton/stepactions.yaml` -> `stepaction.tekton.dev/staging-gate-git created (server dry run)`. New tripwire: test_stepaction_scripts_never_splice_params_directly.

<!-- fr:journal kind=finding scope=plan id=p8-c2-dag-when-status created=2026-09-14T23:59:35 phase=8 state=fixed -->
### p8-c2-dag-when-status · finding [fixed] · C2: promote when-guard reads $(tasks.run-smoke.status) in a DAG task (phase 8)

Confirmed by kubectl apply --dry-run=server: "pipeline tasks can not refer to execution status ... spec.tasks[4].when[0]". Present since June; never admitted because the branch never merged. Fix: remove the when block; runAfter [run-smoke] already skips promote when run-smoke fails. Add an offline tripwire: no spec.tasks entry references $(tasks.*.status) or .reason.

**Fixed in 9e364aa1.** Removed the when block from promote; runAfter: [run-smoke] is unchanged and sufficient. Re-verified admitted: `kubectl apply --dry-run=server --validate=strict -f apps/staging-gate/tekton/pipeline.yaml` -> `pipeline.tekton.dev/staging-gate created (server dry run)`. New tripwire: test_no_pipeline_task_reads_another_tasks_status_outside_finally.

<!-- fr:journal kind=finding scope=plan id=p8-i1-regate-noop-commit created=2026-09-14T23:59:37 phase=8 state=fixed -->
### p8-i1-regate-noop-commit · finding [fixed] · I1: re-gating the same sha fails on an empty commit (phase 8)

push mode runs git commit with no no-op guard, so bump-staging exits 1 when staging-values already holds sha-<sha>. Fix: git add -- "$TARGET"; git diff --cached --quiet && exit 0, as cnc-promotion does.

**Fixed in 9e364aa1.** Push mode now does exactly that (git add -- "$TARGET"; git diff --cached --quiet => exit 0) before committing. New tripwire: test_stepaction_push_mode_is_a_noop_on_an_unchanged_file_and_retries_the_push.

<!-- fr:journal kind=finding scope=plan id=p8-i2-stepaction-computeresources created=2026-09-14T23:59:39 phase=8 state=fixed -->
### p8-i2-stepaction-computeresources · finding [fixed] · I2: computeResources is not a StepAction field — apply fails (phase 8)

Confirmed by kubectl apply --dry-run=server --validate=strict: strict decoding error: unknown field "spec.computeResources". Worse than silently pruned: the whole StepAction fails to apply. Fix: move computeResources onto each calling ref step (allowed there).

**Fixed in 9e364aa1.** Removed from the StepAction; added to each of the five `ref: {name: staging-gate-git}` steps across pipeline.yaml and tasks.yaml. Re-verified admitted (see p8-c1). New tripwires: test_stepaction_has_no_computeresources_field, test_ref_steps_calling_the_stepaction_carry_their_own_computeresources.

<!-- fr:journal kind=finding scope=plan id=p8-m1-token-in-git-config created=2026-09-14T23:59:41 phase=8 state=fixed -->
### p8-m1-token-in-git-config · finding [fixed] · M1: token persisted in .git/config; comments claim otherwise (phase 8)

Cloning https://x-access-token:${TOKEN}@... stores it as remote.origin.url in the per-TaskRun emptyDir. Low severity (pod-local, ~1h TTL) but the comments are false and set +x is a no-op. Fix: clone the plain URL with a credential.helper reading GITHUB_TOKEN from env; correct the comments.

**Fixed in 9e364aa1.** Both clone and push modes authenticate via `git -c credential.helper='!f() { echo username=x-access-token; echo "password=$GITHUB_TOKEN"; }; f'` (clone, transient) / `git config credential.helper "$helper"` (push, persisted to the scratch clone's .git/config — but only the env-var NAME, never the value). Comments in stepactions.yaml and tasks.yaml corrected to describe this instead of the false `set +x`/no-`git remote -v` framing. New tripwire: test_no_clone_or_push_url_embeds_the_token.

<!-- fr:journal kind=finding scope=plan id=p8-m2-push-race-no-retry created=2026-09-14T23:59:43 phase=8 state=fixed -->
### p8-m2-push-race-no-retry · finding [fixed] · M2: non-fast-forward push to main fails the run with no retry (phase 8)

A concurrent push to main between clone and push loses a green promote record. apps/tekton/pipelines/site-promotion.yaml already has a bounded fetch/reset/re-edit/push retry loop to copy.

**Fixed in 9e364aa1.** Push mode retries up to 5 times: on a rejected push, fetch origin/main and `git rebase origin/main` (replays the one local commit — no re-edit needed, unlike site-promotion's reset+re-edit shape), then retry; aborts and fails loudly on a real rebase conflict. Design choice recorded as a separate decision entry (retry-rebases-not-reapply, phase 8). New tripwire: test_stepaction_push_mode_is_a_noop_on_an_unchanged_file_and_retries_the_push.

<!-- fr:journal kind=finding scope=plan id=p8-m3-unneeded-secret-role created=2026-09-14T23:59:44 phase=8 state=fixed -->
### p8-m3-unneeded-secret-role · finding [fixed] · M3: staging-gate-secrets-read Role is unneeded privilege (phase 8)

secretKeyRef env is resolved by the kubelet, not the pod ServiceAccount, so the Role only widens who can read frank-gitops-push via the automounted SA token in third-party step images. Plan issue (P8.T2.S1 mandated it). Fix: drop the Role and its assertion.

**Fixed in 9e364aa1.** Role and RoleBinding staging-gate-secrets-read removed from serviceaccount-rbac.yaml (the argocd-read Role/RoleBinding, which IS needed for the await-sync API read, stays). test_rbac_secrets_role_names_the_github_app_push_secret replaced by test_no_secrets_read_role_exists, which requires absence. Plan text corrected in commit ce310e99 (P8.T2.S1 note; state stays ticked, per instruction).

<!-- fr:journal kind=finding scope=plan id=p8-m4-weak-assertions created=2026-09-14T23:59:46 phase=8 state=fixed -->
### p8-m4-weak-assertions · finding [fixed] · M4: two phase-8 test assertions are weak (phase 8)

The .sha check is satisfied by the text $(params.sha) even with the yq write deleted; the git-token test returns early once the StepAction exists, skipping the inline-step scan. No test would have caught C1, C2 or I2.

**Fixed in 9e364aa1.** test_promote_task_writes_the_last_green_record now asserts on ".sha = strenv(" / ".image = strenv(" / ".pipelineRun = strenv(" / ".promotedAt = strenv(" (the real yq write forms) instead of bare ".sha" etc. test_git_pushing_steps_read_the_github_app_token no longer `return`s once the StepAction is found — the inline-step scan runs unconditionally now. Root cause noted separately as a discovery (m4-sha-substring, phase 8). C1/C2/I2 are now separately guarded by their own new tripwires (see those findings).

<!-- fr:journal kind=finding scope=plan id=p8-m5-sha-placeholder-cli created=2026-09-14T23:59:48 phase=8 state=fixed -->
### p8-m5-sha-placeholder-cli · finding [fixed] · M5: {sha} placeholder enforced only in pytest, not the validator CLI (phase 8)

Onboarders run validate-contract.py, which accepts a smokeRbacUrl without {sha}. Move the check into validate_one.

**Fixed in 833c0ed2.** validate_one now rejects a smokeRbacUrl missing the literal `{sha}` placeholder. New fixture test: test_validate_one_rejects_a_smoke_rbac_url_missing_the_sha_placeholder.

<!-- fr:journal kind=finding scope=plan id=p8-m6-promotedat-readme created=2026-09-14T23:59:51 phase=8 state=fixed -->
### p8-m6-promotedat-readme · finding [fixed] · M6: README misdescribes promotedAt (phase 8)

Says "UTC timestamp of the promote commit"; it is the time of the record step.

**Fixed in b98a6eb0.** README now says "UTC timestamp of when the `record` step ran (not the promote commit)".

<!-- fr:journal kind=finding scope=plan id=p8-rec-validate-inputs created=2026-09-14T23:59:52 phase=8 state=fixed -->
### p8-rec-validate-inputs · finding [fixed] · Recommendation: validate sha and app inside the pipeline (phase 8)

app builds a filesystem path and a Job name; sha reaches scripts. Phase 10 CEL validates at the trigger, but a manual PipelineRun bypasses CEL. Defence in depth: resolve-contract rejects sha not matching ^[a-f0-9]{7,40}$ and app not a DNS label before use.

**Fixed in 9e364aa1.** resolve-contract's taskSpec gained a `sha` param (passed from the pipeline) and a first `validate-inputs` step that greps SHA against `^[a-f0-9]{7,40}$` and APP against `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`, both read via env — not spliced with $(params.*). New tripwire: test_resolve_contract_validates_app_and_sha_before_use.

<!-- fr:journal kind=decision scope=plan id=d8fc89034b06 created=2026-09-15T00:15:08 phase=8 -->
### d8fc89034b06 · decision · Push retry rebases the single commit onto origin/main, rather than re-applying the caller's edit (phase 8)

Chose the 'git pull --rebase'-shaped option from the two offered (p8-m2). The StepAction's push mode now: git add -- $TARGET; no-op exit 0 if git diff --cached --quiet (p8-i1); else commit once; then retry the push up to 5 times, and on a non-fast-forward rejection fetch origin/main and 'git rebase origin/main' (which REPLAYS the already-made local commit — no re-edit needed) before retrying. This keeps the StepAction generic: it never needs to know the caller's yq expression, unlike the 'pass the edit through env' alternative, which would have coupled the shared plumbing to yq and to each caller's specific field-write. A rebase conflict (two callers touching the same file+region in the retry window) aborts the rebase and fails loudly rather than looping forever — accepted as out of scope for a first pass, since every current caller (bump-staging: image.tag; promote: sha/image/pipelineRun/promotedAt) writes its OWN app's registry-scoped file, so a same-file collision needs two concurrent gate runs for the SAME app, which the design does not yet guard against (no PipelineRun concurrency limit) but is unchanged risk from before this fix, not introduced by it.

<!-- fr:journal kind=discovery scope=plan id=03f98450119b created=2026-09-15T00:15:17 phase=8 -->
### 03f98450119b · discovery · M4's own weak assertion: '.sha' is a substring of '$(params.sha)' (phase 8)

The original test_promote_task_writes_the_last_green_record asserted 'assert ".sha" in scripts' to prove the record step writes .sha into the promoted record. But every promote step's script also contains the literal text '$(params.sha)' (e.g. in the push step's commit message param) — which itself contains the substring '.sha' — so the assertion passed even with the yq write line deleted. Fixed by asserting on the actual yq write form '.sha = strenv(' etc. Generalises: a substring assertion on a short dotted-field name is unsafe near any Tekton $(...) reference containing the same field name.

<!-- fr:journal kind=finding scope=plan id=p8-rebase-needs-identity created=2026-09-15T00:26:07 phase=8 state=fixed -->
### p8-rebase-needs-identity · finding [fixed] · Push-mode retry rebase dies with no committer identity in the pod (phase 8)

Found by orchestrator review of the phase-8 fix pass (the retry that fixed p8-m2 cannot run). stepactions.yaml passes committer identity only as -c user.* on git add/commit; git rebase origin/main rewrites the commit and needs one too. Reproduced 2026-09-15 in alpine/git:2.45.2 as --user 65532 (no passwd entry, HOME without gitconfig) against a bare remote with a racing commit: rebase -> "fatal: unable to auto-detect email address (got unknown@<host>.(none))". Control with in-repo user.email/user.name: rebase of the --depth 1 clone succeeds and the push lands, so the shallow clone is not a problem. Every existing guard is structural or admission-level, none executes the script. Fix: configure identity in-repo in push mode; guard with a behaviour test that runs the real script under user.useConfigOnly=true.

**Fixed in 471125ee.** Push mode now runs `git config user.email/user.name` before add/commit/rebase, and the rebase-failure message no longer claims a conflict it cannot know about. New scripts/tests/test_staging_gate_git_stepaction_behaviour.py executes the StepAction script against a raced bare remote: RED on the old script ("no email was given and auto-detection is disabled"), GREEN after (31 passed across the staging-gate test files). The edited StepAction still passes `kubectl apply --dry-run=server --validate=strict`. State flipped by hand (see p7-docstring-ci).

<!-- fr:journal kind=finding scope=plan id=8e74590d1adf created=2026-09-15T00:47:43 phase=9 state=fixed -->
### 8e74590d1adf · finding [fixed] · P9: rancher/kubectl:v1.31.4 is shell-less — every existing script step against it fails at pod runtime (phase 9)

Independently discovered while implementing P9.T1 (vCluster kubeconfig fetch, which needed a new shell script step on a kubectl image). `docker inspect rancher/kubectl:v1.31.4` shows it is built FROM SCRATCH ("kubectl from scratch") — a single static binary, no /bin/sh, no coreutils. Negative control 2026-09-15: mounting a `#!/bin/sh` script as the entrypoint and running it fails `exec /tekton/script.sh: no such file or directory` — the exact opaque failure Tekton's script mechanism would hit at pod runtime (it execs the script file directly, relying on the OS honouring the shebang). This affects every PRE-EXISTING rancher/kubectl `script:` step: staging-gate-await-sync, and the original staging-gate-run-smoke/staging-gate-reset steps (phase 7). None of it was caught by kubectl apply --dry-run=server (schema-only) or by structural pytest (never executes the script) — same blind spot the phase-8 review flagged for the git StepAction, just on the runtime side instead of the admission side.

**Fixed in this phase (P9.T1 GREEN), same commit series.** Swapped all rancher/kubectl:v1.31.4 occurrences (await-sync, the new run-smoke/reset kubeconfig-fetch + smoke + reset steps) to bitnamilegacy/kubectl:1.33.4 (Debian-based; confirmed via docker run to have bash/date/base64/awk on PATH; already used elsewhere in the repo at apps/tekton/manifests/pipelinerun-ttl-gc.yaml with runAsUser 1001). New structural tripwire: test_no_step_with_a_script_uses_a_shell_less_image (scripts/tests/test_staging_gate_manifests.py), RED against the pre-fix images, GREEN after. State flipped by hand (see p7-docstring-ci for the precedent).

<!-- fr:journal kind=decision scope=plan id=f23877569cc2 created=2026-09-15T01:04:41 phase=9 -->
### f23877569cc2 · decision · P9: kubectl steps standardize on bitnamilegacy/kubectl:1.33.4, not per-task fixes (phase 9)

Rather than fixing only the steps P9.T1/T2 newly added, swapped EVERY existing rancher/kubectl:v1.31.4 occurrence in apps/staging-gate/tekton/tasks.yaml (await-sync, the pre-existing run-smoke/reset scripts) to bitnamilegacy/kubectl:1.33.4 in the same pass, since it is the identical defect (shell-less image, see the P9 finding) on files I was already editing for T1/T2. Chose bitnamilegacy/kubectl over an alpine-based kubectl image because it is an EXISTING repo precedent (apps/tekton/manifests/pipelinerun-ttl-gc.yaml), confirmed via docker run to ship bash/date/base64/awk, and keeping one kubectl-with-shell image across the repo avoids adding a second such image with its own gotchas to track.

<!-- fr:journal kind=discovery scope=plan id=e3fa9f838fdd created=2026-09-15T01:04:59 phase=9 -->
### e3fa9f838fdd · discovery · P9: actual scope exceeded the pre-authored no-refactor-because entries (phase 9)

nrb-p9t1/p9t2/p9t3 (written before implementation) predicted small, non-refactor-worthy diffs. Actual P9.T1 also required discovering and fixing that rancher/kubectl:v1.31.4 has no shell at all (see the separate finding), which meant swapping the kubectl image across every task in tasks.yaml (await-sync + the new run-smoke/reset steps) rather than touching only the one new Role the prediction anticipated -- a genuine, in-scope REFACTOR (same defect, same file, same pass), not additional new-code sprawl. The predictions stand as historical record of what was expected going in; this entry records why reality diverged.

<!-- fr:journal kind=finding scope=plan id=p9-c1-netpol-blocks-gate created=2026-09-19T23:19:58 phase=9 state=fixed -->
### p9-c1-netpol-blocks-gate · finding [fixed] · Chart's vc-cp-staging NetworkPolicy blocks the gate and ArgoCD from the staging vCluster API (phase 9)

Confirmed live by the orchestrator: rendering the staging chart produces vc-cp-staging, selecting the control-plane pod (release: staging), policyTypes [Egress, Ingress], allowing ingress only from same-namespace release:staging / vcluster.loft.sh/managed-by:staging (1053/8443), same-namespace app:vcluster-snapshot, and app:loft anywhere — nothing from tekton-pipelines or argocd. apps/vclusters/template/values.yaml:82 sets policies.networkPolicy.enabled: true and staging does not override it (unlike cnc-staging, which disables it for unrelated CNC-stack egress reasons — NOT the fix here per the apps/cnc-staging-host/manifests/networkpolicy-argocd.yaml HISTORY incident). Fixed by an additive NetworkPolicy apps/staging-gate/tekton/networkpolicy-vcluster-staging.yaml (applied by the staging-gate Application, which already syncs vcluster-staging Role/RoleBinding) granting ingress on 8443 from tekton-pipelines, argocd, and podSelector:{} (the vCluster's own pods, mirroring the CoreDNS incident clause). Server-side dry-run passed (retargeted copy; vcluster-staging namespace does not exist pre-registration). Commit d110bebe.

<!-- fr:journal kind=finding scope=plan id=p9-c2-kubeconfig-san created=2026-09-19T23:20:15 phase=9 state=fixed -->
### p9-c2-kubeconfig-san · finding [fixed] · Gate's exported kubeconfig hostname (.svc form) is not a SAN on the syncer cert (phase 9)

Confirmed live by the orchestrator via a TLS handshake against the LIVE cnc-staging vCluster Service (same chart, same version): syncer cert SANs include kubernetes.default.svc.cluster.local, kubernetes.default.svc, kubernetes.default, kubernetes, localhost, *.cnc-staging.cnc-staging-vcluster.nodes.vcluster.com, *.nodes.vcluster.com, cnc-staging, cnc-staging.cnc-staging-vcluster (the name.namespace form), my-host.com, plus IPs — <name>.<namespace> IS a SAN, <name>.<namespace>.svc is NOT. apps/vclusters/staging/values.yaml's exportKubeConfig.additionalSecrets used the .svc form, and unlike the P11 ArgoCD cluster registration (tlsClientConfig.insecure: true, skips hostname verification), the gate's own kubeconfig has no insecure flag anywhere in the fetch-kubeconfig/run-smoke/reset path — the first real gate run would have failed TLS verification. Fixed: server changed to https://staging.vcluster-staging:443 (no .svc), and controlPlane.proxy.extraSANs added for the .svc forms (verified live the key actually reaches the rendered vc-config-staging Secret's config.yaml, not just accepted by the schema). Also corrected the values.yaml comment: exportKubeConfig.secret and .additionalSecrets are MUTUALLY EXCLUSIVE (verified live — rendering the chart with both set fails the WHOLE render with an explicit chart error), not 'the extra Secret alongside the default' as originally written (see p9-decision-c2-svc-vs-name-form). P11.T1.S1's registration step now carries a preflight (openssl SAN check + one kubectl-through-the-gate-kubeconfig command from tekton-pipelines) proving C1+C2 together before the gate's first real run. Commits 7e38a3dd, 62985af8.

<!-- fr:journal kind=decision scope=plan id=p9-decision-c2-svc-vs-name-form created=2026-09-19T23:20:31 phase=9 -->
### p9-decision-c2-svc-vs-name-form · decision · Two different vCluster URL forms are both correct, for different consumers (phase 9)

The ArgoCD cluster registration (P11, out-of-band, tlsClientConfig.insecure: true, cnc-staging precedent) correctly keeps the .svc form (https://staging.vcluster-staging.svc:443) — insecure:true skips hostname verification entirely, so the SAN mismatch is irrelevant there. The gate's OWN kubeconfig (exportKubeConfig.additionalSecrets, consumed with full TLS verification, no insecure flag anywhere in fetch-kubeconfig/run-smoke/reset) needed the name.namespace form instead, because that is what the live syncer cert actually carries as a SAN (verified against cnc-staging, same chart+version). Do not 'fix' the ArgoCD registration to match, and do not fix the gate kubeconfig to match ArgoCD's form — each is correct for its own TLS-verification posture. controlPlane.proxy.extraSANs was added so BOTH forms verify, closing the gap for any future consumer that addresses the vCluster by its .svc name without insecure:true.

<!-- fr:journal kind=finding scope=plan id=p9-i1-waitturn-self-not-found created=2026-09-19T23:20:51 phase=9 state=fixed -->
### p9-i1-waitturn-self-not-found · finding [fixed] · wait-turn spins for the full timeout when self is unlabelled (every manual run) (phase 9)

Only the TriggerTemplate labels PipelineRuns staging-gate/app — every manual tkn pipeline start (including phase 11's own Test Plan, P11.T1.S3/S4) is unlabelled, so self never appeared in the kubectl listing and wait-turn spun for the full waitTurnTimeoutSeconds (default 1800s/30min) before failing with a misleading 'timed out' message on a run that was never actually blocked. Fixed: after a few (default 3, env-overridable SELF_NOT_FOUND_RETRIES) consecutive polls where self is still missing, print 'self not labelled staging-gate/app -- serialization not enforced for this run' to stderr and exit 0 (proceed). Behaviour tests added: proceeds-after-a-few-retries (RED confirmed a 30s subprocess timeout before the fix — the script really did spin for the whole window), and a regression guard proving the bail-out does NOT fire once self legitimately shows up after a poll or two (informer lag). Commit 1da576e5.

<!-- fr:journal kind=finding scope=plan id=p9-i2-waitturn-same-second created=2026-09-19T23:20:59 phase=9 state=fixed -->
### p9-i2-waitturn-same-second · finding [fixed] · Two PipelineRuns created in the same second both see 'no older run' and race (phase 9)

creationTimestamp has one-second granularity; the blocking predicate used a strict timestamp < comparison, so two runs for the same app created in the same second both saw no older run and could proceed concurrently into the one shared staging vCluster. Fixed with a name tiebreak so the comparison is a total order: ($2<selfts) || ($2==selfts && $1<self). Behaviour tests added for both directions of the tiebreak (earlier-sorting name blocks; later-sorting name does not) with identical timestamps. Commit 1da576e5.

<!-- fr:journal kind=finding scope=plan id=p9-i3-pipeline-timeout-cancels-finally created=2026-09-19T23:21:21 phase=9 state=fixed -->
### p9-i3-pipeline-timeout-cancels-finally · finding [fixed] · An unset PipelineRun timeout risks Tekton cancelling reset+notify on a pipeline timeout (phase 9)

Tekton v1.6.0 cancels running finally TaskRuns (reset, notify) when timeouts.pipeline elapses, UNLESS timeouts.tasks is set strictly lower. The default pipeline timeout is 60m and wait-turn alone can consume up to 30m of that (waitTurnTimeoutSeconds default 1800s), so an unset timeouts block risked losing both the vCluster namespace cleanup and the red-path Telegram alert on exactly the run most likely to need them. Fixed: the TriggerTemplate's PipelineRun now sets timeouts: {pipeline: 1h30m, tasks: 1h20m, finally: 10m}. Structural test asserts the exact values and that tasks < pipeline (the rule that actually protects finally). Commit fd554027.

<!-- fr:journal kind=finding scope=plan id=p9-i4-notify-secret-not-optional created=2026-09-19T23:21:29 phase=9 state=fixed -->
### p9-i4-notify-secret-not-optional · finding [fixed] · notify's Telegram secretKeyRefs were not optional — un-synced ExternalSecret makes the pod un-startable (phase 9)

staging-gate-telegram is an ExternalSecret (refreshInterval: 5m, not instant); before it syncs the Secret's keys don't exist, and a non-optional secretKeyRef makes Kubernetes refuse to start the whole container (CreateContainerConfigError) — the worst failure mode for the one Task whose entire job is reporting a red run. Fixed: TELEGRAM_TOKEN/TELEGRAM_CHAT_ID secretKeyRefs are now optional: true, and the script checks for an empty token/chat-id and fails loudly ('staging-gate-telegram token/chat-id is empty (ExternalSecret not yet synced?) -- cannot notify', exit 1) BEFORE ever invoking curl, rather than crashing on an unbound variable or silently POSTing with an empty credential. Also gave the step a short explicit 2m timeout so a Telegram-side hang doesn't consume the whole finally window. Behaviour test (empty-credential path) RED-confirmed the old script would have POSTed with an empty token/chat_id. Commit 1e01b0aa.

<!-- fr:journal kind=finding scope=plan id=p9-minors created=2026-09-19T23:22:01 phase=9 state=fixed -->
### p9-minors · finding [fixed] · P9 review minors M1-M10 — all fixed (combined entry) (phase 9)

Combined entry for the ten minor findings (each small; grouping for readability rather than filing ten separate entries):

M1 (waitTurnTimeoutSeconds not a real knob): was declared only on resolve-contract's embedded taskSpec params (default 1800) with no Pipeline-level param and never passed into the task node. Added a Pipeline-level param (same default) and passed it through explicitly. Commit a7e8474a.

M2 (unused 'get' verb): staging-gate-pipelinerun-read's Role granted get+list, but wait-turn only ever does a label-selector listing (RBAC 'list' verb) — 'get' (single named lookup) was unused. Trimmed to ['list']. Commit 5cb7fbd3.

M3 (smoke RBAC namespace constraint undocumented): run-smoke applies smokeRbacUrl's manifest with a bare kubectl -n "$ns" apply -f -; documented in README that the manifest must be namespace-free or match smokeNamespace exactly, or the smoke Job's serviceAccountName resolves against the wrong namespace with no apply-time error. Commit b5a9e6ff.

M4 (kind-unfiltered apply blast radius undocumented): documented in README that the apply is kind-unfiltered (write access to smokeRbacUrl's content = write access to arbitrary objects in the smoke namespace) and that the pinned ?ref={sha} bounds the blast radius to one already-merged commit. Commit b5a9e6ff.

M5 (reset's --wait=false races the next create): reset deletes smokeNamespace with --wait=false; a re-gate of the same app back-to-back could hit 'the system is terminating' on the next create/apply. Added kubectl wait --for=delete ns/"$ns" --timeout=120s || true before create. Commit 66cbe992.

M6 (exportKubeConfig.secret vs .additionalSecrets comment was wrong): folded into the C2 fix (p9-c2-kubeconfig-san) — corrected live-verified as mutually exclusive (chart render fails outright if both set), not 'the extra Secret alongside the default'. Commit 7e38a3dd.

M7 (kubectl image not digest-pinned): pinned bitnamilegacy/kubectl:1.33.4 by digest sha256:ed0b31a0508da84ee655c5c6e01bd3897fc56ad6cf69debb27fa1893a06d2246, verified live via docker pull (matches the digest given in the review brief exactly). Noted bitnamilegacy/* is Broadcom's frozen mirror of the retired free bitnami/* tags (no further updates ship under this tag) — the pin guards against a re-pushed tag, not upstream movement; the repo-wide kubectl pin needs a maintained successor once one exists. Commit 74eb2151.

M8a (kubeconfig-fetch stub not key-aware): the test stub accepted any -o/jsonpath value; tightened it to check the exact jsonpath expression. This surfaced a REAL production bug it had been hiding: kubectl ... | base64 -d > "$dest" under plain #!/bin/sh has no pipefail, so a failed kubectl fetch would silently write an empty/invalid kubeconfig (base64 -d of empty stdin exits 0). Fixed by capturing kubectl's output via var=$(...) first, which DOES propagate failure through set -e (verified live). Added a negative-control test proving the tightened stub rejects a wrong-key script. Commit a683cf35.

M8b (wait-turn stub never covers the empty-status case): a fresh PipelineRun's jsonpath status field is EMPTY (allowMissingKeys), not the literal 'Unknown' the stub always emitted; added a test covering the empty case explicitly (no code change needed -- the awk predicate already treated empty as unfinished). Commit 1da576e5.

M8c (wait-turn stub missing I1/I2 coverage): added behaviour tests for both to the same file as their fixes. Commit 1da576e5.

M9 (notify step missing HOME): every other step in this dir sets HOME=/tekton/home; notify was the only one that didn't. Added for consistency. Folded into the I4 commit. Commit 1e01b0aa.

M10 (shell-image guard was a one-entry denylist): generalised test_no_step_with_a_script_uses_a_shell_less_image from denylisting rancher/kubectl to allowlisting the four vetted shell-bearing images actually used (alpine/git, mikefarah/yq, curlimages/curl, digest-pinned bitnamilegacy/kubectl). Folded into the M7 commit. Commit 74eb2151.

<!-- fr:journal kind=discovery scope=plan id=bb8d0c5b4dc2 created=2026-09-20T00:15:25 phase=10 -->
### bb8d0c5b4dc2 · discovery · P10.T1: bindings reference the June-authored TriggerBinding/TriggerTemplate by name (phase 10)

The new staging-gate-runs-fr Trigger on github-listener uses 'bindings: [{ref: staging-gate-binding, kind: TriggerBinding}]' and 'template: {ref: staging-gate-template}' rather than duplicating params inline (the shorthand every neighbor trigger in eventlistener-github.yaml uses). This matches the phase's own framing ('the binding/template already exist') and the P5 no-refactor note (nrb-p5t3: 'its follow-on wiring moved to P10.T1'). CEL already filters repo/action/app-shape/sha-shape before admission, so binding straight from body.client_payload via the existing TriggerBinding is safe -- no extensions overlay needed. Verified server-side: the whole EventListener (all 12 triggers incl. the new one) admits with 'eventlistener.triggers.tekton.dev/github-listener configured (server dry run)', proving the CEL .matches() regex syntax is accepted at admission.

<!-- fr:journal kind=decision scope=plan id=d-delivery-gha-direct-post created=2026-09-20T10:20:38 phase=10 -->
### d-delivery-gha-direct-post · decision · Delivery switches to a signed POST from GHA; no GitHub webhook (phase 10)

Supersedes d-dispatch-webhook. GitHub does not allow a REPOSITORY webhook to subscribe to repository_dispatch: the availability matrix lists "app" only (push lists repository/organization/app), confirmed at docs.github.com/en/webhooks/webhook-events-and-payloads on 2026-09-20. Live corroboration: agentic-stoa/cnc-frd hook carries [pull_request, push] though its cnc-image-promotion trigger filters repository_dispatch; derio-net/runs-fr has no hooks; no cnc-image-promotion PipelineRun exists in the retained window. Operator decision 2026-09-20: runs-fr build.yml POSTs the payload straight to https://webhooks.hop.derio.net/ with X-GitHub-Event: repository_dispatch and a self-computed X-Hub-Signature-256 over the exact body, secret held as a runs-fr Actions secret mirroring Infisical /derio-net/GITHUB_WEBHOOK_SECRET. Body: {"action":"staging-gate","client_payload":{"app":"runs-fr","sha":"<short>"},"repository":{"full_name":"derio-net/runs-fr"}} so all four CEL clauses still match. Frank keeps the trigger, CEL filter and ExternalSecret unchanged; only webhooks.yaml (delivery-path declaration shape), the manual op, and the spec change. runs-fr PR #42 (contents: write for the dispatch API) becomes unnecessary and should be closed.

<!-- fr:journal kind=discovery scope=plan id=p10-discovery-cnc-image-promotion-unreachable created=2026-09-20T10:35:21 phase=10 -->
### p10-discovery-cnc-image-promotion-unreachable · discovery · cnc-image-promotion (agentic-stoa/cnc-frd) has the same App-only repository_dispatch gap, pre-existing (phase 10)

While fixing Critical #1 (staging-gate-runs-fr's impossible scope: repo + repository_dispatch declaration) a new tripwire check (declared events must cover a served trigger's github-interceptor eventTypes) also flags agentic-stoa/cnc-frd's webhooks.yaml entry: it declares events [push, pull_request] under scope: repo but also serves cnc-image-promotion, whose github interceptor requires eventTypes: [repository_dispatch] -- the identical GitHub App-only restriction. This predates this plan (P5/P8-era wiring) and is out of scope to fix here. Live corroboration checked 2026-09-20: `gh api repos/agentic-stoa/cnc-frd/hooks` carries only [pull_request, push], and no cnc-image-promotion PipelineRun exists in the retained Tekton window -- the path looks pre-existing and dead, not a live regression this plan is responsible for. Left in place via a documented exemption (scripts/tests/test_webhook_delivery_paths.py KNOWN_EVENT_COVERAGE_GAPS) plus a follow-up note on the webhooks.yaml entry itself, rather than silently "fixed" by an unrelated plan. Follow-up: either retire the cnc-image-promotion trigger or give it its own direct-post/App-webhook delivery path.

<!-- fr:journal kind=finding scope=plan id=p10-c1-repo-webhook-impossible created=2026-09-20T10:35:44 phase=10 state=fixed -->
### p10-c1-repo-webhook-impossible · finding [fixed] · Critical #1: repository_dispatch cannot be delivered by a repo webhook -- the declared delivery path could not exist (phase 10)

RED: GitHub's webhook availability matrix (docs.github.com/en/webhooks/webhook-events-and-payloads, checked 2026-09-20) lists repository_dispatch as App-only -- push lists repository/organization/app as valid scopes, repository_dispatch lists app only. staging-gate-runs-fr's webhooks.yaml entry declared scope: repo, events: [repository_dispatch], which is unreachable by construction, not merely unwired. Live corroboration: agentic-stoa/cnc-frd's hook carries only [pull_request, push] although its cnc-image-promotion trigger filters repository_dispatch, and no cnc-image-promotion PipelineRun exists in the retained window (see p10-discovery-cnc-image-promotion-unreachable) -- the same failure mode, already live and silent elsewhere. New test_forge_webhook_declarations_never_claim_a_github_app_only_event failed against the pre-fix webhooks.yaml.

GREEN: operator decision d-delivery-gha-direct-post -- runs-fr's own build.yml (GHA) POSTs the signed payload straight to https://webhooks.hop.derio.net/ (X-GitHub-Event: repository_dispatch, X-Hub-Signature-256: sha256=<hex HMAC of the exact body>, Content-Type: application/json), no GitHub webhook registered at all. Frank-side: webhooks.yaml's derio-net/runs-fr entry re-expressed as scope: direct-post (new first-class schema value, documented in the file's header) instead of scope: repo; the EventListener trigger, its CEL filter (repo/action/app/sha) and the derio-net-github-webhook-secret ExternalSecret are UNCHANGED -- verified the github/cel interceptors validate purely by HMAC signature + X-GitHub-Event header string equality, never sender identity (Tekton Triggers pkg/interceptors/github behavior; corroborated in-repo by the Gitea-vs-GitHub header-name gotcha in docs/runbooks/frank-gotchas/tekton.md), so a same-shape signed POST from anywhere satisfies it identically. Two new tripwire assertions added to test_webhook_delivery_paths.py: (1) no scope: repo/org declaration may claim a GitHub App-only event (GITHUB_APP_ONLY_EVENTS, currently {repository_dispatch}); (2) every declaration's events: must cover its served triggers' github-interceptor eventTypes (KNOWN_EVENT_COVERAGE_GAPS carries the one pre-existing exemption, cnc-image-promotion, with a reason). 11.yaml's cicd-staging-gate-runs-fr-webhook manual op rewritten to generate+seed the shared secret, mirror it into runs-fr's FRANK_STAGING_GATE_WEBHOOK_SECRET Actions secret, force-sync the ExternalSecret, and verify via a signed test POST or the first real gate run; notes runs-fr PR #42 (contents: write, the abandoned dispatch-API approach) should be closed. Spec Component 1/3 and the Revision table updated.

scripts/tests/test_webhook_delivery_paths.py scripts/tests/test_staging_gate_manifests.py: 68 passed at this step.

<!-- fr:journal kind=finding scope=plan id=p10-i2-binding-ref-unverified created=2026-09-20T10:38:52 phase=10 state=fixed -->
### p10-i2-binding-ref-unverified · finding [fixed] · Important #2: nothing verified staging-gate-binding/-template exist or that params line up (phase 10)

RED: staging-gate-runs-fr refs TriggerBinding staging-gate-binding and TriggerTemplate staging-gate-template by name only -- a typo'd ref passes yaml parsing, the existing pytest suite, kubeconform AND admission (a Trigger's ref fields are not resolved/validated until an event actually fires), failing only at event time. No test asserted these objects exist or that the binding supplies every param the template declares.

GREEN: new test_referenced_binding_and_template_actually_exist_and_params_line_up parses apps/staging-gate/tekton/triggers.yaml, asserts a TriggerBinding named staging-gate-binding and a TriggerTemplate named staging-gate-template exist in namespace tekton-pipelines, and that the template's spec.params (app, sha, repo-full-name) are all supplied by the binding's params. Passed immediately against the existing (correct) manifests -- the finding was a missing assertion, not a missing object; the test now guards against a future typo'd ref regressing silently.

<!-- fr:journal kind=finding scope=plan id=p10-i3-tripwire-events-blind created=2026-09-20T10:38:54 phase=10 state=fixed -->
### p10-i3-tripwire-events-blind · finding [fixed] · Important #3: the delivery-path tripwire could not tell a repo/org webhook was structurally impossible (phase 10)

RED: test_webhook_delivery_paths.py only checked that SOME declaration named a trigger and repo -- it never parsed the trigger's own github-interceptor eventTypes, and never asked whether a scope: repo/org declaration's events were even deliverable to that webhook type. staging-gate-runs-fr's original scope: repo + events: [repository_dispatch] passed every existing check while being structurally unreachable (see p10-c1-repo-webhook-impossible).

GREEN: two new assertions in test_webhook_delivery_paths.py -- test_forge_webhook_declarations_never_claim_a_github_app_only_event (GITHUB_APP_ONLY_EVENTS, currently {repository_dispatch}; scope: repo/org may never claim one) and test_declared_events_cover_the_served_triggers_interceptor_event_types (a declaration's events: must be a superset of every served trigger's github-interceptor eventTypes). Both run against the live triggers/declarations offline at PR time. The second check immediately flagged the pre-existing agentic-stoa/cnc-frd <-> cnc-image-promotion gap (KNOWN_EVENT_COVERAGE_GAPS exemption with a written reason; see p10-discovery-cnc-image-promotion-unreachable) -- confirming the new check generalizes to the class of bug, not just this one instance.

<!-- fr:journal kind=finding scope=plan id=p10-i4-degraded-window created=2026-09-20T10:40:47 phase=10 state=fixed -->
### p10-i4-degraded-window · finding [fixed] · Important #4: merging leaves tekton-extras Degraded until Infisical is seeded, undocumented (phase 10)

RED: nothing said, on either the ExternalSecret or the webhooks.yaml entry, that merging this phase leaves tekton-extras Degraded (ArgoCD's built-in ExternalSecret health check) until the operator runs cicd-staging-gate-runs-fr-webhook. No alert pages on it, so an operator seeing Degraded post-merge with no comment pointing at the cause would have to rediscover the manual-op dependency from scratch.

GREEN: added an EXPECTED DEGRADED WINDOW paragraph to both apps/tekton/manifests/externalsecret-derio-net-github-webhook-secret.yaml's header comment and the webhooks.yaml derio-net/runs-fr note, naming tekton-extras and the manual op. Also documented the Infisical folder-vs-project trap in the ExternalSecret comment: /derio-net must be a folder inside the SAME project the infisical ClusterSecretStore targets -- a sibling-project value is unreadable and ESO's error names the folder, not the project, which reads like a typo'd path rather than a wrong-project lookup.
