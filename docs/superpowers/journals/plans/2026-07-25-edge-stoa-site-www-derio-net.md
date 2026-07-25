# Journal: 2026-07-25-edge-stoa-site-www-derio-net

<!-- fr:journal kind=finding scope=plan id=r1-inert-race-guard created=2026-07-25T19:32:38 state=fixed -->
### r1-inert-race-guard · finding [fixed] · site-promotion's ordering guard was inert — merge-base ran in the wrong repo

Found in self-review. The pipeline ran 'git merge-base --is-ancestor $OUR_SHA $CURRENT_SHA' inside the FRANK clone, but both shas are agentic-stoa/site commits. Frank's object database has never seen them, so git errors; stderr was discarded with 2>/dev/null, the non-zero exit read as 'not an ancestor', and the guard could never fire — a newer build could be silently overwritten by an older one. Root cause: the loop shape was lifted from the blog workflow, where OUR_SHA and CURRENT_SHA ARE frank shas, so the in-place form is correct there; the sha provenance changed but the code did not. Fixed by resolving ancestry against a bare, blobless, depth-100 clone of agentic-stoa/site using the already-present read-only stoa-github-mirror token (no new credential), with cat-file -e existence checks and a loud WARNING when either sha falls outside the fetched window rather than a silent pass. Test tightened to assert merge-base runs with --git-dir against the site repo, and the credential assertion sharpened from 'stoa token absent' to a per-URL check that frank is cloned with GITHUB_TOKEN and agentic-stoa with STOA_TOKEN.

<!-- fr:journal kind=finding scope=plan id=r2-probe-masked-by-fallback created=2026-07-25T19:32:38 state=fixed -->
### r2-probe-masked-by-fallback · finding [fixed] · Acceptance row overclaimed: handle_errors 200 hides a backend outage from the probe

Found in self-review. www-outage-is-visible claimed the operator is alerted if www 'stops answering'. But the handle_errors fallback answers 200 when the backend is unreachable, so the blackbox probe stays green for a www-backend outage and only catches an edge/Caddy outage. The fallback is still right (before launch it IS the intended state, and a content assertion would page continuously), so the fix is honesty plus a scheduled close: the acceptance note now states the limit explicitly, the spec records the trade-off next to the fallback rationale, and phase 6 gains step P6.T2.S4 to move the www probe to a content-asserting module once the real page ships — with a scale-to-0 verification.

<!-- fr:journal kind=finding scope=plan id=r3-inline-css-vs-csp created=2026-07-25T19:32:38 state=fixed -->
### r3-inline-css-vs-csp · finding [fixed] · Astro's default inline stylesheet would have been blocked by the CSP

Found while building phase 1. Astro inlines small stylesheets by default (build.inlineStylesheets: 'auto'), and the edge CSP is style-src 'self' with no 'unsafe-inline' — the page would have returned a healthy 200 while rendering completely unstyled, invisible to every server-side check. Fixed by setting inlineStylesheets: 'never' rather than weakening the CSP, and asserting both the presence of an external stylesheet and the absence of any <style> block in scripts/check-build.sh.

<!-- fr:journal kind=finding scope=plan id=r4-runbook-diff-churn created=2026-07-25T19:32:38 state=fixed -->
### r4-runbook-diff-churn · finding [fixed] · Runbook sync re-serialised the whole file: 1297-line diff for 5 additions

The sync-runbook procedure sorts by (layer, id), but the live file is grouped by layer WITHOUT being sorted by id inside each group. A faithful sort plus PyYAML re-serialisation produced 683 insertions / 614 deletions for five new entries — burying the change and making it impossible to review that nothing else moved. Reverted and replaced with a textual insertion at the end of each entry's layer group: 69 insertions, 0 deletions. Verified no pre-existing entry lost its status and none were dropped.

<!-- fr:journal kind=discovery scope=plan id=r5-sh-not-bash created=2026-07-25T19:32:38 -->
### r5-sh-not-bash · discovery · Check scripts had to be POSIX sh — the image build stage has no bash

The Dockerfile runs the build checks inside node:22-alpine, which ships no bash. The scripts started as bash with 'set -euo pipefail'. Converted to /bin/sh with 'set -eu' (no pipes, so pipefail was never load-bearing) and rewrote a fragile 'grep -q X && fail' construct as an explicit if/then — under set -e that pattern is only safe because it is not the final command of the list, which is too subtle to leave in place.

<!-- fr:journal kind=decision scope=plan id=p6-age-key created=2026-07-26T00:08:06 phase=6 -->
### p6-age-key · decision · Operator supplies the age key; both halves of the gitops-push repair land (phase 6)

No age key on the Mac (`~/.config/sops/age/` absent, nothing in shell config), so the durable SOPS copy was blocked. Operator will make the key available. Plan: repair the cluster immediately by copying `github-app-derio-key` from `secure-agent-pod` to `tekton-pipelines` (no SOPS needed for the live half), then commit `secrets/github-app/github-app-derio-key-tekton.yaml` once the key is present, so a rebuild cannot silently reintroduce the break.

