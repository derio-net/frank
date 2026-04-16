---
title: "Operating on ArgoCD Drift"
date: 2026-04-16
draft: false
tags: ["operations", "argocd", "gitops", "debugging", "serverside-apply"]
summary: "How 20 of my 52 ArgoCD apps were permanently OutOfSync, why it was seven different bugs, and how fixing the noise unmasked a 21-day crashloop."
weight: 124
---

This is a debugging-focused companion to [Operating on GitOps]({{< relref "/docs/operating/03-gitops" >}}). That post covers the day-to-day ArgoCD commands. This one is about what happens when the `OutOfSync` column stops being useful.

## The Problem

When I last ran `argocd app list`, I got this:

```
NAME                    SYNC STATUS   HEALTH STATUS
argo-rollouts           OutOfSync     Progressing
gitea                   OutOfSync     Progressing
gitea-extras            OutOfSync     Healthy
gpu-operator            OutOfSync     Healthy
grafana-alerting        OutOfSync     Healthy
...
```

Twenty apps. One third of the cluster. All permanently out of sync.

I'd been ignoring it. Everything worked. The dashboards were green. The workloads ran. "Out of sync" had become part of the scenery — the ArgoCD column equivalent of an unread count you stop looking at.

Then I decided to investigate. Not one bug. **Seven.** And one of them was hiding a twenty-one-day crashloop.

## How to Actually Diagnose Drift

The official diagnosis command is `argocd app diff <app>`. In principle it shows you exactly what ArgoCD thinks is different between git and the cluster. In practice, when you have twenty drifting apps, you want a bird's-eye view first.

Start with per-app resource counts:

```bash
kubectl -n argocd get applications -o json \
  | jq -r '.items[] | .metadata.name as $app
           | .status.resources[]?
           | select(.status != "Synced")
           | "\($app)\t\(.kind)/\(.name)\t\(.namespace // "cluster")"' \
  | sort
```

That one pipe gives you the *shape* of the drift: which app has which kind drifting, at which scope. Patterns jump out immediately.

On my cluster the output was dominated by three kinds:

- `ExternalSecret/*` — ten different apps
- `Application/*` — twelve entries, all listed under the `root` app
- `CustomResourceDefinition/*` — twelve entries across argo-rollouts, tekton-pipelines, tekton-dashboard

Those aren't random. Each cluster is its own drift class with its own fix.

## Class A: CRD Schema Defaults

Every `ExternalSecret` in git looked like this:

```yaml
spec:
  target:
    name: paperclip-anthropic
    creationPolicy: Owner
  data:
    - secretKey: ANTHROPIC_API_KEY
      remoteRef:
        key: ANTHROPIC_API_KEY
```

The live object looked like this:

```yaml
spec:
  target:
    name: paperclip-anthropic
    creationPolicy: Owner
    deletionPolicy: Retain             # <-- defaulted by CRD schema
  data:
    - secretKey: ANTHROPIC_API_KEY
      remoteRef:
        key: ANTHROPIC_API_KEY
        conversionStrategy: Default    # <-- defaulted
        decodingStrategy: None         # <-- defaulted
        metadataPolicy: None           # <-- defaulted
```

The External Secrets CRD has `default` values baked into its OpenAPI schema. The API server injects them on `kubectl apply`. Git doesn't have them. Three-way diff flags the gap. Forever.

**Fix:** pin the defaults in git so it matches what the CRD writes.

```yaml
spec:
  target:
    name: paperclip-anthropic
    creationPolicy: Owner
    deletionPolicy: Retain
  data:
    - secretKey: ANTHROPIC_API_KEY
      remoteRef:
        key: ANTHROPIC_API_KEY
        conversionStrategy: Default
        decodingStrategy: None
        metadataPolicy: None
```

Sixteen manifests, four lines each. A mechanical edit — but it's the cheapest way to close the diff. The alternative (`ignoreDifferences`) hides real changes to those same fields if we ever start setting them intentionally, so I prefer pinning.

After pinning: ten apps moved from `OutOfSync` to `Synced` in two minutes.

## Class B: The Default-Value Phantom Diff

The `root` Application listed twelve child Applications as drifting. All of them. And every one of those templates had this block:

```yaml
syncPolicy:
  automated:
    prune: false
    selfHeal: true
```

The *live* Application CR had this:

```yaml
syncPolicy:
  automated:
    selfHeal: true
```

That's it. `prune: false` isn't present.

This is the mirror of Class A. ArgoCD's Application CRD has `prune: false` as its *schema default*. When ArgoCD's own controller writes the CR, it normalises the default away — absent and `false` are semantically identical. Git still has the explicit line. Three-way diff flags the gap on every one of the twelve child templates.

