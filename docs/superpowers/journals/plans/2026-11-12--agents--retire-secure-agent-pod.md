<!-- fr:journal-schema=4 -->
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

<!-- fr:journal kind=review scope=plan id=p1-review created=2026-11-12T13:44:44+00:00 phase=1 -->
### p1-review · review · independent code review of phase 1: 16 findings, all in scope, none critical (phase 1)

Read-only review of `git diff origin/main...HEAD` against spec, plan and ops.yaml. Verdict: the
git-state removal is clean and complete (root renders 66 Applications, no dangling references,
exactly five uids tombstoned, comment-only edits changed no parsed YAML, remaining-workload test
coverage intact, tripwire real). The archive script and ops.yaml had real holes: p1-r1..p1-r8
important, p1-r9..p1-r16 minor. All sixteen were fixed: p1-r7, r8, r10, r11, r16 in ops.yaml and
the plan prose by the orchestrator; p1-r1..r6, r9, r12..r15 by the implementer with tests.

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · verify passes a truncated tarball (tar error swallowed) and a truncated bundle (list-heads fallback is header-only) (phase 1)

scripts/retire-secure-agent-pod.sh verify and archive never tested the stream; MANIFEST is computed after transfer.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · git/exec failure during local-only detection is recorded as zero, so the clone lands in NONE.txt with no bundle (phase 1)

`rev-list … || echo 0` and `for-each-ref … || true` hid failures.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · session guard false negatives: pipefail+grep -q on large ps output, pattern misses cli.js/versioned binary/tmux/hermes (phase 1)

R9's 'confirms no interactive session remains' was not met.

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · key-fingerprint cannot compare the deleted SOPS file from the only tree where the script exists; gate silently weaker than spec (phase 1)

The PR deletes the old key file, so the script compared the Tekton copy only and passed.

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · credential exclusion misses .credentials.json and .hermes/.env/auth.json and is tested only by source grep (phase 1)

The fixture held no credential file.

<!-- fr:journal kind=finding scope=plan id=p1-r6 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r6 · finding [open] (reviewer: in scope) · tar aborts on files changing on a live pod, sqlite copied without WAL, missing path aborts the run (phase 1)

From GNU tar's documented behaviour; not reproduced against the pod.

<!-- fr:journal kind=finding scope=plan id=p1-r7 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r7 · finding [open] (reviewer: in scope) · step-11 check can pass on a bump run that predates the agent-images kali-removal merge (phase 1)

ops.yaml step-11 accepted the first run after the Frank merge.

<!-- fr:journal kind=finding scope=plan id=p1-r8 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r8 · finding [open] (reviewer: in scope) · step-10 check is instantaneous; Test Plan row 10 requires an hour (phase 1)

ops.yaml step-10 could pass seconds after the silence was deleted.

<!-- fr:journal kind=finding scope=plan id=p1-r9 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r9 · finding [open] (reviewer: in scope) · bundles cover only refs/heads: detached HEAD commits, stashes and local tags are dropped; stale bundles survive re-runs (phase 1)

Agent worktrees are detached by convention.

<!-- fr:journal kind=finding scope=plan id=p1-r10 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r10 · finding [open] (reviewer: in scope) · three ops sub-checks pass vacuously when kubectl fails (phase 1)

`! kubectl … | grep -q` and `test -z "$(kubectl … | python3 …)"` are true on error.

<!-- fr:journal kind=finding scope=plan id=p1-r11 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r11 · finding [open] (reviewer: in scope) · sweep-revisions syncs root without prune and its check ignores operationState.phase (phase 1)

A failed sync at the right revision passed.

<!-- fr:journal kind=finding scope=plan id=p1-r12 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r12 · finding [open] (reviewer: in scope) · always-loaded rules wrong: FR_ISOLATION_TARGET bullet marked HISTORICAL though hermes still uses it; repo-workflows.md says both agent pods (phase 1)

agents/rules/frank-gotchas.md, agents/rules/repo-workflows.md.

<!-- fr:journal kind=finding scope=plan id=p1-r13 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r13 · finding [open] (reviewer: in scope) · agents-github-app-provision and agents-clawdia-retire retired with an inaccurate reason, beyond the spec's list (phase 1)

docs/runbooks/manual-operations.yaml.

<!-- fr:journal kind=finding scope=plan id=p1-r14 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r14 · finding [open] (reviewer: in scope) · script test never exercises --not --remotes against a real remote (phase 1)

