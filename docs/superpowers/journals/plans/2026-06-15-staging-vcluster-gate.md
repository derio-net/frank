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
