# ArgoCD application-controller cluster-wide crash on registering the cnc-staging vCluster

- **Date:** 2026-07-19
- **Layer:** secrets / cnc (CNC permanent-deployment rollout, Blocker B)
- **Branch:** `fix/argocd-vcluster-cache-panic`
- **Status:** root cause confirmed; surgical fix landed; runtime re-verification is a back-loaded manual step (operator-gated)

## Symptom & reproduction

Registering the `cnc-staging` vCluster as an ArgoCD **cluster target** (out-of-band
`cluster-cnc-staging` Secret, server `https://cnc-staging.cnc-staging-vcluster.svc:443`)
makes the `argocd-application-controller-0` StatefulSet pod **panic and exit** while
building that cluster's cache. On the next cold start it rebuilds *all* cluster caches,
hits the same panic, and exits again → **CrashLoopBackOff cluster-wide**: all ~60
Applications stop reconciling. Recovery was `kubectl delete secret cluster-cnc-staging -n
argocd` + delete the controller pod; the controller then came up clean (61 Synced).

Reproduction is destructive (cluster-wide outage), so it was NOT re-triggered. The panic
was instead read from the already-captured controller logs in VictoriaLogs
(`192.168.55.225:9428`), which is how the root cause was pinned without re-crashing the
cluster.

## Evidence

Verbatim panic (VictoriaLogs, `kubernetes.pod_name:argocd-application-controller-0`,
crash window ~20:12–20:23Z, two cold-start crashes at 20:12:24 and 20:17:26):

```
ArgoCD Application Controller is starting ... version=v3.3.2
Start syncing cluster server="https://cnc-staging.cnc-staging-vcluster.svc:443"
panic: assignment to entry in nil map
goroutine 329 [running]:
k8s.io/kubectl/pkg/util/resource.maxResourceList(...)        resource.go:179
k8s.io/kubectl/pkg/util/resource.max(...)                    resource.go:157
k8s.io/kubectl/pkg/util/resource.determineContainerReqs(...) resource.go:149
k8s.io/kubectl/pkg/util/resource.podRequests(...)            resource.go:57
k8s.io/kubectl/pkg/util/resource.PodRequestsAndLimits(...)   resource.go:36
github.com/argoproj/argo-cd/v3/controller/cache.populatePodInfo(...)  controller/cache/info.go:462
github.com/argoproj/argo-cd/v3/controller/cache.populateNodeInfo(...)
github.com/argoproj/gitops-engine/pkg/cache.(*clusterCache).newResource(...)
github.com/argoproj/gitops-engine/pkg/cache.(*clusterCache).sync ... listResources ... EachListItem
created by golang.org/x/sync/errgroup.(*Group).Go in goroutine 301
```

Key facts:
- Panic fires 0.3s after `Start syncing cluster server=".../cnc-staging-vcluster..."` —
  it is the **vCluster** cache sync, never the main cluster (which syncs fine repeatedly
  in the same log).
- ArgoCD **v3.3.2** (argo-cd Helm chart `9.4.6`), which vendors **kubectl v0.34.0**.
- The assignment-to-nil-map is in kubectl's pod-resource helper (`maxResourceList`),
  reached from ArgoCD `populatePodInfo` while caching a **Pod**.
