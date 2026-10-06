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

<!-- fr:journal kind=review scope=plan id=p1-review created=2026-10-05T19:00:01+00:00 phase=1 -->
### p1-review · review · Phase 1 code review: 10 findings (8 in, 2 out) (phase 1)

Dispatched code-reviewer, read-only, over f546afd0..e11e28a1 against spec + plan. Core change correct; R1/R2/R3/R8 met; findings were the TRUST_PROXY LB-path premise, doc leftovers, guard-test gaps, acceptance linkage, purge-script ids.

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · TRUST_PROXY pod-CIDR premise unverified for the LB path; negative R4 check missing (phase 1)

Cilium tunnel mode + eTP Cluster may SNAT LAN->.212 to an in-CIDR router IP; spec's negative curl in no verify block; no row asserts R4.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=out -->
### p1-r2 · finding [open] (reviewer: out of scope) · TRUST_PROXY trusts every pod, not only Traefik (phase 1)

Strict narrowing of the pre-v2026.916 trust-anyone state; residual risk needs a k8s NetworkPolicy (cnc-fru precedent) verified live.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · Building post References list deleted manifests as current (phase 1)

building/15-paperclip index.md References.

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · Operating post troubleshooting describes deleted paperclip-llm-key ES (phase 1)

operating/18-paperclip ExternalSecret Not Syncing.

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · Top diagrams/frontmatter still show shell/.221/llm-key as current; Four ExternalSecrets (phase 1)

Both posts.

<!-- fr:journal kind=finding scope=plan id=p1-r6 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=in -->
### p1-r6 · finding [open] (reviewer: in scope) · paperclip-pure-upstream-pod row not linked to its CI guard (phase 1)

levels {} / not-implemented.

<!-- fr:journal kind=finding scope=plan id=p1-r7 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=in -->
### p1-r7 · finding [open] (reviewer: in scope) · Guard test misses volume/envFrom refs, TRUST_PROXY token check, PATH in CM (phase 1)

test_paperclip_pure_upstream.py.

<!-- fr:journal kind=finding scope=plan id=p1-r8 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=in -->
### p1-r8 · finding [open] (reviewer: in scope) · Posts state the wipe happened 2026-10-04 though it is a pending post-merge op (phase 1)

Both posts.

<!-- fr:journal kind=finding scope=plan id=p1-r9 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=in -->
### p1-r9 · finding [open] (reviewer: in scope) · purge-fs keeps ids of companies the wipe destroys (phase 1)

scripts/paperclip-purge-fs.sh KEEP_ID/DELETED_IDS.

<!-- fr:journal kind=finding scope=plan id=p1-r10 created=2026-10-05T19:00:01+00:00 phase=1 state=open review_scope=out -->
### p1-r10 · finding [open] (reviewer: out of scope) · fr schema-migration collateral bundled in the PR (phase 1)

fr-profiles.yaml, unrelated _meta.yaml, matrix schema rewrite, staging-vcluster run files.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: TRUST_PROXY pod-CIDR premise unverified for the LB path; negative R4 check missing (phase 1)

paperclip-lb gets externalTrafficPolicy: Local (source IP preserved; L2 announce from gpu-1 only) + guard test test_lb_preserves_client_source_ip (red→green); negative forged-header curl added to orch-paperclip-bootstrap-admin verify in plan block and runbook; new post-merge row paperclip-forwarded-headers-trusted-from-cluster-only; spec records the premise.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=open resolves=p1-r2 out_of_scope=true -->
### p1-r2-resolved · finding [out-of-scope] · resolves p1-r2: TRUST_PROXY trusts every pod, not only Traefik (phase 1)

Not caused by this change — v2026.916 narrowed trust from any peer to the pod CIDR; this PR only declares it. A NetworkPolicy restricting ingress to traefik-system + tekton-pipelines needs live verification; follow-up issue at merge.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: Building post References list deleted manifests as current (phase 1)

References rewritten to current manifests + guard test; deleted files listed as historical.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=fixed resolves=p1-r4 -->
### p1-r4-resolved · finding [fixed] · resolves p1-r4: Operating post troubleshooting describes deleted paperclip-llm-key ES (phase 1)

Troubleshooting now lists/describes the three live ExternalSecrets.

<!-- fr:journal kind=finding scope=plan id=p1-r5-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=fixed resolves=p1-r5 -->
### p1-r5-resolved · finding [fixed] · resolves p1-r5: Top diagrams/frontmatter still show shell/.221/llm-key as current; Four ExternalSecrets (phase 1)

Both top diagrams redrawn to the pure-upstream pod; frontmatter reader_goal/summary/description updated; Three ExternalSecrets; Waves diagram ×3; banners moved above diagrams.

<!-- fr:journal kind=finding scope=plan id=p1-r6-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=fixed resolves=p1-r6 -->
### p1-r6-resolved · finding [fixed] · resolves p1-r6: paperclip-pure-upstream-pod row not linked to its CI guard (phase 1)

Row linked to 8 unit tests, status ci via fr acceptance set-status; reports in sync (--check).

<!-- fr:journal kind=finding scope=plan id=p1-r7-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=fixed resolves=p1-r7 -->
### p1-r7-resolved · finding [fixed] · resolves p1-r7: Guard test misses volume/envFrom refs, TRUST_PROXY token check, PATH in CM (phase 1)

Whole-Deployment scan for banned names + agent-bin, tokenised TRUST_PROXY, PATH in ConfigMap.

<!-- fr:journal kind=finding scope=plan id=p1-r8-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=fixed resolves=p1-r8 -->
### p1-r8-resolved · finding [fixed] · resolves p1-r8: Posts state the wipe happened 2026-10-04 though it is a pending post-merge op (phase 1)

Wipe described as the post-merge runbook step; retirement dates normalised to 2026-10.

<!-- fr:journal kind=finding scope=plan id=p1-r9-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=fixed resolves=p1-r9 -->
### p1-r9-resolved · finding [fixed] · resolves p1-r9: purge-fs keeps ids of companies the wipe destroys (phase 1)

KEEP_ID/DELETED_IDS emptied with a note; script exits early when empty, refuses an empty keeper.

<!-- fr:journal kind=finding scope=plan id=p1-r10-resolved created=2026-10-05T19:00:01+00:00 phase=1 state=open resolves=p1-r10 out_of_scope=true -->
### p1-r10-resolved · finding [out-of-scope] · resolves p1-r10: fr schema-migration collateral bundled in the PR (phase 1)

fr's own schema migration, required before fr would start the run; not caused by the feature. Called out in the PR body.
