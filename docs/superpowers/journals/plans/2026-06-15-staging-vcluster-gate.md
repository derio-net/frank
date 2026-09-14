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

<!-- fr:journal kind=finding scope=plan id=p7-docstring-ci created=2026-09-14T23:08:25 phase=7 state=open -->
### p7-docstring-ci · finding [open] · test_staging_gate_manifests.py docstring claims scripts/tests is not run in CI (phase 7)

The module docstring says "LOCAL guards (frank does not run scripts/tests/ in CI)". repo-tripwires.yml has run the suite on every PR since #707, so the claim is stale (copied from an older test).

<!-- fr:journal kind=finding scope=plan id=p7-es-comment-evidence created=2026-09-14T23:08:28 phase=7 state=open -->
### p7-es-comment-evidence · finding [open] · repo-runs-fr ExternalSecret comment misstates its evidence (phase 7)

It says "verified live: argocd repo list has no runs-fr entry"; the verification was a kubectl listing of argocd repository Secrets. It also says "same pattern as repo-stoa-companies above" although that precedent is a different file.

<!-- fr:journal kind=finding scope=plan id=p7-vacuous-argocd-assert created=2026-09-14T23:08:31 phase=7 state=open -->
### p7-vacuous-argocd-assert · finding [open] · Consumer-namespace test asserts "argocd" in raw, which is always true (phase 7)

test_repo_credential_manifest_documents_the_consumer_namespace_key checks `"argocd" in raw`; the `namespace: argocd` line always satisfies it, so only the manual-op-name half of the assertion can fail.

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
