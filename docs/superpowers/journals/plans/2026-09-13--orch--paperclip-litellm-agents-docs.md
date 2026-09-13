# Journal: 2026-09-13--orch--paperclip-litellm-agents-docs

<!-- fr:journal kind=decision scope=plan id=p2-inline created=2026-09-13T22:19:19 phase=2 -->
### p2-inline · decision · Phases 1-2 executed inline by the orchestrator, not via fr-phase-executor (phase 2)

The live-cluster fact-finding that framed the operator Q&A was also the red half of every phase 2 task, so the content edits were made during brainstorm/spec-review, before the plan existed. Re-dispatching them to a phase executor would have repeated finished work. Evidence: commit b96048ba, validate_educational POST QUALITY OK on both posts, actionable-sections tripwire 78 passed, hugo --minify rc=0, all 9 new anchors present with no dangling in-page hrefs.

<!-- fr:journal kind=decision scope=plan id=no-refactor-because-P1.T1 created=2026-09-13T22:19:21 phase=1 -->
### no-refactor-because-P1.T1 · decision · no-refactor-because: P1.T1 only exercises existing gates (phase 1)

No code or content is written in the walking-skeleton task.

<!-- fr:journal kind=finding scope=plan id=rv1-cold-pvc-reconcile created=2026-09-13T22:28:58 phase=2 state=fixed -->
### rv1-cold-pvc-reconcile · finding [fixed] · critical: cold-PVC step claimed paperclip-shell-reconcile restores hermes/opencode (phase 2)

The reconcile only handles mise/npm-global/pipx/cargo; the inventory's uv and paperclip-shared sections are manual (configmap-shell-inventory.yaml:50-66). Replaced with the documented manual install commands.

<!-- fr:journal kind=finding scope=plan id=rv2-revert-pr created=2026-09-13T22:29:00 phase=2 state=fixed -->
### rv2-revert-pr · finding [fixed] · Missteps row cited #296 as the revert; the revert is #297 (phase 2)

0f9b6331 (#296) shipped the wrapper; eea8fd89 (#297) reverted it.

<!-- fr:journal kind=finding scope=plan id=rv3-psql-password created=2026-09-13T22:29:01 phase=2 state=fixed -->
### rv3-psql-password · finding [fixed] · psql recipes fail with fe_sendauth: no password supplied (phase 2)

The db container needs POSTGRES_PASSWORD; recipes now exec -c postgresql with PGPASSWORD from the container env, and the stranded-agent UPDATE gets an interactive session.

<!-- fr:journal kind=finding scope=plan id=rv4-prefix-list created=2026-09-13T22:29:03 phase=2 state=fixed -->
### rv4-prefix-list · finding [fixed] · Prefix-hint list incomplete (o4-, moonshot, minimax) (phase 2)

Listed every non-auto prefix from constants.ts at sha-8e6edcd; huggingface/ omitted because inferProviderFromModel strips provider/ before startsWith, so it cannot match.

<!-- fr:journal kind=finding scope=plan id=rv5-hire-form created=2026-09-13T22:29:05 phase=2 state=fixed -->
### rv5-hire-form · finding [fixed] · Hire-form claims were API-only or contradicted the table (phase 2)

persistSession is a UI toggle defaulting true; Provider is a select limited to VALID_PROVIDERS; the UI splits extraArgs on whitespace. Scoped the ignored/dropped claims to adapter config sent via the API.

<!-- fr:journal kind=finding scope=plan id=rv6-qr-grep created=2026-09-13T22:29:06 phase=2 state=fixed -->
### rv6-qr-grep · finding [fixed] · Quick Reference lacked the routing-grep row the spec asks for (phase 2)

<!-- fr:journal kind=finding scope=plan id=rv7-last-updated-commit created=2026-09-13T22:29:08 phase=2 state=fixed -->
### rv7-last-updated-commit · finding [fixed] · operating/18 last_updated_commit never scheduled for update (phase 2)

Added to phase 3's rebase step.

<!-- fr:journal kind=finding scope=plan id=rv8-what-transfers-grammar created=2026-09-13T22:29:10 phase=2 state=fixed -->
### rv8-what-transfers-grammar · finding [fixed] · What Transfers sentence did not parse (phase 2)

<!-- fr:journal kind=finding scope=plan id=rv9-rebase-conflicts created=2026-09-13T22:29:11 phase=2 state=fixed -->
### rv9-rebase-conflicts · finding [fixed] · Phase 3 expected a rebase conflict only in building/15 (phase 2)

#787 also adds description: to operating/18 frontmatter.

<!-- fr:journal kind=finding scope=plan id=rv10-prose-stale created=2026-09-13T22:29:13 phase=2 state=fixed -->
### rv10-prose-stale · finding [fixed] · Plan prose said the acceptance row could not be appended (phase 2)

The row already exists; prose now matches 04.yaml.

<!-- fr:journal kind=discovery scope=plan id=d-live-poisoned-row created=2026-09-13T22:31:01 phase=2 -->
### d-live-poisoned-row · discovery · A poisoned hermes_local session row exists on the live cluster (phase 2)

The corrected detection query (run read-only 2026-09-13) returned one agent_task_sessions row: session_display_id=from, session_params_json={"sessionId": "from"}, last_error=run_failed. This is the exact paperclip#1 stranded shape, left over although no hermes_local agent is hired now. Not cleared: mutating live DB state is the operator's call. It also proves the recipe detects the real failure.