The bundle fixture had no remote.

<!-- fr:journal kind=finding scope=plan id=p1-r15 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r15 · finding [open] (reviewer: in scope) · stale comments in test_claude_autoupdater_disabled.py and test_vk_retired.py describe removed kali behaviour (phase 1)

Comments only.

<!-- fr:journal kind=finding scope=plan id=p1-r16 created=2026-11-12T13:44:44+00:00 phase=1 state=open review_scope=in -->
### p1-r16 · finding [open] (reviewer: in scope) · manual-op block and ops.yaml name different revision fields for the same sync check (phase 1)

_prose.md said operation.sync.revision; ops.yaml reads syncResult.revision.

<!-- fr:journal kind=discovery scope=plan id=p1-script-live-paths-unexercised created=2026-11-12T13:44:44+00:00 phase=1 -->
### p1-script-live-paths-unexercised · discovery · Three script paths cannot be exercised off the pod (phase 1)

GNU tar's exit-1 tolerance, sops decryption from /dev/stdin, and the FIFO digest over a real
`kubectl exec` are covered only by stubs on macOS (bsdtar). Their first real run is the
operator's `archive` / `key-fingerprint`, both read-only, so a failure there is safe and visible.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: verify passes a truncated tarball (tar error swallowed) and a truncated bundle (list-heads fallback is header-only) (phase 1)

archive and verify require gzip -t and tar -tzf to pass; the pod emits a sha256 per stream, compared locally and stored in REMOTE.sha256; bundles get a pack-trailer check. Tests: test_truncated_tarball_stream_fails_archive, test_verify_fails_on_a_truncated_tarball, test_verify_fails_on_a_truncated_bundle.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: git/exec failure during local-only detection is recorded as zero, so the clone lands in NONE.txt with no bundle (phase 1)

git failures abort the run. Test: test_a_failing_rev_list_fails_the_run.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: session guard false negatives: pipefail+grep -q on large ps output, pattern misses cli.js/versioned binary/tmux/hermes (phase 1)

Guard matches over a here-string with a wider pattern, exempting remote-control. Tests: test_session_guard_catches_herdr_tmux_node_and_versioned_claude, test_session_guard_survives_a_huge_listing.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r4 -->
### p1-r4-resolved · finding [fixed] · resolves p1-r4: key-fingerprint cannot compare the deleted SOPS file from the only tree where the script exists; gate silently weaker than spec (phase 1)

The deleted file is read from origin/main and decrypted through a pipe; absent in both places fails unless --old-file-gone-ok; empty values rejected. Tests: test_key_fingerprint_compares_the_deleted_file_from_origin_main, test_key_fingerprint_fails_when_the_old_file_cannot_be_found, test_key_fingerprint_rejects_empty_values.

<!-- fr:journal kind=finding scope=plan id=p1-r5-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r5 -->
### p1-r5-resolved · finding [fixed] · resolves p1-r5: credential exclusion misses .credentials.json and .hermes/.env/auth.json and is tested only by source grep (phase 1)

One CRED_NAMES list feeds the excludes and verify's member check. Test: test_credentials_are_excluded_at_depth_and_verify_rejects_them.

<!-- fr:journal kind=finding scope=plan id=p1-r6-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r6 -->
### p1-r6-resolved · finding [fixed] · resolves p1-r6: tar aborts on files changing on a live pod, sqlite copied without WAL, missing path aborts the run (phase 1)

Paths are probed first (SKIPPED.txt; verify fails on a skipped essential), sqlite -wal/-shm included, GNU tar exit 1 tolerated with a warning. Tests: test_missing_optional_path_is_skipped_but_essentials_fail_verify, test_sqlite_wal_and_shm_are_archived_when_present.

<!-- fr:journal kind=finding scope=plan id=p1-r7-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r7 -->
### p1-r7-resolved · finding [fixed] · resolves p1-r7: step-11 check can pass on a bump run that predates the agent-images kali-removal merge (phase 1)

step-11 now requires kali absent from agent-images main and takes the first run created after both the Frank merge and the kali-removal commit.

<!-- fr:journal kind=finding scope=plan id=p1-r8-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r8 -->
### p1-r8-resolved · finding [fixed] · resolves p1-r8: step-10 check is instantaneous; Test Plan row 10 requires an hour (phase 1)

