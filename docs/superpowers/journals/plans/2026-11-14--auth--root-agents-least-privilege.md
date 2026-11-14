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

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · token-review client-credentials mode likely authenticates as the synthetic user, not claude-agent (phase 1)

token-review client-credentials mode likely authenticates as the synthetic user, not claude-agent

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · token-review passes on an unauthenticated TokenReview (phase 1)

token-review passes on an unauthenticated TokenReview

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · token-review env vars undocumented; sourcing .env_agent repoints KUBECONFIG (phase 1)

token-review env vars undocumented; sourcing .env_agent repoints KUBECONFIG

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · guard does not forbid get on pods/exec, portforward, nodes/proxy, services/proxy (phase 1)

guard does not forbid get on pods/exec, portforward, nodes/proxy, services/proxy

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · guard allows a root-agents ClusterRoleBinding to namespaced kinds cluster-wide (phase 1)

guard allows a root-agents ClusterRoleBinding to namespaced kinds cluster-wide

<!-- fr:journal kind=finding scope=plan id=p1-r6 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r6 · finding [open] (reviewer: in scope) · guard fails open on unresolved roles, aggregation and User subjects (phase 1)

guard fails open on unresolved roles, aggregation and User subjects

<!-- fr:journal kind=finding scope=plan id=p1-r7 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r7 · finding [open] (reviewer: in scope) · no audit of ConfigMaps, pod env and pod logs in credential-store namespaces (phase 1)

no audit of ConfigMaps, pod env and pod logs in credential-store namespaces

<!-- fr:journal kind=finding scope=plan id=p1-r8 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r8 · finding [open] (reviewer: in scope) · SA allowlist wildcards and six tekton entries (phase 1)

SA allowlist wildcards and six tekton entries

<!-- fr:journal kind=finding scope=plan id=p1-r9 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r9 · finding [open] (reviewer: in scope) · docs state the gap closed before the cutover has run (phase 1)

docs state the gap closed before the cutover has run

<!-- fr:journal kind=finding scope=plan id=p1-r10 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=in -->
### p1-r10 · finding [open] (reviewer: in scope) · live namespace-exists check is prose only (phase 1)

live namespace-exists check is prose only

<!-- fr:journal kind=finding scope=plan id=p1-r11 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=out -->
### p1-r11 · finding [open] (reviewer: out of scope) · vendored Tekton controllers read Secrets cluster-wide: a platform fact (phase 1)

vendored Tekton controllers read Secrets cluster-wide: a platform fact

<!-- fr:journal kind=finding scope=plan id=p1-r12 created=2026-11-14T20:43:42+00:00 phase=1 state=open review_scope=out -->
### p1-r12 · finding [open] (reviewer: out of scope) · Helm-rendered RBAC is invisible to a repo-static guard (phase 1)

Helm-rendered RBAC is invisible to a repo-static guard

<!-- fr:journal kind=review scope=plan id=review-p1 created=2026-11-14T20:43:42+00:00 phase=1 -->
### review-p1 · review · independent review of phase 1: 12 findings (10 in scope, 2 out) (phase 1)

Reviewer read the RBAC manifests, generator, guard, cutover script and tests, coupled docs, manual operation and spec; verified no secrets, wildcards, impersonate/bind/escalate or write verbs in either role and no generated binding in the protected namespaces. It ran nothing.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r1 -->
### p1-r1-resolved · finding [fixed] · resolves p1-r1: token-review client-credentials mode likely authenticates as the synthetic user, not claude-agent (phase 1)

token-review gained a service-account mode (K8S_AGENT_USERNAME/PASSWORD) and prints the resolved username; the spec records that client id+secret alone yields the synthetic user. Which mode the operator uses stays unverifiable from the repo, so the cutover op runs the second mode.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: token-review passes on an unauthenticated TokenReview (phase 1)

token-review now requires status.authenticated=true; test added.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: token-review env vars undocumented; sourcing .env_agent repoints KUBECONFIG (phase 1)

The manual operation documents the variables and says not to source .env_agent.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r4 -->
### p1-r4-resolved · finding [fixed] · resolves p1-r4: guard does not forbid get on pods/exec, portforward, nodes/proxy, services/proxy (phase 1)

pods/exec, attach, portforward, pods/proxy, nodes/proxy and services/proxy are forbidden resources.

<!-- fr:journal kind=finding scope=plan id=p1-r5-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r5 -->
### p1-r5-resolved · finding [fixed] · resolves p1-r5: guard allows a root-agents ClusterRoleBinding to namespaced kinds cluster-wide (phase 1)

A root-agents ClusterRoleBinding may name only cluster-scoped kinds (CLUSTER_SCOPED).

<!-- fr:journal kind=finding scope=plan id=p1-r6-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r6 -->
### p1-r6-resolved · finding [fixed] · resolves p1-r6: guard fails open on unresolved roles, aggregation and User subjects (phase 1)

Aggregation (aggregationRule or aggregate-to labels) now fails the guard. An unresolved role already fails for root-agents bindings (rules asserted non-empty); unresolved or Helm-rendered roles of other subjects are the platform limit in p1-r12; User subjects named root-agents do not exist, and the Group subject is what Authentik emits.

