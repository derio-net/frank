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

## Registering a vCluster as an ArgoCD cluster target panics the controller cluster-wide (2026-07-19)

Adding a vCluster (e.g. `cnc-staging`, server
`https://cnc-staging.cnc-staging-vcluster.svc:443`) as an ArgoCD **cluster
target** — the out-of-band `cluster-<name>` Secret — makes the
`argocd-application-controller` **panic and exit** while building that cluster's
cache. On the next cold start it rebuilds *all* caches, panics again →
**CrashLoopBackOff cluster-wide**: every Application stops reconciling. It is
latent — it works while a cache builds incrementally; a controller **restart**
triggers the full rebuild and the crash.

Verbatim panic (read from VictoriaLogs;
`kubernetes.pod_name:argocd-application-controller-0`):

```
panic: assignment to entry in nil map
  k8s.io/kubectl/pkg/util/resource.maxResourceList        resource.go:179
  ...PodRequestsAndLimits                                 resource.go:36
  argo-cd/v3/controller/cache.populatePodInfo             controller/cache/info.go:462
  ...gitops-engine clusterCache.sync → listResources → EachListItem
```

**Root cause:** ArgoCD **v3.3.2** (chart `9.4.6`) vendors kubectl **v0.34.0**,
whose `PodRequestsAndLimits` writes to a nil `ResourceList` map when computing the
requests of a Pod carrying **LimitRange-defaulted** resources — and vClusters ship
a default LimitRange, so any pod cached from the vCluster hits it. The panic is
uncaught in a cache-sync goroutine, so the whole controller process dies (not just
that cluster's cache). Upstream
[argo-cd#26529](https://github.com/argoproj/argo-cd/issues/26529) /
[kubernetes#136533](https://github.com/kubernetes/kubernetes/issues/136533);
permanent fix ships in **ArgoCD 3.5** (client-go 1.36.1), **not** backported to 3.4.

**Fix (frank #658):** a **cluster-scoped** `resource.exclusions` in
`apps/argocd/values.yaml` `configs.cm` that skips **Pod on the vCluster URL only**
(`resource.exclusions` matches `apiGroups` + `kinds` + a `clusters` glob list).
ArgoCD then never caches the vCluster's Pods → `populatePodInfo` never runs there.
The main cluster keeps full per-pod visibility.

- The value **replaces** the argo-cd chart default (Helm does not merge a multiline
  string), so the chart-default exclusions must be reproduced verbatim and the Pod
  entry appended. Guard: `scripts/tests/test_argocd_vcluster_pod_exclusion.py`
  (asserts scoped-to-vcluster, **never-global**, main-cluster-safe,
  defaults-preserved).
- **NEVER make the Pod exclusion global** (absent/`*` `clusters`) — that silently
  strips the pod tree + health rollup from every main-cluster app.

```yaml
      - apiGroups:
        - ''
        kinds:
        - Pod
        clusters:
        - https://cnc-staging.cnc-staging-vcluster.svc:443
```

**Safe (re-)registration sequence** (order matters — the exclusion must be loaded
before the controller sees the cluster):

1. Merge the exclusion; let ArgoCD self-apply `argocd-cm` (hard-refresh the
   `argocd` app if impatient). Confirm the live CM has the entry.
2. **Restart the application-controller** so it reloads `resource.exclusions` —
   safe while the vCluster is unregistered (nothing to crash on).
3. Register the vCluster: out-of-band `cluster-<name>` Secret with
   `tlsClientConfig.insecure: true` and `certData`/`keyData` from the vCluster's
   `vc-<name>` secret (`client-certificate`/`client-key`). **No `caData`** — it
   conflicts with `insecure: true` ("specifying a root certificates file with the
   insecure flag is not allowed").
4. Watch the controller: `restartCount` stays 0 and no `panic:` in the logs →
   the exclusion is working; the vCluster apps reconcile.

**Recovery from a live crash** (proven): `kubectl delete secret cluster-<name> -n
argocd` (removes the trigger) + delete the controller pod. It comes back clean.
Do NOT clear a wedged sync-op via `kubectl patch .../operation` — it is
controller-owned; delete the offending virtual resource instead.

**When ArgoCD reaches ≥ 3.5, remove the Pod exclusion** (the client-go 1.36.1 bump
fixes the panic upstream). Full investigation:
`docs/superpowers/debugging/2026-07-19-argocd-vcluster-cache-panic.md`.


## RespectIgnoreDifferences + array-item jqPathExpressions silently freezes the array

Observed 2026-07-20 (the gitea-actions rollout, frank#659): both Tekton
EventListeners were frozen at their **June 13** state for five weeks. Every
sync of `tekton-extras` reported `Succeeded … serverside-applied`, the app
alternated Synced/OutOfSync, and `managedFields` showed argocd-controller's
last real Apply on Jun 13 — the July cnc triggers and the gitea-actions
triggers (#659) never reached the cluster. New resources (Pipelines,
TriggerTemplates) were created fine; only UPDATES to the ignored array froze.

Mechanism: `#613/#614` (Jul 6) added ignoreDifferences jqPathExpressions that
address array items (`.spec.triggers[]?.bindings[]?.kind`, …) to quiet
controller-default drift. With `RespectIgnoreDifferences=true`, removing a
subfield from array items requires ArgoCD to materialize the array from the
LIVE object — so the whole live `spec.triggers` is carried into the applied
manifest, and git-side changes to that array are discarded. The sync is
"successful": it applied the live state back to itself.

Symptom pattern: **git changes to a list inside a kind that has array-item
ignore rules; app syncs Succeeded; live object unchanged; `kubectl get <obj>
-o json --show-managed-fields` shows argocd-controller's Apply timestamp stuck
in the past.** That managedFields timestamp is the decisive probe.

Fix (frank#663): never use array-item jq expressions with
RespectIgnoreDifferences. Delete the rules and instead set the defaulted
per-item fields explicitly in the manifests so no drift appears (bindings get
`kind: TriggerBinding`, cel interceptor refs get `kind: ClusterInterceptor`).
Tripwire: `scripts/tests/test_tekton_ignore_rules_no_arrays.py`.

Known remaining debt: the Pipeline/Task rules in the same Application still
use `.spec.tasks[]?` / `.spec.results[]?` expressions — Pipeline/Task UPDATES
are frozen the same way until they get the explicit-defaults treatment
(exempted in the tripwire; follow-up tracked in the plan's rework notes).