<!-- fr:journal kind=decision scope=plan id=p6-merge-order created=2026-07-26T00:08:09 phase=6 -->
### p6-merge-order · decision · Enroll pre-merge, operator merges, loop closes post-merge (phase 6)

P6.T2.S3 needs the `www` app and `site-promotion` pipeline live on main, so it cannot run before the merge. Everything pre-merge-able (T1.S1 repair, Gitea repo + backfill + has_actions, GitHub webhook, first build) runs now and is pushed to PR 704 with evidence. Operator merges. S3 verification and the post-launch S4 probe tightening land in a close-out PR.

<!-- fr:journal kind=decision scope=plan id=p6-ghcr-visibility created=2026-07-26T00:08:12 phase=6 -->
### p6-ghcr-visibility · decision · GHCR visibility flip stays operator-driven; package remains public per spec (phase 6)

Container package visibility has no REST endpoint and the session token lacks packages write, so the flip is a web-UI action. Agent stops after the first build publishes the package, hands the operator the exact URL, then verifies with an unauthenticated `docker manifest inspect`. Public (not private + a Hop pull secret) is unchanged from the spec's trade-off.

<!-- fr:journal kind=finding scope=plan id=p6-ghcr-verify-falsepositive created=2026-07-26T00:20:51 phase=6 state=fixed -->
### p6-ghcr-verify-falsepositive · finding [fixed] · GHCR visibility check could not fail: docker manifest inspect reads a cached ghcr login (phase 6)

The manual-op verified the package was public with `docker manifest inspect ghcr.io/agentic-stoa/site:<sha>  # succeeds with no credentials`. That command consults `~/.docker/config.json`; on the operator Mac (Docker Desktop, `credsStore: desktop`, `ghcr.io` present in auths) it succeeds against a PRIVATE package, so the check cannot fail on the very host it would be run from. Observed live 2026-07-26: inspect passed, while `gh api orgs/agentic-stoa/packages/container/site --jq .visibility` returned `private` and an anonymous token fetch of `/v2/agentic-stoa/site/manifests/latest` returned HTTP 403. This matters because Hop has no imagePullSecrets — it pulls with genuinely no credentials, which is precisely the condition the old check failed to reproduce. FIXED: verify now asserts the API `visibility` field AND performs an anonymous-token manifest GET expecting 200, with the false-positive documented inline.

<!-- fr:journal kind=discovery scope=plan id=p6-enrollment-ordering created=2026-07-26T00:20:52 phase=6 -->
### p6-enrollment-ordering · discovery · Gitea enrollment does not depend on the frank PR; only the ongoing sync does (phase 6)

The manual-op said to wait for the frank merge because 'triggers live'. Inspecting the diff shows the PR only widens the `agentic-stoa-main-sync` CEL filter and adds an `agentic-stoa-site-promotion` trigger — both are ONGOING-sync concerns. Repo creation, the one-shot backfill and `has_actions` are pure Gitea state, and the first build runs on the Gitea mirror via workflow_dispatch, independent of frank entirely. So enrollment was safely front-loaded; the only cost is possible mirror drift until merge, closed by re-running the backfill.

<!-- fr:journal kind=discovery scope=plan id=p6-eventlistener-freeze-clear created=2026-07-26T00:20:53 phase=6 -->
### p6-eventlistener-freeze-clear · discovery · Verified the array-item ignoreDifferences freeze cannot swallow these trigger additions (phase 6)

Both new triggers are edits to existing `.spec.triggers[]` arrays — the exact shape that silently froze EventListener updates from 2026-06-13 to 2026-07-20 while syncs reported Succeeded. Confirmed the tekton-extras EventListener rule is now only `.spec.namespaceSelector | select(. == {})` (no array-item path), and `scripts/tests/test_tekton_ignore_rules_no_arrays.py` passes (2 passed). Latent and unchanged: the Pipeline/Task rules still use array-item expressions, so the NEW site-promotion Pipeline applies cleanly on create but a future edit to its `.spec.tasks` would be frozen — pre-existing and already tracked, not introduced here.

<!-- fr:journal kind=finding scope=plan id=p6-webhook-scope created=2026-07-26T00:20:54 phase=6 state=open -->
### p6-webhook-scope · finding [open] · Webhook creation blocked: session gh token lacks admin:repo_hook (phase 6)

`POST repos/agentic-stoa/site/hooks` returns 404 + 'needs the admin:repo_hook scope'. Token has repo, workflow, read:org, read:packages, admin:public_key, gist. Handed to the operator in `scripts/tmp/phase6-operator-steps.sh`, which refreshes the scope and then creates the hook with config copied verbatim from the in-service second-brain hook, reading the shared secret live from the cluster.

