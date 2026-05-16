# Frank Gotchas — Tekton

Long-form companion to the **Tekton** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## `computeResources`, not `resources`

Tekton v1 Task CRD uses `computeResources` (not `resources`) for step resource requests/limits — `resources` silently fails schema validation, causing ArgoCD `ComparisonError` ("field not declared in schema") that blocks all syncs for the app. (Note: native K8s containers in CronJobs/Jobs use `resources` — this only applies to Tekton Task steps.)

## `$(tasks.status)` returns "Completed" when tasks are skipped

Tekton `$(tasks.status)` in `finally` blocks returns `"Completed"` (not `"Succeeded"`) when some tasks are skipped via `when` clauses — use `in ["Succeeded", "Completed"]` for success checks.

## PVC workspaces mount as root

Tekton PipelineRun PVC workspaces mount as root — tasks running as non-root UID need `taskRunTemplate.podTemplate.securityContext.fsGroup` set in the TriggerTemplate/PipelineRun spec.

## `runAsUser: 65534` (nobody) → `HOME=/` (read-only)

Tekton tasks with `runAsUser: 65534` get `HOME=/` from `/etc/passwd`. Since `/` is read-only, any command that writes to `$HOME` fails — including `git config --global`. Set `env: [{name: HOME, value: /tekton/home}]` explicitly on the step.

## Gitea sends `X-Gitea-Event`, not `X-GitHub-Event`

Tekton `github` ClusterInterceptor silently drops Gitea webhooks because Gitea sends `X-Gitea-Event` header instead. Use `cel` interceptor with `header.match('X-Gitea-Event', 'push')` instead.
