<!-- fr:journal-schema=4 -->
# Journal: 2026-11-14--auth--root-agents-least-privilege

<!-- fr:journal kind=discovery scope=plan id=p1-venv-linux created=2026-11-14T20:37:35+00:00 phase=1 -->
### p1-venv-linux · discovery · The worktree .venv is a Linux container venv (phase 1)

The worktree .venv/bin/python points at a linux interpreter, so it cannot run on the host. Tests ran via `fr isolation exec --branch feat/scope-root-agents-912 -- .venv/bin/python -m pytest`, and every shell command had to lead with `cd <worktree>` or the fr guard refuses it.

<!-- fr:journal kind=discovery scope=plan id=p1-sa-secret-readers created=2026-11-14T20:37:35+00:00 phase=1 -->
### p1-sa-secret-readers · discovery · Vendored Tekton controllers legitimately read Secrets cluster-wide (phase 1)

The R7 guard (any ServiceAccount outside the allowlist that can read Secrets in a protected namespace) flagged the vendored Tekton controllers, resolvers, webhook, core-interceptors and tekton-triggers-sa, whose ClusterRoles grant Secret reads. They are platform controllers, not agent identities, so each is in the guard's SA_ALLOWLIST with a reason. Narrowing them means forking apps/tekton/vendor.

<!-- fr:journal kind=discovery scope=plan id=p1-token-review-env created=2026-11-14T20:37:35+00:00 phase=1 -->
### p1-token-review-env · discovery · .env_agent variable names are unknown to the script (phase 1)

No file in the repo records the variable names inside .env_agent (the k8s-agent kubeconfig uses an exec plugin). token-review therefore mints via client_credentials and reads K8S_AGENT_CLIENT_SECRET (required), K8S_AGENT_CLIENT_ID (default k8s-agent) and K8S_AGENT_TOKEN_URL (default https://auth.cluster.derio.net/application/o/token/) from the environment. The operator must export the secret from .env_agent before the op. The token travels curl -> python -> kubectl on pipes only, and only status.user.groups is printed. Untested against live Authentik; only against a fake kubectl and curl.

<!-- fr:journal kind=discovery scope=plan id=p1-live-ns created=2026-11-14T20:37:35+00:00 phase=1 -->
### p1-live-ns · discovery · Every generated namespace exists live (phase 1)

Read-only `kubectl get ns` against Frank: 44 live namespaces; none of the 35 generated root-agents-rbac namespaces is missing, so the RoleBinding sync will not fail on an absent namespace. The three manifests pass `kubectl create --dry-run=client`.

<!-- fr:journal kind=discovery scope=plan id=p1-docs-check created=2026-11-14T20:37:35+00:00 phase=1 -->
### p1-docs-check · discovery · fr docs check does not apply (phase 1)

The repo has no .fr/docs.yaml, so `fr docs check` reports nothing to check; the blog page was still updated by hand (role table and the deliberate-decision paragraph).

<!-- fr:journal kind=discovery scope=plan id=p1-suite-scope created=2026-11-14T20:37:35+00:00 phase=1 -->
### p1-suite-scope · discovery · Suite excluded five hugo-related test files (phase 1)

Full suite run excluded test_image_optimization_adoption, test_series_index_adoption, test_series_index_resync, test_mermaid_bundle_pinned and test_blog_ci_at_repo_root. Result: 2379 passed, 17 skipped, exit 0 (the cel-python admission tests may skip on this interpreter and run in CI).

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-11-14T20:37:35+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

doc and comment rewording only; nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-11-14T20:37:35+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

quality gate task; no production code

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t4 created=2026-11-14T20:37:35+00:00 phase=1 -->
### no-refactor-p1-t4 · discovery · no-refactor-because P1.T4 (phase 1)

the script and its fake-kubectl test were written once; no duplication to remove