<!-- fr:journal kind=discovery scope=plan id=p6-gitops-push-repaired created=2026-07-26T00:34:58 phase=6 -->
### p6-gitops-push-repaired · discovery · frank-gitops-push repaired; cnc-promotion un-blocked as a side effect (phase 6)

Operator ran the hand-off script. The derio App PEM is now in tekton-pipelines, the ExternalSecret went SecretSyncedError -> SecretSynced/True and the frank-gitops-push Secret was minted — ending a 1477-failure run that started 2026-07-18. Because cnc-promotion is the pre-existing consumer of that Secret, CNC tag promotion into derio-net/frank had been unable to authenticate for that entire window; it is fixed here as a side effect. The durable SOPS copy (secrets/github-app/github-app-derio-key-tekton.yaml, namespace tekton-pipelines) is committed so a namespace rebuild cannot silently reintroduce the break.

<!-- fr:journal kind=discovery scope=plan id=p6-premerge-compat created=2026-07-26T00:43:10 phase=6 -->
### p6-premerge-compat · discovery · Pre-merge compatibility checks: arch, ports and listen address all match (phase 6)

The published image is a SINGLE-arch manifest (no index), so architecture is not negotiable at pull time — verified `amd64/linux` against hop-1's `amd64/linux`. Port path verified end to end rather than assumed: the Dockerfile writes a Caddyfile listening on :8080 and EXPOSEs 8080; the Deployment declares containerPort 8080 named http; the Service maps 8080 -> targetPort http. This was worth checking pre-merge precisely BECAUSE of the handle_errors fallback — a listen-port or arch mismatch would leave the pod never-Ready while the edge kept serving the holding page with a 200, which is the exact blind spot P6.T2.S4 exists to close.

<!-- fr:journal kind=finding scope=plan id=p6-gitea-push-webhook-missing created=2026-07-26T01:09:22 phase=6 state=fixed -->
### p6-gitea-push-webhook-missing · finding [fixed] · The promotion trigger had no delivery path: no Gitea push webhook existed (phase 6)

Phase 3 added an `agentic-stoa-site-promotion` trigger to the gitea-listener, but nothing provisions Gitea→EventListener delivery. The org webhook sends **only `status`** events, and the one per-repo push hook in the org (companies) targets `el-live-mirror-sync`, a different listener — so `push`→`gitea-listener` had ZERO delivery paths in any repo. Everything upstream reported healthy (mirror Succeeded, Actions green, image published, ArgoCD Synced, trigger present and correct, listener logs silent because the request never arrived), so it read as a broken pipeline rather than a missing webhook. FIXED: per-repo push hook (id 5) to el-gitea-listener, scoped to `site` so the other ten repos don't start delivering pushes. Verified by Gitea test-delivery firing the trigger, then a real promotion. New manual-op `cicd-stoa-site-gitea-push-webhook`; gotcha one-liner + full prose in tekton.md.

<!-- fr:journal kind=finding scope=plan id=p6-handle-errors-unhardened created=2026-07-26T01:09:23 phase=6 state=fixed -->
### p6-handle-errors-unhardened · finding [fixed] · handle_errors served the fallback with no security headers at all (phase 6)

Measured live while the backend was unpullable: `www.derio.net` returned 200 with NO HSTS, CSP, Referrer-Policy or Permissions-Policy, and leaked `Server: Caddy` despite the snippet's `-Server` — because Caddy runs `handle_errors` as its own handler chain and the site-level `import security_headers` does not reach it. This is worst-case timing by construction: the fallback only serves during an outage. It also directly weakened the plan's own 'hardened headers on both sites' acceptance row. FIXED by re-importing the snippet inside `handle_errors`, proven at config level rather than by hope: adapting both revisions with Hop's real caddy-cloudflare:2.11.3 image shows `.apps.http.servers.srv0.errors` gaining HSTS/CSP/Server-strip (origin/main: all False; this branch: all True).

<!-- fr:journal kind=finding scope=plan id=p6-caddy-never-reloads created=2026-07-26T01:09:24 phase=6 state=fixed -->
### p6-caddy-never-reloads · finding [fixed] · Caddy served the old config for 62 days of pod uptime while ArgoCD reported Synced (phase 6)

After the merge the caddy app was Synced at the new revision and the pod's own /etc/caddy/Caddyfile contained the new snippet (the mount is a directory, not subPath, so kubelet DOES live-update it) — but Caddy parses config once at boot, runs without --watch, and the Deployment has no content hash, so the 62-day-old pod kept serving the old routes. Both public sites answered with zero security headers while every status surface was green. Recovered with an in-pod `caddy validate` then `caddy reload` (zero-downtime; a rollout restart would be a real edge outage here because the Deployment is Recreate + hostPort). Documented in hop-gotchas.md; durable fix is a kustomize configMapGenerator, same shape as the gitea-inline-config and homepage traps.
