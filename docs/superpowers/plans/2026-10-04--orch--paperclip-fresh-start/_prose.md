# Paperclip fresh start — pure upstream v2026.916.1

Spec: `docs/superpowers/specs/2026-10-04--orch--paperclip-fresh-start-design.md`.
Supersedes PR #820, which closes unmerged once this PR is open.

## Shape

- **Phase 1 (agentic):** every repo change in one PR. A guard test pins the
  pure-upstream pod (red, then green). The manifests lose the sidecar, the CLI
  shims, the adapter ConfigMaps and the LiteLLM key, and gain `TRUST_PROXY` and
  the announcements opt-out. The shell's other artefacts go (client setup,
  SOPS key, bump-workflow entry, test exemption). The paused companies hook is
  declared in `webhooks.yaml`. Docs and the runbook stop describing the old
  setup as current.
- **Phase 2 (manual):** the post-merge live sequence. Pause the companies hook
  *before* merging; after merging, wipe the DB and then the data volume, sweep
  the objects `prune: false` leaves behind, bootstrap the first admin, and run
  the R7 proof.

Measured during planning (2026-10-05): node pod CIDRs are all /24s inside
`10.244.0.0/16`. Live objects in `paperclip-system` match the spec's names
(PVCs `data-paperclip-db-postgresql-0`, `paperclip-data`, `paperclip-shell-home`;
Services `paperclip-lb`, `paperclip-shell`). `paperclip-db-postgresql` is a
chart-managed Secret (postgresql-14.1.10).

Expected side effect: `layer-15-workflows-down` may fire during the wipe
window. It must have resolved before the R7 proof.

## Manual operations

```yaml
# manual-operation
id: orch-paperclip-pause-companies-mirror
layer: orch
app: stoa-live-mirror-sync
plan: 2026-10-04--orch--paperclip-fresh-start
when: Before merging the fresh-start PR — the wipe destroys the Paperclip routine the hook fires.
why_manual: Gitea webhooks are forge state, not cluster state; nothing in GitOps owns their `active` flag.
commands: |
  cd "$FRANK_REPO" && source .env
  GU=$(kubectl -n gitea get secret gitea-secrets -o jsonpath='{.data.username}' | base64 -d)
  GP=$(kubectl -n gitea get secret gitea-secrets -o jsonpath='{.data.password}' | base64 -d)
  API=http://192.168.55.209:3000/api/v1/repos/agentic-stoa/companies/hooks
  HID=$(curl -fsS -u "$GU:$GP" "$API" | jq -r '.[] | select(.config.url | contains("el-live-mirror-sync")) | .id')
  test -n "$HID"
  curl -fsS -u "$GU:$GP" -X PATCH "$API/$HID" -H 'Content-Type: application/json' -d '{"active":false}' >/dev/null
verify: |
  curl -fsS -u "$GU:$GP" "$API" | jq '.[] | select(.config.url | contains("el-live-mirror-sync")) | {id, active}'
  # → "active": false. After the next natural merge to the companies repo:
  kubectl -n tekton-pipelines get taskruns --sort-by=.metadata.creationTimestamp | grep live-mirror-sync | tail -3
  # → no TaskRun newer than the pause.
status: pending
```

```yaml
# manual-operation
id: orch-paperclip-fresh-start-wipe
layer: orch
app: paperclip
plan: 2026-10-04--orch--paperclip-fresh-start
when: Right after the fresh-start PR merges and the paperclip Application's sync operation has reached the merge revision (live Deployment shows sha-d554c47, one container). Do not wait on Synced — the app is OutOfSync until the sweep.
why_manual: Deleting persistent data is irreversible and owned by no controller; the operator chose a no-backup wipe.
commands: |
  cd "$FRANK_REPO" && source .env
  NS=paperclip-system
  kubectl -n $NS get deploy paperclip -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
  RV=$(kubectl -n $NS get secret paperclip-db-postgresql -o jsonpath='{.metadata.resourceVersion}')
  DB_OLD=$(kubectl -n $NS get pvc data-paperclip-db-postgresql-0 -o jsonpath='{.metadata.uid}')
  DATA_OLD=$(kubectl -n $NS get pvc paperclip-data -o jsonpath='{.metadata.uid}')
  echo "secret rv=$RV db=$DB_OLD data=$DATA_OLD"
  # 1. Database first.
  kubectl -n $NS delete pvc data-paperclip-db-postgresql-0 --wait=false
  kubectl -n $NS delete pod paperclip-db-postgresql-0
  kubectl -n $NS wait --for=delete pvc/data-paperclip-db-postgresql-0 --timeout=180s || true
  # If the new DB pod is Pending on the deleted claim, delete the pod again — the STS creates claims only with pods.
  kubectl -n $NS wait --for=condition=Ready pod/paperclip-db-postgresql-0 --timeout=600s
  # 2. Then the data volume (ArgoCD selfHeal recreates the PVC).
  kubectl -n $NS delete pvc paperclip-data --wait=false
  kubectl -n $NS delete pod -l app.kubernetes.io/name=paperclip,app.kubernetes.io/component=server
  kubectl -n $NS wait --for=condition=Ready pod -l app.kubernetes.io/name=paperclip,app.kubernetes.io/component=server --timeout=900s
verify: |
  kubectl -n $NS get pvc data-paperclip-db-postgresql-0 paperclip-data -o custom-columns=N:.metadata.name,UID:.metadata.uid,S:.status.phase
  # → both Bound, both UIDs differ from $DB_OLD / $DATA_OLD
  kubectl -n $NS get secret paperclip-db-postgresql -o jsonpath='{.metadata.resourceVersion}'   # → == $RV
  kubectl -n $NS logs deploy/paperclip --tail=50   # migrations applied to an empty DB, server listening
status: pending
```

