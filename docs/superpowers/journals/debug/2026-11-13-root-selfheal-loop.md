<!-- fr:journal-schema=4 -->
# Journal: 2026-11-13-root-selfheal-loop

<!-- fr:journal kind=repro scope=debug id=2177a9ae9b7d created=2026-11-13T22:34:41+00:00 -->
### 2177a9ae9b7d · repro · root permanently OutOfSync, selfHeal filtered

autoHealAttemptsCount 13-59; operation.sync.resources lists only longhorn/victoria-metrics/gpu-operator; live diff is finalizers only.

<!-- fr:journal kind=ruled-out scope=debug id=4319795ce5b2 created=2026-11-13T22:34:43+00:00 -->
### 4319795ce5b2 · ruled-out · victoria-metrics converged on its own

False: it holds the same pre-delete finalizers live; reads Synced only just after a strip.

<!-- fr:journal kind=root-cause scope=debug id=ea17c9dbccf5 created=2026-11-13T22:34:46+00:00 -->
### ea17c9dbccf5 · root-cause · Controller-added delete-hook finalizers vs undeclared root

ArgoCD 3.x adds pre/post-delete finalizers to Apps whose charts ship hooks; templates declare only resources-finalizer; root was not in git so had no ignoreDifferences. Filtered selfHeal ops then overwrite full syncs.
