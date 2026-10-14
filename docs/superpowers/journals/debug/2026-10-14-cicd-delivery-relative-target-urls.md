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