**Fix:** drop the explicit line.

```bash
for f in apps/root/templates/*.yaml; do
  sed -i '/^      prune: false$/d' "$f"
done
```

Fifty-one templates. One commit. The root app went from permanently OutOfSync to Synced.

I also left a comment in `apps/root/values.yaml` explaining why:

```yaml
# Note: Application templates do NOT set automated.prune explicitly — the
# schema default (false) is our project-wide convention (manual pruning only).
# ArgoCD normalizes explicit `prune: false` to absent, which caused permanent
# drift on the root Application until we dropped the line from the templates.
```

There's a sibling of this bug: `group: ""` in `ignoreDifferences` blocks. Same shape — ArgoCD treats empty-string groups as unset, strips them, and the three-way diff fires. Twenty-one more templates edited.

## Class C: Orphan CRDs

All twelve drifting CRDs were from Tekton and Argo Rollouts. Live CRDs had zero ArgoCD tracking-id annotation; git had the manifest checked in but ArgoCD didn't believe it owned the object:

```bash
kubectl get crd rollouts.argoproj.io -o jsonpath='{.metadata.annotations}'
```

Output:

```
{"controller-gen.kubebuilder.io/version":"v0.14.0","helm.sh/resource-policy":"keep"}
```

No `argocd.argoproj.io/tracking-id`. Those CRDs were installed by a pre-ArgoCD bootstrap — the cluster created them before the Application existed. ArgoCD won't silently adopt strangers. So every reconcile it said "these aren't mine, OutOfSync."

**Fix:** explicitly annotate them:

```bash
for crd in analysisruns.argoproj.io analysistemplates.argoproj.io \
           clusteranalysistemplates.argoproj.io experiments.argoproj.io \
           rollouts.argoproj.io; do
  kubectl annotate crd $crd \
    "argocd.argoproj.io/tracking-id=argo-rollouts:apiextensions.k8s.io/CustomResourceDefinition:/$crd" \
    --overwrite
done
```

But adoption alone wasn't enough. Even after annotation, ArgoCD still reported OutOfSync. The chart renders the CRDs *without* the `kubectl.kubernetes.io/last-applied-configuration` annotation that `kubectl apply` writes, and the three-way diff keeps flagging that mismatch. Apply succeeds every sync (`serverside-applied`), then the next comparison re-flags.

For CRDs specifically, I gave up fighting and used `ignoreDifferences`:

```yaml
ignoreDifferences:
  - group: apiextensions.k8s.io
    kind: CustomResourceDefinition
    jsonPointers:
      - /metadata/labels
      - /metadata/annotations
      - /spec/preserveUnknownFields
```

The schema still gets synced. Only the metadata noise is silenced.

## Class D: Zombie Sub-charts

Two Helm charts had the same smell: values set `enabled: false`, but cluster had resources.

```bash
grep -E "redis-cluster|mongodb|ingress" apps/gitea/values.yaml apps/infisical/values.yaml
```

```
apps/gitea/values.yaml:redis-cluster:
apps/gitea/values.yaml:  enabled: false
apps/infisical/values.yaml:ingress:
apps/infisical/values.yaml:  nginx:
```

But the cluster had `Service/gitea-redis-cluster`, `ConfigMap/infisical-ingress-nginx-controller`, a dozen other orphans — ServiceAccounts, Roles, ValidatingWebhookConfigurations, an IngressClass. Subchart resources from when those features *were* enabled, kept alive by `prune: false`.

These aren't reclaimable without confirming nothing uses them. The bitnami nginx orphans even included cluster-scoped resources that could break other apps if I got it wrong.

**Pre-delete verification:**

```bash
# Are any Ingress resources still using the nginx IngressClass?
kubectl get ingress -A -o json \
  | jq -r '.items[] | select(.spec.ingressClassName=="nginx")
                   | "\(.metadata.namespace)/\(.metadata.name)"'
```

Empty output = safe. Every cluster uses Traefik now, not nginx.

**Rollback dump** (for every resource, before deleting):

```bash
mkdir -p /tmp/argocd-drift
kubectl get clusterrole infisical-ingress-nginx -o yaml \
  > /tmp/argocd-drift/rollback-infisical-clusterrole.yaml
# ...repeated for each object
```

Then delete, dependency-safe, one at a time:

```bash
kubectl -n infisical delete rolebinding infisical-ingress-nginx
kubectl -n infisical delete role infisical-ingress-nginx
kubectl delete clusterrolebinding infisical-ingress-nginx
kubectl delete clusterrole infisical-ingress-nginx
kubectl delete validatingwebhookconfiguration infisical-ingress-nginx-admission
kubectl delete ingressclass nginx
kubectl -n infisical delete cm infisical-ingress-nginx-controller mongodb-common-scripts
kubectl -n infisical delete sa infisical-ingress-nginx mongodb redis
```

