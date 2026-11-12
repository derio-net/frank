<!-- fr:journal-schema=3 -->
# Journal: 2026-11-12--agents--retire-secure-agent-pod

<!-- fr:journal kind=decision scope=plan id=plan-one-agentic-phase created=2026-11-12T12:40:23+00:00 -->
### plan-one-agentic-phase · decision · One agentic phase for all git-state work, one back-loaded manual phase for the live sequence

R9-R15's git changes (removal, tombstones, tripwire, archive script, blog notices) are one
reviewable ask: retire the pod from git. The live sequence (archive, gates, merge, sweep,
explicit ClusterRoleBinding delete) is a back-loaded [manual] phase with 14 ops, because
the operator said the triage run is still going and no agentic phase may touch the pod.

<!-- fr:journal kind=discovery scope=plan id=plan-live-facts-2026-11-12 created=2026-11-12T12:40:23+00:00 -->
### plan-live-facts-2026-11-12 · discovery · Live state read on 2026-11-12 (read-only)

root Application: automated {prune: true, selfHeal: true}. ClusterGenerator
github-app-derio tracking id is already tekton-extras. ClusterRoleBinding
secure-agent-pod-cluster-admin exists and is tracked by the secure-agent-pod Application.
tekton-pipelines/github-app-derio-key exists (created 2026-07-25). The five rule uids are
present in the running Grafana (GET /api/v1/provisioning/alert-rules via the .203
LoadBalancer with the admin secret). Pushgateway is ClusterIP only. Pod home layout:
interviews 64M, orgs 77M, .hermes 424K, .willikins-agent/audit-archive,
.local/share/vibe-kanban/db.v2.sqlite, 12 git clones. agent-images#176 and bump PR
frank#953 are open.

<!-- fr:journal kind=decision scope=plan id=retired-status-word created=2026-11-12T13:03:55+00:00 phase=1 -->
### retired-status-word · decision · Retired ops use status: retired plus a retired: note (phase 1)

The spec says status: retired. Existing runbook entries use status: decommissioned with a decommissioned: note. I followed the spec (status: retired, retired: note) for the eight pod ops, and set it in the generated runbook directly because sync-runbook preserves an existing entry's status. Revisit if a validator ever whitelists status values.

<!-- fr:journal kind=decision scope=plan id=pod-ops-source-blocks created=2026-11-12T13:03:55+00:00 phase=1 -->
### pod-ops-source-blocks · decision · Pod manual ops retired in the three non-archive plan sources; v1-archive snapshots left alone (phase 1)

kali-cleanup (01.yaml), kali-cutover and sidecar-merge (02.yaml) now read status: retired. bootstrap-secrets, infisical-setup and the three agents-github-app-* ops exist only in the runbook (their v1-archive sources are frozen snapshots), so their runbook entries were flipped by hand. The key-apply and cicd-frank-gitops-push-derio-key commands now point at github-app-derio-key-tekton.yaml.

<!-- fr:journal kind=discovery scope=plan id=paper10-vk-is-virtual-keys created=2026-11-12T13:03:55+00:00 phase=1 -->
### paper10-vk-is-virtual-keys · discovery · papers/10-self-hosted-inference has no VibeKanban mention (phase 1)

The only VK there is LiteLLM's Virtual keys in a mermaid diagram, so no edit was made despite the spec listing the paper as a passing-mention fix.

<!-- fr:journal kind=discovery scope=plan id=pin-exceptions-absent created=2026-11-12T13:03:55+00:00 phase=1 -->
### pin-exceptions-absent · discovery · scripts/tests/fixtures/life/pin-exceptions.yaml is not on this branch (phase 1)

Test (f) in test_vk_retired.py passes vacuously. Whichever of frank#913 and this PR merges second must drop the vk-local and secure-agent-kali entries; the plan's leftovers op records this.

<!-- fr:journal kind=discovery scope=plan id=retire-vk-phase1-ops-untouched created=2026-11-12T13:03:55+00:00 phase=1 -->
### retire-vk-phase1-ops-untouched · discovery · Phase 1 manual ops of the retire-vk plan still name the pod namespace (phase 1)

agents-retire-vk-premerge/postmerge-sweep/fork-archive (plan 2026-11-08) check that the pod is untouched and that its ExternalSecrets stay synced. They are Phase 1 operations with status pending and were left as written; they are not this plan's to retire.

<!-- fr:journal kind=discovery scope=plan id=tooling-notes created=2026-11-12T13:03:55+00:00 phase=1 -->
### tooling-notes · discovery · Environment notes (phase 1)

No .venv in the worktree: used the base clone's .venv/bin/pytest read-only. The repo pre-commit dossier gate needs PyYAML, so commits touching papers need the venv bin first on PATH. shellcheck was installed and passes. fr acceptance report --check is in sync; fr acceptance check exits non-zero on pre-existing staleness rows unrelated to this change; fr docs check has no .fr/docs.yaml so owes nothing; fr plan self-review passed. Hugo was not run. Excluded four hugo-adjacent test files from the suite run: test_blog_ci_at_repo_root, test_image_optimization_adoption, test_series_index_adoption, test_series_index_resync (the last two were run separately and pass).

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t1 created=2026-11-12T13:03:55+00:00 phase=1 -->
### no-refactor-p1-t1 · discovery · no-refactor-because P1.T1 (phase 1)

Test-only red task; nothing to clean beyond removing the POD_DEPLOYMENT/POD_PIN/skip_pod scaffolding, which was done in the same edit.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-11-12T13:03:55+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

Pure deletions plus comment rewrites; parsed manifests compared before and after and are identical, nothing left to tidy.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t4 created=2026-11-12T13:03:55+00:00 phase=1 -->
### no-refactor-p1-t4 · discovery · no-refactor-because P1.T4 (phase 1)

Rule and panel removals only; both ConfigMaps load and every embedded JSON/YAML value parses; the Pod Status panel was kept and its regex trimmed.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t5 created=2026-11-12T13:03:55+00:00 phase=1 -->
### no-refactor-p1-t5 · discovery · no-refactor-because P1.T5 (phase 1)

Removals and wording changes only; the dead KALI_SHIM_CM constants and unused imports were dropped in the same edits.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t6 created=2026-11-12T13:03:55+00:00 phase=1 -->
### no-refactor-p1-t6 · discovery · no-refactor-because P1.T6 (phase 1)

Notice insertions and annotations; no structure to refactor.
