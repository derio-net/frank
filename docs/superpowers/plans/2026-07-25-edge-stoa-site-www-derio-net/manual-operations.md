# Manual operations — www.derio.net rollout

```yaml
# manual-operation
id: cicd-frank-gitops-push-derio-key
layer: cicd
app: tekton
plan: docs/superpowers/plans/2026-07-25-edge-stoa-site-www-derio-net/06.yaml
when: Before the first site-promotion run. PRE-EXISTING BREAK — cnc-promotion is also blocked by it.
why_manual: SOPS-encrypted bootstrap secret; needs the age key, which is deliberately absent from agent pods.
commands:
- '# frank-gitops-push has been SecretSyncedError since 2026-07-18 (1477 failures as of 2026-07-25): "error getting GH pem from secret: github-app-derio-key not found". ESO resolves auth.privateKey.secretRef in the CONSUMING ExternalSecret namespace and IGNORES secretRef.namespace, so the derio App PEM must exist in tekton-pipelines. It currently exists only in secure-agent-pod. The sibling github-app-stoa-key IS in tekton-pipelines, which is why the mirror token syncs and this one does not.'
- 'source .env ; sops -d secrets/github-app/github-app-derio-key.yaml | sed ''s/namespace: secure-agent-pod/namespace: tekton-pipelines/'' | kubectl apply -f -'
- '# Durable copy so a rebuild does not regress: create secrets/github-app/github-app-derio-key-tekton.yaml (same PEM, namespace tekton-pipelines), SOPS-encrypt with the same age key, and commit it.'
- 'kubectl -n tekton-pipelines annotate externalsecret frank-gitops-push force-sync=$(date +%s) --overwrite   # clears the cached SecretSyncedError'
verify:
- kubectl -n tekton-pipelines get externalsecret frank-gitops-push   # STATUS SecretSynced, READY True
- kubectl -n tekton-pipelines get secret frank-gitops-push -o jsonpath='{.metadata.name}'
status: pending

# manual-operation
id: cicd-stoa-site-gitea-mirror
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-07-25-edge-stoa-site-www-derio-net/06.yaml
when: After the frank PR merges (triggers live); before the GitHub webhook is added.
why_manual: Gitea repo creation + history backfill uses stoa-bot credentials; one-time per repo (pattern of cicd-stoa-mirror-remaining-repos).
commands:
- 'curl -s -X POST http://192.168.55.209:3000/api/v1/orgs/agentic-stoa/repos -H ''Authorization: token <stoa-bot token from Infisical>'' -H ''Content-Type: application/json'' -d ''{"name": "site", "private": true, "default_branch": "main"}'''
- git clone --mirror git@github.com:agentic-stoa/site.git /tmp/site.git && cd /tmp/site.git && git push --mirror ssh://git@192.168.55.209:2222/agentic-stoa/site.git   # stoa-bot key
- '# Enable the Actions unit. Instance-level actions.ENABLED does NOT switch it on for a repo created afterwards, and the failure mode is a SILENT no-run: curl -s -X PATCH http://192.168.55.209:3000/api/v1/repos/agentic-stoa/site -H ''Authorization: token <token>'' -H ''Content-Type: application/json'' -d ''{"has_actions": true}'''
verify:
- 'Gitea UI: agentic-stoa/site exists, main matches GitHub main HEAD sha, and an Actions tab is present'
status: pending

# manual-operation
id: cicd-stoa-site-github-webhook
layer: cicd
app: tekton
plan: docs/superpowers/plans/2026-07-25-edge-stoa-site-www-derio-net/06.yaml
when: After the Gitea mirror repo exists.
why_manual: GitHub webhook config is per-repo UI work; no IaC for this in our setup (same as cicd-stoa-github-webhook-hum et al).
commands:
- 'GitHub UI, agentic-stoa/site: Settings -> Webhooks -> Add webhook'
- 'Payload URL: https://webhooks.hop.derio.net/ | Content type: application/json | Secret: STOA_GITHUB_WEBHOOK_SECRET from Infisical | SSL verify: enabled | Events: push, pull_request | Active: yes'
verify:
- Recent Deliveries shows 200 on the ping event
- kubectl -n tekton-pipelines logs -l eventlistener=github-listener --tail=20
status: pending

# manual-operation
id: cicd-stoa-site-ghcr-package-public
layer: cicd
app: www
plan: docs/superpowers/plans/2026-07-25-edge-stoa-site-www-derio-net/06.yaml
when: Immediately after the first Gitea Actions build publishes the image.
why_manual: GHCR package visibility is GitHub UI/API state, not chart values, and the package does not exist until the first push.
commands:
- '# Trigger the first build if it has not run: push any commit to agentic-stoa/site main, or use workflow_dispatch on the Gitea mirror.'
- 'GitHub UI: agentic-stoa -> Packages -> site -> Package settings -> Change visibility -> Public'
- '# WHY PUBLIC: Hop has no External Secrets Operator and no imagePullSecrets anywhere — every pull there is anonymous. A private package would need Hop''s first pull secret, backed by a long-lived manually-rotated token on a cluster that cannot rotate it, which is the silent-credential-expiry failure class this estate keeps hitting. The artifact is a public website, so the package exposes nothing the site does not already serve. Escalation path if pre-launch confidentiality ever matters: flip to private and add a SOPS-managed pull secret on Hop, accepting the rotation burden.'
verify:
- docker manifest inspect ghcr.io/agentic-stoa/site:<sha>   # succeeds with no credentials
status: pending

# manual-operation
id: cicd-stoa-site-first-promotion
layer: edge
app: www
plan: docs/superpowers/plans/2026-07-25-edge-stoa-site-www-derio-net/06.yaml
when: After the package is pullable. This is what makes www.derio.net serve the real page.
why_manual: End-to-end observation of a delivery chain; ArgoCD Synced/Healthy does not prove the workflow ran.
commands:
- 'kubectl -n tekton-pipelines get pipelinerun -l tekton.dev/pipeline=site-promotion --sort-by=.metadata.creationTimestamp | tail -5'
- '# The promotion commits a tag bump to derio-net/frank main; ArgoCD on Hop then rolls the www Deployment.'
- 'source .env_hop ; kubectl -n www-system get pods -w'
verify:
- 'curl -sI https://www.derio.net | head -1   # 200, and the body is the built page, not the handle_errors holding page'
- 'curl -s https://www.derio.net | grep -q "counter.derio.net" && echo analytics-wired'
- 'git -C <frank> log --oneline -1 clusters/hop/apps/www/manifests/deployment.yaml   # a deploy(edge) commit from stoa-fr-automation'
status: pending
```
