<!-- fr:journal-schema=3 -->
# Journal: 2026-11-03-ci-outcome-alert-repeat

<!-- fr:journal kind=repro scope=debug id=1d263c0cd0f1 created=2026-11-03T08:47:23+00:00 -->
### 1d263c0cd0f1 · repro · layer-25-pipeline-failing re-pages every 3m and its Fix command lists nothing

Telegram re-sent the identical kid-laptops-ci page repeatedly. The annotation's `kubectl -n tekton-pipelines get pipelinerun -l tekton.dev/pipeline=kid-laptops-ci` returns no rows; the three failed runs (2026-11-02 20:15/20:51/22:09Z, unit-tests step) live in namespace kid-laptops-ci.

<!-- fr:journal kind=ruled-out scope=debug id=e31b5e2179a0 created=2026-11-03T08:47:28+00:00 -->
### e31b5e2179a0 · ruled-out · Not a dedup bug: there is no repeat limit for this alert at all

The only repeat override in notification-policy-cm.yaml is the pvc_capacity route (4h, frank#722). Everything else inherits the root repeat_interval: 3m.
