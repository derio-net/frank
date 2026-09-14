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