```yaml
# manual-operation
id: orch-paperclip-retire-shell-sweep
layer: orch
app: paperclip
plan: 2026-10-04--orch--paperclip-fresh-start
when: After orch-paperclip-fresh-start-wipe.
why_manual: The paperclip Application runs prune false; deleting manifests from git leaves the live objects serving forever.
commands: |
  cd "$FRANK_REPO" && source .env
  NS=paperclip-system
  kubectl -n $NS delete svc paperclip-shell --ignore-not-found
  kubectl -n $NS delete pvc paperclip-shell-home --ignore-not-found
  kubectl -n $NS delete secret paperclip-shell-ssh-keys --ignore-not-found
  kubectl -n $NS delete externalsecret paperclip-llm-key paperclip-shell-alerts --ignore-not-found
  kubectl -n $NS delete configmap paperclip-hermes paperclip-opencode paperclip-shell-inventory paperclip-shell-motd-tips --ignore-not-found
verify: |
  kubectl -n $NS get svc,pvc,secret,externalsecret,configmap -o name | grep -E 'paperclip-(shell|hermes|opencode|llm-key)' || echo "none left"
  kubectl get svc -A -o jsonpath='{range .items[*]}{.status.loadBalancer.ingress[*].ip}{"\n"}{end}' | grep -x 192.168.55.221 || echo ".221 free"
  kubectl -n argocd get application paperclip -o custom-columns=SYNC:.status.sync.status,HEALTH:.status.health.status   # → Synced
status: pending
```

```yaml
# manual-operation
id: orch-paperclip-bootstrap-admin
layer: orch
app: paperclip
plan: 2026-10-04--orch--paperclip-fresh-start
when: After the sweep, once layer-15-workflows-down has resolved.
why_manual: The first admin of an authenticated instance is created from a one-time invite printed inside the pod and accepted in a browser.
commands: |
  cd "$FRANK_REPO" && source .env
  kubectl -n paperclip-system exec deploy/paperclip -- pnpm paperclipai auth bootstrap-ceo
  # Open the printed invite at https://paperclip.cluster.derio.net (Authentik in front), create the admin.
  # R7 proof: throwaway company → Connections → connect Claude (subscription sign-in) → hire one
  # Claude-adapter agent → assign a trivial task → observe completion; then
  kubectl -n paperclip-system rollout restart deploy/paperclip
  # → assign a second trivial task; it completes without re-signing in.
verify: |
  kubectl -n paperclip-system logs deploy/paperclip --tail=200 | grep -iE 'req.ip|10\.244\.'   # R4: requests via Traefik log a pod IP
  # R4 negative: from a LAN host (not a pod), hit the LoadBalancer directly with a forged header —
  curl -sS -o /dev/null -w '%{http_code}\n' -H 'X-Forwarded-Host: evil.invalid' -H 'X-Forwarded-For: 203.0.113.9' http://192.168.55.212:3100/
  kubectl -n paperclip-system logs deploy/paperclip --tail=50 | grep -E '203\.0\.113\.9|192\.168\.55\.'
  # → the request logs the LAN client's own 192.168.55.x address, never 203.0.113.9 or a 10.244.x address
  #   (eTP Local preserved the source IP and TRUST_PROXY ignored the forged headers).
  #   .212 must still answer at all — if it times out, Cilium is not announcing it from gpu-1.
  # Admin can sign in; both tasks completed in the UI.
status: pending
```

```yaml
# manual-operation
id: orch-paperclip-resume-companies-mirror
layer: orch
app: stoa-live-mirror-sync
plan: 2026-10-04--orch--paperclip-fresh-start
when: Later — once the reworked company is imported into Paperclip and its sync routine exists.
why_manual: The routine trigger URL is minted by Paperclip at routine creation and lives in Infisical; the hook flag is forge state.
commands: |
  # 1. Infisical: set STOA_LIVE_MIRROR_FIRE_URL to the new routine's public trigger URL.
  cd "$FRANK_REPO" && source .env
  kubectl -n tekton-pipelines annotate externalsecret live-mirror-paperclip force-sync=$(date +%s) --overwrite
  # 2. Re-activate the hook (same lookup as orch-paperclip-pause-companies-mirror), with {"active":true}.
  # 3. Remove the "paused" note from apps/tekton/webhooks.yaml in a follow-up PR.
verify: |
  # The next merge to the companies repo produces a Succeeded live-mirror-sync TaskRun and the routine runs in Paperclip.
  kubectl -n tekton-pipelines get taskruns --sort-by=.metadata.creationTimestamp | grep live-mirror-sync | tail -1
status: deferred
```
