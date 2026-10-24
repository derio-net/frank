<!-- fr:journal-schema=2 -->
# Journal: 2026-10-14-cicd-delivery-relative-target-urls

<!-- fr:journal kind=hypothesis scope=debug id=150b916cecda created=2026-10-14T19:55:09+00:00 -->
### 150b916cecda · hypothesis · Relative status API URLs explain the healthy-delivery warnings

Refs derio-net/frank#870. PR871 merged as 8bccbac78faa, preserving authenticated live evidence: all 22 findings have matching state/description and equivalent relative Gitea vs absolute GitHub target URLs. The bridge forwards webhook URLs verbatim; API.statuses normalizes Gitea state but leaves target_url relative, so matches compares different string representations. apps/gitea/values.yaml declares ROOT_URL http://192.168.55.209:3000/. Hypothesis: normalize Gitea status API targets against the declaratively configured web root at the adapter boundary, preserving raw cached data and genuinely distinct targets.

<!-- fr:journal kind=repro scope=debug id=4ccd47f11aa5 created=2026-10-14T19:56:21+00:00 -->
### 4ccd47f11aa5 · repro · Observed relative/absolute pair reproduces one false overdue count

RED: uv run pytest -q scripts/tests/test_ci_delivery_check.py -k live_relative_gitea_target failed: expected mirror=0,status=0 but got status=1 with errors=0 (1 failed, 67 deselected). The fixture runs the extracted deployed checker through real API adapters with injected forge responses containing the observed #870 URL pair. States/descriptions and SHA match; only representation differs. No production code changed.

<!-- fr:journal kind=root-cause scope=debug id=ee8d2c6ce370 created=2026-10-14T19:57:37+00:00 -->
### ee8d2c6ce370 · root-cause · Gitea API adapter leaves relative links incomparable with webhook delivery

Confirmed by original authenticated probes and failing adapter-level regression: Gitea status API returns a relative Actions link while the successfully forwarded GitHub status contains the absolute Gitea ROOT_URL-based link. Literal tuple comparison produces overdue findings. Root resolution belongs in API.statuses beside the existing status/state adaptation, not in alert predicates or bridge writes. Additional RED cases: 7 failed, 8 passed, 67 deselected for configured root/subpath, absent/unusable root, equivalent live URLs; negative destination identity and empty/absolute URL cases already pass.

<!-- fr:journal kind=finding scope=debug id=bd5918903516 created=2026-10-14T19:59:01+00:00 state=fixed -->
### bd5918903516 · finding [fixed] · Resolve Gitea status targets using the declared web root

API.statuses now resolves nonempty relative Gitea targets against CronJob GITEA_WEB_URL, matching apps/gitea/values.yaml server.ROOT_URL. Absolute and absent/empty URLs retain their semantics; raw cached responses are not mutated, and state/description/URL mismatches still warn. Missing/unusable web root raises a checker read error for relative targets. GREEN: 94 checker and outcome-alert tests passed, including the observed #870 regression, alternative configured root/subpath, changed host/scheme/run/query/fragment, empty/absolute targets and root parity. Production deployment and original step4 stay owed until merge and live re-walk.

<!-- fr:journal kind=finding scope=debug id=c1009f631781 created=2026-10-14T20:08:31+00:00 state=fixed -->
### c1009f631781 · finding [fixed] · Full verification passed for the URL normalization patch

uv run pytest -q scripts/tests/: 1272 passed, 9 skipped, 1 xfailed in 312.22s. The initial 120-second run timed out; completed rerun used a 600-second budget. hugo --source blog --minify completed successfully (155 pages, 576 processed images); first cold build exceeded 120 seconds, rerun passed. scripts/validate-agent-config.sh passed; scripts/validate-plans.sh passed minimal fallback checks with canonical super-fr validator unavailable. Documentation now explains ROOT_URL vs in-cluster API addressing and genuinely different links. Original ci-real-work-delivery row remains failing and step4 owed pending corrected scheduled snapshots and Grafana recovery after merge.

<!-- fr:journal kind=owed scope=debug id=post-merge-url-recovery created=2026-10-14T20:10:14+00:00 -->
### post-merge-url-recovery · owed · Verify scheduled healthy delivery and clear the original live gate after merge

what: After PR872 merges, verify live ci-delivery-check script and GITEA_WEB_URL match the fix; observe scheduled snapshots with fresh timestamp, zero read errors and healthy delivery counts; assert Grafana overdue instances recover. Record the ci-real-work-delivery passing walk, resolve original actionable-alerts Test Plan step4, clear its DevOps gate and archive only after that evidence. Close frank#870 on live evidence.
why: The fix is offline-proven but production still runs the merged original checker. The original failing acceptance row and owed step4 must not be cleared before deployment.
how: From the base clone run fr pickup --branch fix/cicd-delivery-relative-target-urls after merge. Use the operator-selected cluster-admin workspace for live checks and a fresh closeout isolation workspace for records; resolve original Test Plan step4 and this debug owed entry with actual recovery evidence.
owed_key: row:ci-real-work-delivery

<!-- fr:journal kind=review scope=debug id=dfa2a95c8a85 created=2026-10-14T20:10:35+00:00 -->
### dfa2a95c8a85 · review · Inline code review completed with no outstanding findings

Reviewed the complete diff against #870, the original actionable-alerts requirements and repository reviewer criteria. No outstanding findings. Checked adapter-only normalization, matching declared public root, empty/absolute target semantics, rejection of genuinely different URL identities, cached response immutability, configured-root errors, credential-safe diagnostics and unchanged read-only execution. Regression demonstrably failed first; affected suites and full suite pass. Review was inline, not a separate subagent review. PR872 is draft; operator review/ready transition and post-merge live verification remain required. New debug owed key row:ci-real-work-delivery links the correction to the original failing acceptance and owed step4.

<!-- fr:journal kind=finding scope=debug id=post-merge-url-recovery-resolved created=2026-10-14T20:25:19+00:00 state=fixed resolves=post-merge-url-recovery -->
### post-merge-url-recovery-resolved · finding [fixed] · resolves post-merge-url-recovery: Verify scheduled healthy delivery and clear the original live gate after merge

2026-10-14 PR872 deployment and recovery verified: script hash and GITEA_WEB_URL match merged fix; scheduled ci-delivery-check-29866820 succeeded; all monitored overdue/read-error counts zero; timestamp fresh; logs empty; all Grafana delivery rules inactive/healthy. ci-real-work-delivery passing live walk recorded and original Test Plan step4 resolved. Evidence: docs/investigations/2026-10-14--cicd--delivery-url-closeout.md#recovery-after-pr-872.