If anything breaks: `kubectl apply -f /tmp/argocd-drift/rollback-*.yaml`.

Nothing broke. Infisical stayed Synced/Healthy through the whole deletion.

## Class E: Two Apps Fighting for One Namespace

`sympozium-extras` had a `namespace.yaml` adding pod-security labels. `sympozium` (the chart) *also* rendered a namespace. Both apps tried to own the `argocd.argoproj.io/tracking-id` annotation. Every sync, whoever got there second flagged OutOfSync.

The fix I tried first — `managedNamespaceMetadata` on the sympozium Application — didn't work. That feature only applies to namespaces ArgoCD *auto-creates*; it can't override a chart-rendered Namespace object.

The chart doesn't expose `namespace.labels` in values. Forking the chart wasn't worth it for three sticky labels.

**Fix:** apply the labels out-of-band, document as a manual op, delete the duplicate manifest.

```bash
kubectl label ns sympozium-system \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/warn=privileged \
  --overwrite
```

Labels are sticky — once applied, they survive chart re-renders. The plan captures this as a `# manual-operation` YAML block so the runbook registry knows about it.

## Class F: Terminal Hook Noise

`Job/postgres-vk-init-electric` and `PipelineRun/test-build-sign-5qtn4`. Both `Complete`. Both showing up in app status as OutOfSync because `requiresPruning: true` and the project-wide `prune: false` refused to clean them up.

The Job is an ArgoCD PostSync hook (`argocd.argoproj.io/hook: PostSync`). It creates a Postgres role idempotently. The chart recreates it on every sync; `hook-delete-policy: BeforeHookCreation` deletes the previous one *before* the next run, leaving a Completed job in the window between.

If I'd stopped at one delete, this would have been a clean class. But I did — and the Job came back three minutes later, because it's supposed to. That's hook behaviour, not drift.

**Disposition:** one-shot delete is fine; permanent fix would be `hook-delete-policy: BeforeHookCreation,HookSucceeded` on the hook definition. I left that for a follow-up — it's a genuine config improvement, not a drift fix.

## Class G: When the Chart and the Cluster Disagree

Four apps had drift that didn't fit any of the above: `victoria-metrics`, `gpu-operator`, `vcluster-experiments`, `infisical` (its own Deployment), and the `infisical-postgresql` PDB.

Each one needed per-resource investigation. The pattern turned out to be the same: charts and operators inject fields the git source doesn't specify, often timestamps or hashes that *change* between renders.

- **`victoria-metrics-grafana` Deployment:** `checksum/config`, `checksum/sc-dashboard-provider-config`, `checksum/secret` annotations on the pod template. Chart rotates them when ConfigMaps change. Narrow `ignoreDifferences` on those pointers.
- **`gpu-operator` ClusterPolicy:** the NVIDIA operator webhook defaults dozens of sub-fields we intentionally leave unset (driver off, toolkit off, CDI off — Talos handles the driver stack). Fighting field-by-field isn't worth it. `ignoreDifferences` on `/spec` wholesale.
- **`vcluster-experiments` StatefulSet:** a `vClusterConfigHash` annotation plus Kubernetes-defaulted fields (`whenScaled`, `revisionHistoryLimit`, `updateStrategy`) that the chart doesn't render.
- **`infisical` Deployment:** the chart stamps `updatedAt: "2026-04-04 UTC 21:31:24"` on every render. Nothing to do except ignore.
- **`infisical-postgresql` PDB:** standalone single-replica Postgres — PDB provides zero protection, and the chart-rendered PDB (`maxUnavailable: ""`) diverges from what Kubernetes defaults the empty string to. Easiest fix: `pdb.create: false` in values. Delete the PDB entirely.

Each of these got a narrow `ignoreDifferences` in the Application CR, scoped to a specific JSON pointer. The full working object spec stays under GitOps control.

## The Unmasked Bug

The most important thing I learned wasn't about ArgoCD normalisation or SSA three-way diffs.

Four of the twenty drifting apps had health `Progressing`. They'd been Progressing for weeks. I'd stopped looking at the column. In my head, Progressing meant "mid-reconcile, probably fine."

When I resolved `argo-rollouts`'s drift, the controller logs became readable for the first time. The pods looked like this:

```
NAME                             READY   STATUS             RESTARTS           AGE
argo-rollouts-6b4c4dfbd9-ghl9c   0/1     CrashLoopBackOff   1154 (2m18s ago)   21d
```