sweep-silence-delete records its time; step-10 requires 3600 s to have elapsed.

<!-- fr:journal kind=finding scope=plan id=p1-r9-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r9 -->
### p1-r9-resolved · finding [fixed] · resolves p1-r9: bundles cover only refs/heads: detached HEAD commits, stashes and local tags are dropped; stale bundles survive re-runs (phase 1)

Candidate refs are heads, tags, stash and a detached HEAD; uncovered worktree HEADs go to DETACHED.txt as a warning; outputs are cleared per run. Tests: test_tags_stash_and_detached_work_are_covered, test_rerun_clears_stale_bundles.

<!-- fr:journal kind=finding scope=plan id=p1-r10-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r10 -->
### p1-r10-resolved · finding [fixed] · resolves p1-r10: three ops sub-checks pass vacuously when kubectl fails (phase 1)

The three sub-checks capture kubectl output first and require it non-empty; the binding scan prints NONE explicitly.

<!-- fr:journal kind=finding scope=plan id=p1-r11-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r11 -->
### p1-r11-resolved · finding [fixed] · resolves p1-r11: sweep-revisions syncs root without prune and its check ignores operationState.phase (phase 1)

root's sync operation carries prune true; the check requires operationState.phase Succeeded and a non-empty revision.

<!-- fr:journal kind=finding scope=plan id=p1-r12-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r12 -->
### p1-r12-resolved · finding [fixed] · resolves p1-r12: always-loaded rules wrong: FR_ISOLATION_TARGET bullet marked HISTORICAL though hermes still uses it; repo-workflows.md says both agent pods (phase 1)

The FR_ISOLATION_TARGET bullet is present tense and hermes-only; the Recreate + RWO bullet is a retired incident with a live lesson; repo-workflows.md names hermes-agent-shell.

<!-- fr:journal kind=finding scope=plan id=p1-r13-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r13 -->
### p1-r13-resolved · finding [fixed] · resolves p1-r13: agents-github-app-provision and agents-clawdia-retire retired with an inaccurate reason, beyond the spec's list (phase 1)

Both operations restored to done and re-homed (tekton, bootstrap); only the pod-namespace command line is marked retired.

<!-- fr:journal kind=finding scope=plan id=p1-r14-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r14 -->
### p1-r14-resolved · finding [fixed] · resolves p1-r14: script test never exercises --not --remotes against a real remote (phase 1)

The fixture has a bare remote. Test: test_bundle_excludes_pushed_branch_and_keeps_local_only.

<!-- fr:journal kind=finding scope=plan id=p1-r15-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r15 -->
### p1-r15-resolved · finding [fixed] · resolves p1-r15: stale comments in test_claude_autoupdater_disabled.py and test_vk_retired.py describe removed kali behaviour (phase 1)

Both comments rewritten.

<!-- fr:journal kind=finding scope=plan id=p1-r16-resolved created=2026-11-12T13:44:44+00:00 phase=1 state=fixed resolves=p1-r16 -->
### p1-r16-resolved · finding [fixed] · resolves p1-r16: manual-op block and ops.yaml name different revision fields for the same sync check (phase 1)

The manual-op block now names operationState.phase and syncResult.revision, and the runbook was resynced.

<!-- fr:journal kind=owed scope=plan id=manual-phase-2 created=2026-11-13T22:13:10+00:00 phase=2 -->
### manual-phase-2 · owed · 2026-11-12--agents--retire-secure-agent-pod: manual phase 2 is not ticked (phase 2)

what: do manual phase 2 of 2026-11-12--agents--retire-secure-agent-pod and tick its steps
why: fr archive holds the plan until its manual phases are ticked
how: tick phase 2 (fr plan edit --tick), then fr archive docs/superpowers/plans/2026-11-12--agents--retire-secure-agent-pod
owed_key: plan:2026-11-12--agents--retire-secure-agent-pod#p2

<!-- fr:journal kind=finding scope=plan id=manual-phase-2-resolved created=2026-11-13T22:13:14+00:00 phase=2 state=open resolves=manual-phase-2 filed_as=derio-net/frank#974 -->
### manual-phase-2-resolved · finding [filed → derio-net/frank#974] · resolves manual-phase-2: 2026-11-12--agents--retire-secure-agent-pod: manual phase 2 is not ticked (phase 2)

Filed at archive as derio-net/frank#974; still owed until discharged.
