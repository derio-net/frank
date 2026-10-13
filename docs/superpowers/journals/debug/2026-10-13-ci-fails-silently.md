# Journal: 2026-10-13-ci-fails-silently

<!-- fr:journal kind=repro scope=debug id=07d555715485 created=2026-10-13T17:10:26+00:00 -->
### 07d555715485 · repro · Timed-out CI PipelineRuns post no commit status

From 2026-10-11T21:22Z to 2026-10-12T04:21Z, 23 PipelineRuns (cnc-ci / cnc-frd-ci / agentic-stoa-main-sync) ended PipelineRunTimeout. Example cnc-frd-ci-82dr7: spec.timeouts={pipeline: 1h} (controller default; no template sets timeouts); childReferences=[mirror] only; skippedTasks: github-status-failure and gitea-status-failure with reason 'PipelineRun timeout has been reached'. Repro: kubectl -n tekton-pipelines get pipelinerun cnc-frd-ci-82dr7 -o json | jq .status.skippedTasks. The mirror pod was blocked on its volumeClaimTemplate PVC (longhorn-hdd: disk tag hdd does not exist). Net effect: GitHub received no tekton/ci status, so PRs looked green.