One thousand one hundred and fifty-four restarts. Twenty-one days.

The pod log:

```
time="2026-04-16T21:10:14Z" level=info msg="Argo Rollouts starting" version=v1.8.4
time="2026-04-16T21:10:14Z" level=info msg="Downloading plugin argoproj-labs/cilium
  from: https://github.com/argoproj-labs/rollouts-plugin-trafficrouter-cilium/releases
  /download/v0.4.1/rollouts-plugin-trafficrouter-cilium-linux-amd64"
time="2026-04-16T21:10:14Z" level=fatal msg="Failed to download plugins: ...
  response code Not Found"
```

I had a `trafficRouterPlugins` entry in `apps/argo-rollouts/values.yaml` pointing at a Cilium traffic router plugin URL. The URL 404s. The plugin was never published — the `argoproj-labs` organisation has no such repo:

```bash
curl -s "https://api.github.com/orgs/argoproj-labs/repos?per_page=100" \
  | jq -r '.[] | select(.name | test("cilium|trafficrouter")) | .name'
```

Returns seven other traffic-router plugins (nginx, gatewayapi, contour, glooplatform, glooedge, openshift, consul). No cilium.

I must have added the config hoping the plugin existed, or copied it from stale documentation. Either way: twenty-one days of a crashlooping controller that every other monitoring signal masked.

**Fix:** delete the plugin config, add a comment, let the controller start up clean:

```yaml
controller:
  replicas: 1
  # Note: the Cilium traffic router plugin referenced in the original extras
  # ConfigMap points to a release URL that 404s — the plugin was never
  # published on GitHub. The controller crash-looped for 21 days because of
  # this. Leaving plugin config unset until a real Cilium traffic router
  # plugin exists. Canary/blueGreen on Deployments still work without it.
```

No live Rollout was using the plugin. Nothing actually depended on it. The whole thing was aspirational config that broke the controller on startup and was invisible because the noise drowned it out.

This is the argument for taking drift seriously. A healthy ArgoCD install isn't one where every app is Synced — it's one where `OutOfSync` actually means something is wrong. When the column is always red, you stop reading it.

## The Final Tally

Starting point: 20 of 52 apps OutOfSync.
End state: 2 of 52 OutOfSync. Both Healthy. Both functionally fine.

The two residuals:

- **`tekton-extras`** — Task/Pipeline/EventListener report OutOfSync. `kubectl apply --dry-run=server -f` shows no delta. Every sync logs `serverside-applied`. Then the next comparison re-flags. An ArgoCD-Tekton SSA quirk I couldn't fully run to ground in this pass.
- **`vcluster-experiments` StatefulSet** — every field I could identify as drifted got an `ignoreDifferences` pointer. It still flags. Something in how the chart normalises the StatefulSet spec that I haven't pinpointed.

I'm keeping both as residuals instead of blanket-ignoring the whole resources, because a narrow-then-wider escalation is the right path if either turns into a real problem. If you can't explain the drift, at least name it so future-you can tell the noise from the signal.

## Takeaways

- **`OutOfSync` is a signal, not decoration.** If most of your apps are always OutOfSync, the column is broken. Fix it, or mute it deliberately — don't normalise "partially red dashboard."
- **Classify before you fix.** Seven drift classes. Each needed a different fix. Blanket-ignoring everything would have worked on the dashboard and hidden the 21-day crashloop.
- **Pin schema defaults in git where possible.** Preferred over `ignoreDifferences` because real changes still flag. Only reach for `ignoreDifferences` when the mutator is a controller/webhook you don't own.
- **Dump before you delete.** `kubectl get -o yaml > rollback.yaml` takes two seconds and saves you from a bad Monday.
- **Read the logs of every app that moved from `Progressing` to a new state.** That's where the hiding things are.

## References

- Plan: [`docs/superpowers/plans/2026-04-15--gitops--argocd-drift-cleanup.md`](https://github.com/derio-net/frank/blob/main/docs/superpowers/plans/2026-04-15--gitops--argocd-drift-cleanup.md)
- Spec: [`docs/superpowers/specs/2026-04-15--gitops--argocd-drift-cleanup-design.md`](https://github.com/derio-net/frank/blob/main/docs/superpowers/specs/2026-04-15--gitops--argocd-drift-cleanup-design.md)
- Related: [Operating on GitOps]({{< relref "/docs/operating/03-gitops" >}}) — day-to-day ArgoCD CLI commands
- [ArgoCD `ignoreDifferences`](https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/)
- [ArgoCD `managedNamespaceMetadata`](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/#namespace-metadata)
- [Kubernetes ServerSideApply field management](https://kubernetes.io/docs/reference/using-api/server-side-apply/)
