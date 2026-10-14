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