<!-- fr:journal kind=finding scope=plan id=p1-r7-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=refuted resolves=p1-r7 -->
### p1-r7-resolved · finding [refuted] · resolves p1-r7: no audit of ConfigMaps, pod env and pod logs in credential-store namespaces (phase 1)

The spec's Design states the choice (pods, ConfigMaps, logs in those namespaces, never Secrets) and the operator confirmed it. The agents get strictly less than root-developers, which already holds the built-in view cluster-wide. Credential material in a ConfigMap or pod env is a separate, pre-existing exposure of that group.

<!-- fr:journal kind=finding scope=plan id=p1-r8-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r8 -->
### p1-r8-resolved · finding [fixed] · resolves p1-r8: SA allowlist wildcards and six tekton entries (phase 1)

The wildcard entries are replaced by the four named session ServiceAccounts; runs-fr needs none. The tekton entries stay, each with a reason and a ClusterRoleBinding in this repo.

<!-- fr:journal kind=finding scope=plan id=p1-r9-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r9 -->
### p1-r9-resolved · finding [fixed] · resolves p1-r9: docs state the gap closed before the cutover has run (phase 1)

The briefs, the blog and the cutover wording now say the second half closes when the cutover has run.

<!-- fr:journal kind=finding scope=plan id=p1-r10-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=fixed resolves=p1-r10 -->
### p1-r10-resolved · finding [fixed] · resolves p1-r10: live namespace-exists check is prose only (phase 1)

scripts/root-agents-cutover.sh namespaces compares the generated set to the live cluster; premerge-namespaces op and Test Plan line added.

<!-- fr:journal kind=finding scope=plan id=p1-r11-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=open resolves=p1-r11 out_of_scope=true -->
### p1-r11-resolved · finding [out-of-scope] · resolves p1-r11: vendored Tekton controllers read Secrets cluster-wide: a platform fact (phase 1)

Platform fact, not caused by this change.

<!-- fr:journal kind=finding scope=plan id=p1-r12-resolved created=2026-11-14T20:43:42+00:00 phase=1 state=open resolves=p1-r12 out_of_scope=true -->
### p1-r12-resolved · finding [out-of-scope] · resolves p1-r12: Helm-rendered RBAC is invisible to a repo-static guard (phase 1)

Limit of any repo-static guard, not caused by this change.

<!-- fr:journal kind=finding scope=plan id=l-security-r1 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-security-r1 · finding [open] (reviewer: in scope) · root-agents-ns-read grants pods/log, configmaps and pod specs in credential-store namespaces; the matrix tests only secrets

root-agents-ns-read grants pods/log, configmaps and pod specs in credential-store namespaces; the matrix tests only secrets

<!-- fr:journal kind=finding scope=plan id=l-security-r2 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-security-r2 · finding [open] (reviewer: in scope) · ops.yaml cutover-token-review check re-runs the apply and mints a second token

ops.yaml cutover-token-review check re-runs the apply and mints a second token

<!-- fr:journal kind=finding scope=plan id=l-tests-r1 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-tests-r1 · finding [open] (reviewer: in scope) · freshness test restates the generator; no independent namespace pin

freshness test restates the generator; no independent namespace pin

<!-- fr:journal kind=finding scope=plan id=l-tests-r2 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-tests-r2 · finding [open] (reviewer: in scope) · hop/ prefix assertion can never fail

hop/ prefix assertion can never fail

<!-- fr:journal kind=finding scope=plan id=l-tests-r3 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-tests-r3 · finding [open] (reviewer: in scope) · namespaces and move-membership subcommands untested

namespaces and move-membership subcommands untested

<!-- fr:journal kind=finding scope=plan id=l-tests-r4 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-tests-r4 · finding [open] (reviewer: in scope) · verify tested against only one broken cell

verify tested against only one broken cell

<!-- fr:journal kind=finding scope=plan id=l-tests-r5 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-tests-r5 · finding [open] (reviewer: in scope) · matrix test substring-only; generated-file precheck untested

matrix test substring-only; generated-file precheck untested

<!-- fr:journal kind=finding scope=plan id=l-tests-r6 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-tests-r6 · finding [open] (reviewer: in scope) · fake curl discards stdin and args; secret handling unverified

fake curl discards stdin and args; secret handling unverified

<!-- fr:journal kind=finding scope=plan id=l-tests-r7 created=2026-11-14T20:47:46+00:00 state=open review_scope=in -->
### l-tests-r7 · finding [open] (reviewer: in scope) · guard seen>=2 is loose and the cluster-read binding is not required

guard seen>=2 is loose and the cluster-read binding is not required

<!-- fr:journal kind=finding scope=plan id=l-tests-r8 created=2026-11-14T20:47:46+00:00 state=open review_scope=out -->
### l-tests-r8 · finding [open] (reviewer: out of scope) · guard scans only apps/*.yaml; pre-existing scope

