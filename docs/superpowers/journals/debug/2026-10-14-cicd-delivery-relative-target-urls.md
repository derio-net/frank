<!-- fr:journal-schema=2 -->
# Journal: 2026-10-14-cicd-delivery-relative-target-urls

<!-- fr:journal kind=hypothesis scope=debug id=150b916cecda created=2026-10-14T19:55:09+00:00 -->
### 150b916cecda · hypothesis · Relative status API URLs explain the healthy-delivery warnings

Refs derio-net/frank#870. PR871 merged as 8bccbac78faa, preserving authenticated live evidence: all 22 findings have matching state/description and equivalent relative Gitea vs absolute GitHub target URLs. The bridge forwards webhook URLs verbatim; API.statuses normalizes Gitea state but leaves target_url relative, so matches compares different string representations. apps/gitea/values.yaml declares ROOT_URL http://192.168.55.209:3000/. Hypothesis: normalize Gitea status API targets against the declaratively configured web root at the adapter boundary, preserving raw cached data and genuinely distinct targets.
