# Frank Gotchas — ArgoCD

Long-form companion to the **ArgoCD** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## Notifications: named-webhook subscription syntax is counter-intuitive

With `service.webhook.<name>` in `argocd-notifications-cm`, notifications-engine registers the service under the **third dotted segment** (`<name>`), not `webhook`. Subscription annotations must reference the name, not the type:

- ✅ `notifications.argoproj.io/subscribe.<trigger>.<name>: ""` (empty value — recipient is implicit in the webhook URL)
- ❌ `notifications.argoproj.io/subscribe.<trigger>.webhook: <name>` — produces `notification service 'webhook' is not supported using the configuration in namespace argocd` because no service is registered under the literal name `webhook`. The trigger still fires (logs show `Trigger TRIGGERED`), but delivery silently fails.

For frank's `service.webhook.telegram` the correct annotation is `subscribe.on-sync-running.telegram: ""`. Successful delivery logs as `Sending notification ... to '{telegram }'` — the trailing space is the empty `Recipient` field in notifications-engine's `Destination{...}.String()` formatter, not a typo or a different bug.

## Out-of-bounds symlinks lock the entire GitOps loop

ArgoCD's repo-server refuses to generate manifests for any source in a repo that contains a symlink resolving above the repo root, with `repository contains out-of-bounds symlinks. file: <path>`. Self-heal can't fire because comparison itself fails, so the cluster silently runs on the last-known-good cache indefinitely; nothing on the homepage tile or the standard `kubectl get applications` summary calls attention to it unless you look at `.status.conditions[].type=ComparisonError`.

Bit us on 2026-05-13 when commit 024ab58 created `.claude/skills → ../../agents/skills` (two `..`s from `.claude/` escapes the repo root); fix was a single `..` (`../agents/skills`). Repo-wide blast radius — every Application in the repo went `Unknown` for ~14 hours before anyone noticed.

Sanity check after any commit that adds/changes a symlink:

```bash
find . -type l -lname '*../../..*' -not -path './.git/*'
kubectl -n argocd get applications -o json \
  | jq '.items[] | select(.status.conditions[]? | .type=="ComparisonError") | .metadata.name'
```

## Manually-triggered syncs do NOT inherit `spec.syncPolicy.syncOptions`

Patching `kubectl patch application -n argocd <name> --type=merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'` runs the sync client-side. `kubectl apply` injects `kubectl.kubernetes.io/last-applied-configuration` into every resource, and any chart-bundled CM larger than ~250KB (e.g. Grafana dashboard CMs like `victoria-metrics-victoria-metrics-k8s-stack-node-exporter-full`, 241KB of JSON in `data`) fails with `metadata.annotations: Too long: may not be more than 262144 bytes`.

The controller's polling-loop auto-sync honors spec syncOptions correctly; only manually-triggered operations are affected. Always pass syncOptions explicitly:

```bash
kubectl patch application -n argocd <name> --type=merge -p \
  '{"operation":{"sync":{"revision":"HEAD","syncOptions":["ServerSideApply=true","RespectIgnoreDifferences=true"]}}}'
```

## Notifications: native `service.telegram` mis-routes positive chat IDs

The notifications-engine native Telegram service routes negative recipients to `NewMessage` (group/private chats) but positive recipients to `NewMessageToChannel("@"+id)` (channel/username lookup), which the Bot API rejects with `Bad Request: chat not found` for numeric user IDs.

Use `service.webhook.telegram` instead (HTTP POST to `https://api.telegram.org/bot$token/sendMessage` with `chat_id` in the body); subscribe via `notifications.argoproj.io/subscribe.<trigger>.webhook=telegram`.

## ArgoCD chart owns `argocd-notifications-cm`

Having a second ArgoCD app try to manage that ConfigMap causes ownership/tracking-id conflicts. Put service/triggers/templates under `notifications.notifiers/.triggers/.templates` in `apps/argocd/values.yaml` so the chart merges them into the existing CM. Set `notifications.secret.create: false` so the chart's empty placeholder Secret doesn't race ESO for ownership of `argocd-notifications-secret`.

## Root App-of-Apps re-templates leaf Application specs on every sync

Any live mutation to a leaf (selfHeal off, `targetRevision` pointed at a feature branch, etc.) is reverted within the root's sync window. The root app's chart re-renders the leaf `Application` CRs from `apps/<name>/values.yaml` + `apps/root/templates/<app>.yaml` and SSAs the result, so spec-level patches on leaves get fought back to ground truth.

Practical bites:
- (a) you can't temporarily flip a leaf to a feature branch to live-test a CM/Secret change end-to-end — the revert lands before you finish observing
- (b) you can't durably suspend selfHeal on a leaf via `kubectl patch application` for a multi-step manual flow

Workarounds:
- live-patch the live `ConfigMap`/`Secret` directly (selfHeal-suspend window is enough for one-off observability)
- accept that cumulative state changes need push→merge→sync
- if you need a longer window — patch `apps/root/templates/<app>.yaml` itself on the feature branch so root re-templates with the values you want

Same constraint applies to every leaf under `apps/root/`.

## The UI LoadBalancer is plain HTTP (443→8080 plaintext)

The `argocd-server` LB Service at 192.168.55.200 maps port 443 to the server's plaintext 8080 — ArgoCD runs in `--insecure` mode behind the LB, so there is no TLS listener at all. `https://192.168.55.200` fails with a connection reset that looks like a network problem; the fix is just `http://192.168.55.200`.

Bites automation hardest: blog screenshot placeholders and runbooks that reflexively write `https://` URLs get a reset, and `curl -k` doesn't help (it's not a cert problem — there's no TLS handshake to complete). Also note for captures: the UI ignores `prefers-color-scheme` (own theme system), so dark-mode emulation has no effect.

## Stale appTree health after a source-path change (2026-06-05)

Converting ai-alert-helper from a plain-directory `path:` to a kustomize root
left the Application stuck `Degraded` with a `lastTransitionTime` from the
previous day, while every resource showed Synced and the Deployment was
Available. `status.resourceHealthSource: appTree` means app-level health comes
from the controller's live-state (Redis) tree, and that tree held a stale
node. `argocd.argoproj.io/refresh=hard` did NOT clear it — the cache needs an
application-controller restart or its natural resync. Cosmetic (the badge
lies), but it masks real health changes until cleared.

Related: switching a live Deployment to `strategy: Recreate` via git fails
the sync with `spec.strategy.rollingUpdate: Forbidden` — the live object keeps
an orphan `rollingUpdate` block from its RollingUpdate past. One-time fix:

```bash
kubectl -n <ns> patch deployment <name> --type=merge \
  -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
```

then re-sync (the ArgoCD operation retries 5× and then needs a manual
re-trigger). Same root cause as the Helm-values variant documented in
storage-secrets-ssa.md.