- Panic is uncaught in an `errgroup` goroutine → the whole process dies (not just that
  cluster's cache), so it is latent (fine while a cache builds incrementally) and only
  manifests on a full **cold** rebuild — i.e. on every controller restart.
- Upstream: [argo-cd#26529](https://github.com/argoproj/argo-cd/issues/26529) →
  [kubernetes#136533](https://github.com/kubernetes/kubernetes/issues/136533) (fixed in
  [k8s#136534](https://github.com/kubernetes/kubernetes/pull/136534), milestone 1.36).
  Maintainers confirm client-go was bumped to 1.36.1 in argo-cd master, **shipping in
  ArgoCD 3.5** — explicitly **not** backported to 3.4. The named trigger is "a remote
  vCluster that uses **LimitRanges**" — vClusters ship a default LimitRange, so any pod
  cached from the vCluster hits the nil-map path.

## Root cause

**ArgoCD v3.3.2 crashes because kubectl v0.34.0's `resource.PodRequestsAndLimits` writes
to a nil `ResourceList` map when computing the resource requests of a Pod that carries
LimitRange-defaulted resources** (`argo-cd#26529` / `kubernetes#136533`). The
`cnc-staging` vCluster ships a default LimitRange; registering it as an ArgoCD cluster
target makes the controller cache the vCluster's Pods, invoking `populatePodInfo` →
`PodRequestsAndLimits` → panic. Because the panic is unrecovered in a background cache-sync
goroutine, it kills the entire controller process → cluster-wide CrashLoop on cold start.

Stated as X because Y: *the controller crashes cluster-wide because a single vCluster Pod
drives a version-pinned kubectl nil-map panic in an uncaught cache-sync goroutine.* It is a
library-version regression, not a Frank manifest/config error.

## Fix

The permanent fix (ArgoCD 3.5 / client-go 1.36.1) is a major cross-version bump of the
component that already crashed cluster-wide — too heavy and risky to chase now. Instead,
apply the maintainer-endorsed workaround, **scoped so it stays surgical**: a
`resource.exclusions` entry that skips **Pod** on the `cnc-staging` vCluster URL only.
ArgoCD `resource.exclusions` matches on `apiGroups` + `kinds` + a `clusters` glob list, so
the exclusion applies solely to `https://cnc-staging.cnc-staging-vcluster.svc:443`; the
main cluster keeps full per-pod visibility for all other apps.

Change: `apps/argocd/values.yaml` → `configs.cm.resource.exclusions`. Because setting this
value **replaces** the argo-cd chart default (Helm does not merge a multiline string), the
chart's default exclusions (Endpoints/EndpointSlice, Lease, Authz/Authn, CSR, Cilium
identities, Kyverno reports) are reproduced verbatim and the scoped Pod entry appended.

Cost: the CNC staging apps lose the per-pod tree/health in the ArgoCD UI (app health still
rolls up from StatefulSet/Deployment/Rollout/Job status; sync/prune/self-heal of managed
manifests is unaffected; direct `kubectl`/`exec` access is unaffected). Reversible — drop
the Pod entry when ArgoCD ≥ 3.5 is deployed.

Failing test that pins it: `scripts/tests/test_argocd_vcluster_pod_exclusion.py`
(red → green). It renders the argo-cd chart with the repo values and asserts:
1. a Pod exclusion scoped to the vCluster URL exists;
2. **no Pod exclusion is ever global** (empty `clusters`) — the catastrophic silent
   regression this fix must avoid;
3. no Pod-exclusion glob matches the main cluster URL;
4. every chart-default exclusion survives the value override (drift guard for chart bumps).

The failing test proves *schema*. That the panic is **actually gone on re-registration** is
a RUNTIME fact — proven by the manual on-cluster spike below, not by helm template.
Trusting schema over runtime is exactly the #651 trap (Pro-only integration passed
`helm template` and still crashed OSS at runtime).

### Back-loaded manual step (operator-gated, cluster-wide risk)

After merge and ArgoCD self-applies the argocd-cm change:
1. Restart the application-controller so it reloads `resource.exclusions` (safe now — the
   vCluster is currently unregistered, nothing to crash on).
2. Re-register the `cnc-staging` vCluster (out-of-band `cluster-cnc-staging` Secret:
   `tlsClientConfig.insecure: true`, NO caData, server
   `https://cnc-staging.cnc-staging-vcluster.svc:443`; dry-run-proven registration script
   in scratchpad).
3. Verify: controller stays up (no panic in logs), the vCluster cluster goes to a healthy
   cache, and the CNC staging Applications reconcile (cncd/node/fru/postgres come up).
4. On failure: `kubectl delete secret cluster-cnc-staging -n argocd` + delete the
   controller pod (the proven recovery), and STOP.

## Rejected hypotheses

- **gitops-engine `EachListItem` cache bug (the pre-debug paraphrase).** The frame is real
  but incidental — it's the iteration harness. The panic is one frame deeper, in kubectl's
  `maxResourceList`. Rejected once the full (unfiltered) goroutine dump was read.
- **A malformed/nil-Object list from the vCluster's aggregated API.** The panic is not in
  list *decoding*; it is in per-item pod-resource *computation* (`populatePodInfo`).
  Rejected by the stack frames.
- **A one-off bad Pod (e.g. the failed `cncd-migrate` Job pod) — delete it and move on.**
  The trigger is structural (any LimitRange-defaulted Pod on the vCluster), not one pod;
  cleanup would not prevent recurrence. Rejected.
- **Global `resource.exclusions` Pod entry (the naive workaround).** Correct for the panic
  but would strip pod tree/health from all ~60 main-cluster apps. Rejected in favour of the
  `clusters`-scoped form.
- **Bump ArgoCD to 3.5 now (the permanent fix).** Highest blast radius on the component
  that just crashed cluster-wide; 3.5 maturity uncertain; not a "wrap up the rollout"
  move. Deferred — the scoped exclusion carries a "remove when ≥ 3.5" note.
- **Abandon the vCluster; run staging in a host namespace.** Viable and would kill the
  panic class permanently, but it reworks the approach + #653–657 and changes the
  deployment model (T1-owned). Operator chose to keep the vCluster with the surgical
  exclusion.