guard scans only apps/*.yaml; pre-existing scope

<!-- fr:journal kind=review scope=plan id=lens-review-1 created=2026-11-14T20:47:46+00:00 -->
### lens-review-1 · review · lens review: security (2 findings), tests (8 findings)

One dispatched reviewer per lens over the diff from the merge base. Security found no injection, token leak or ordering defect in the cutover script; tests found the generator, deny cells, move-membership and secret handling under-tested.

<!-- fr:journal kind=finding scope=plan id=l-security-r1-resolved created=2026-11-14T20:47:46+00:00 state=refuted resolves=l-security-r1 -->
### l-security-r1-resolved · finding [refuted] · resolves l-security-r1: root-agents-ns-read grants pods/log, configmaps and pod specs in credential-store namespaces; the matrix tests only secrets

Same exposure as p1-r7: the spec's Design states the choice (pods, ConfigMaps and logs in those namespaces, never Secrets) and the operator confirmed it as one design. Agents get strictly less than the built-in view that root-developers already holds cluster-wide. Narrowing pods/log or ConfigMaps in credential-store namespaces is the operator's call and is listed in the PR for that.

<!-- fr:journal kind=finding scope=plan id=l-security-r2-resolved created=2026-11-14T20:47:46+00:00 state=fixed resolves=l-security-r2 -->
### l-security-r2-resolved · finding [fixed] · resolves l-security-r2: ops.yaml cutover-token-review check re-runs the apply and mints a second token

The op's check now reads membership back instead of minting again.

<!-- fr:journal kind=finding scope=plan id=l-tests-r1-resolved created=2026-11-14T20:47:46+00:00 state=fixed resolves=l-tests-r1 -->
### l-tests-r1-resolved · finding [fixed] · resolves l-tests-r1: freshness test restates the generator; no independent namespace pin

Guard pins argocd, monitoring, authentik, infisical, kube-system and longhorn-system and a floor of 30 namespaces, and ties PROTECTED across generator, guard and script.

<!-- fr:journal kind=finding scope=plan id=l-tests-r2-resolved created=2026-11-14T20:47:46+00:00 state=fixed resolves=l-tests-r2 -->
### l-tests-r2-resolved · finding [fixed] · resolves l-tests-r2: hop/ prefix assertion can never fail

The impossible hop/ assertion is replaced with a check that Hop-only namespaces never appear.

<!-- fr:journal kind=finding scope=plan id=l-tests-r3-resolved created=2026-11-14T20:47:46+00:00 state=fixed resolves=l-tests-r3 -->
### l-tests-r3-resolved · finding [fixed] · resolves l-tests-r3: namespaces and move-membership subcommands untested

namespaces and move-membership have behavioural tests (ACTION=move reaches the pod, add precedes remove, read does not mutate).

<!-- fr:journal kind=finding scope=plan id=l-tests-r4-resolved created=2026-11-14T20:47:46+00:00 state=fixed resolves=l-tests-r4 -->
### l-tests-r4-resolved · finding [fixed] · resolves l-tests-r4: verify tested against only one broken cell

verify is tested once per deny cell leaking and per trusted-admin lockout, with a parametrised fake.

<!-- fr:journal kind=finding scope=plan id=l-tests-r5-resolved created=2026-11-14T20:47:46+00:00 state=fixed resolves=l-tests-r5 -->
### l-tests-r5-resolved · finding [fixed] · resolves l-tests-r5: matrix test substring-only; generated-file precheck untested

The matrix test checks cell count, control markers and the generated-file precheck with bad files.

<!-- fr:journal kind=finding scope=plan id=l-tests-r6-resolved created=2026-11-14T20:47:46+00:00 state=fixed resolves=l-tests-r6 -->
### l-tests-r6-resolved · finding [fixed] · resolves l-tests-r6: fake curl discards stdin and args; secret handling unverified

The fake curl records args and stdin; tests prove secrets reach curl on stdin only and username mode sends the form fields.

<!-- fr:journal kind=finding scope=plan id=l-tests-r7-resolved created=2026-11-14T20:47:46+00:00 state=fixed resolves=l-tests-r7 -->
### l-tests-r7-resolved · finding [fixed] · resolves l-tests-r7: guard seen>=2 is loose and the cluster-read binding is not required

The guard requires 31+ root-agents bindings, the cluster-read binding by name and roleRef, and every generated binding's roleRef and subject.

<!-- fr:journal kind=finding scope=plan id=l-tests-r8-resolved created=2026-11-14T20:47:46+00:00 state=open resolves=l-tests-r8 out_of_scope=true -->
### l-tests-r8-resolved · finding [out-of-scope] · resolves l-tests-r8: guard scans only apps/*.yaml; pre-existing scope

Pre-existing scope of any repo-static guard.

<!-- fr:journal kind=finding scope=plan id=p1-r11-resolved-2 created=2026-11-14T21:20:25+00:00 phase=1 state=open resolves=p1-r11 tracked_by=https://github.com/derio-net/frank/issues/987 -->
### p1-r11-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/987] · resolves p1-r11: vendored Tekton controllers read Secrets cluster-wide: a platform fact (phase 1)

Filed at deliver as https://github.com/derio-net/frank/issues/987.
