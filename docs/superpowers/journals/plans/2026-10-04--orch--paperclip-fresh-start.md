# Journal: 2026-10-04--orch--paperclip-fresh-start

<!-- fr:journal kind=decision scope=plan id=plan-shape created=2026-10-05T18:26:03+00:00 -->
### plan-shape · decision · One agentic phase + one trailing manual phase

All repo changes are one reviewable ask (one PR); the live sequence (pause hook, wipe, sweep, bootstrap) is real deploy work and goes in a trailing [manual] phase. Operator approved the shape; PR #820 is superseded and closes unmerged.

<!-- fr:journal kind=discovery scope=plan id=pod-cidr-measured created=2026-10-05T18:26:03+00:00 phase=1 -->
### pod-cidr-measured · discovery · Pod CIDRs all inside 10.244.0.0/16 (measured 2026-10-05) (phase 1)

Seven node /24s 10.244.7-13.0/24; TRUST_PROXY loopback,10.244.0.0/16 confirmed.

<!-- fr:journal kind=discovery scope=plan id=acceptance-row-shell-absent created=2026-10-05T18:47:07+00:00 phase=1 -->
### acceptance-row-shell-absent · discovery · No paperclip-shell acceptance row existed to retire (phase 1)

Only paperclip-litellm-agents-operable was in matrix.yaml; paperclip-shell-retired is this plan's own new row. Retired the former via fr acceptance set-status (status skipped, RETIRED note, prior evidence kept); the CLI committed it and regenerated the reports.

<!-- fr:journal kind=discovery scope=plan id=runbook-sources-in-implemented created=2026-10-05T18:47:07+00:00 phase=1 -->
### runbook-sources-in-implemented · discovery · Decommissioned runbook ops live in implemented/ specs and plans (phase 1)

Sources were docs/superpowers/implemented/specs/2026-05-17--orch--paperclip-litellm-agents-design.md and the paperclip-shell-sidecar plan (03.yaml + v1-archive), not plans/. Edited those plus manual-operations.yaml (status decommissioned + decommissioned: field, existing convention) and appended the 5 new blocks by hand rather than running a sync that would reformat the file. The orch-create-infisical-secrets note exists only in manual-operations.yaml (no source block), so it was corrected there only.

<!-- fr:journal kind=discovery scope=plan id=suite-excluded-hugo-files created=2026-10-05T18:47:07+00:00 phase=1 -->
### suite-excluded-hugo-files · discovery · Local suite excludes six hugo-referencing test files (phase 1)

Ignored test_blog_craft_version_pin_is_a_release, test_blog_ci_at_repo_root, test_image_optimization_adoption, test_mermaid_bundle_pinned, test_series_index_adoption, test_series_index_resync; CI runs them. Used the base clone's .venv pytest since the worktree has none.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t1 created=2026-10-05T18:47:07+00:00 phase=1 -->
### no-refactor-p1-t1 · discovery · no-refactor-because P1.T1 (phase 1)

Test-only task; the guard is already minimal.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-10-05T18:47:07+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

Manifests were rewritten to the stripped shape directly; nothing left to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-10-05T18:47:07+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

Pure deletions plus a doc-comment fix in the purge script.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t5 created=2026-10-05T18:47:07+00:00 phase=1 -->
### no-refactor-p1-t5 · discovery · no-refactor-because P1.T5 (phase 1)

Docs-only edits; historical content marked in place, not restructured.
