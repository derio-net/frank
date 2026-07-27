# Frank Gotchas — Storage / Secrets / SSA

Long-form companion to the **Storage / Secrets / SSA** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## `envFrom.secretRef` without `optional: true` blocks rolling updates

If the Secret is missing, the new pod hits `CreateContainerConfigError` and Kubernetes keeps the old pod alive indefinitely. Mark adapter/feature secrets as `optional: true` when the app can run without them.

## RWO PVC + RollingUpdate strategy deadlocks

The new pod can't mount the volume while the old pod holds it, so the new pod never becomes Ready, so the old pod is never deleted. Use `strategy: type: Recreate` for any single-replica deployment backed by a RWO PVC.

## Switching strategy from RollingUpdate → Recreate via Helm fails ArgoCD sync

Switching a Deployment's `strategy.type` from `RollingUpdate` to `Recreate` via Helm chart values fails ArgoCD sync with `spec.strategy.rollingUpdate: Forbidden: may not be specified when strategy type is 'Recreate'`. SSA does not strip the existing `rollingUpdate: { maxSurge, maxUnavailable }` block from the live resource, and the API rejects the resulting hybrid as invalid.

One-time unblocker:

```bash
kubectl patch deploy <name> -n <ns> --type=merge \
  -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
```

After that, ArgoCD reconciles cleanly. Affects any chart whose default strategy is RollingUpdate when the values override flips to Recreate.

Same root cause for the more general SSA case: Helm charts with `strategy` values that include `rollingUpdate` defaults cannot be overridden to `Recreate` via ServerSideApply in a single sync — SSA validates before merging, so the existing `rollingUpdate` field causes rejection. Workaround: patch the live Deployment strategy first, then let ArgoCD sync.

## ESO ExternalSecret validation webhook rejects empty `data: []`

If all keys are removed, delete the ExternalSecret entirely rather than leaving an empty data array.

## ESO `GithubAccessToken` generator resolves `secretRef` in the consuming namespace (2026-06-08)

ESO's `GithubAccessToken` generator (used to mint short-lived GitHub App
installation tokens — e.g. for the secure-agent-pod and the tekton CI mirror)
resolves its `auth.privateKey.secretRef` **in the namespace of the consuming
ExternalSecret**, and **ignores the `secretRef.namespace` field** — even when the
generator is a cluster-scoped `ClusterGenerator`. Put the private-key Secret in
the *consumer's* namespace, not a central one:

- Symptom: the ExternalSecret is `SecretSyncedError` with
  `error using generator: ... error getting GH pem from secret: secrets "<name>" not found`,
  while the key plainly exists — just in the wrong namespace.
- Fix: SOPS the key into the consuming ns (e.g. `secure-agent-pod`,
  `tekton-pipelines`) and drop the misleading `secretRef.namespace`.
- Note: the agent pod's ServiceAccount is cluster-admin anyway, so the key's
  namespace is moot for that threat model — the real protection is that the key
  is **never mounted into a container** (only the rotating token is).

**Cached generatorState.** After moving/fixing the key, the ExternalSecret stays
`SecretSyncedError` because ESO caches the prior generator failure in a
`generatorstates.generators.external-secrets.io` object. Force a re-run:

```bash
kubectl -n <ns> annotate externalsecret <name> force-sync="$(date +%s)" --overwrite
```

(Separately, an App-token installation is **per-repo + per-org** — a minted token
404s on repos not added to the App install; see `agent-shells.md` for the git/gh
credential-delivery side.)

## SOPS + ArgoCD ServerSideApply don't mix

Encrypted secrets must live outside ArgoCD-managed paths (see `secrets/` dir) and be applied out-of-band.

## AWX operator-managed Postgres CrashLoops on Longhorn — volume permissions

**Symptom (2026-05-31, auto layer):** after deploying the `auto` layer (AWX),
the operator-managed `awx-postgres-15-0` pod sat in CrashLoopBackOff (696
restarts over ~2.5 days). Single log line:

```
mkdir: cannot create directory '/var/lib/pgsql/data/userdata': Permission denied
```

`awx-web` CrashLooped in turn (no reachable DB) and `awx-task` was stuck at
`Init:0/2` (waiting on DB migrations) — all three symptoms trace to the one DB
fault.

**Root cause:** the `quay.io/sclorg/postgresql-15-c9s` image has a baked-in
`USER 26`, but a freshly provisioned Longhorn PVC mounts root-owned (`root:root`,
mode 755). The AWX operator emits an **empty** pod `securityContext` (no
`fsGroup`, no init container) unless the CR tells it otherwise — so UID 26 cannot
create its `PGDATA` subdir (`/var/lib/pgsql/data/userdata`). Confirm with:

```bash
kubectl -n awx get statefulset awx-postgres-15 -o jsonpath='{.spec.template.spec.securityContext}'   # → {}
```

**Fix (declarative, in the AWX CR `apps/awx/manifests/awx.yaml`):**

```yaml
spec:
  postgres_data_volume_init: true
```

This makes the operator inject a root init container that `chown`s the data
volume to UID 26 before postgres starts. Chosen over
`postgres_security_context_settings: {fsGroup: 26}` because it is
storage-agnostic — it works regardless of whether the CSI driver honours
`fsGroup` (Longhorn does, but the init-container route is the AWX-operator's
purpose-built answer to this exact error and survives a storage-class swap).
After the CR change syncs, the operator regenerates the StatefulSet with the
init container and the postgres pod (and then web/task) reconcile to Running.

## Longhorn instance-manager memory-thrash wedges low-RAM nodes (raspi-1, 2026-06-04)

**Root cause (corrected 2026-06-04 evening, after cluster-wide forensics):**
the Longhorn **v1.11.0** instance-manager leaks **anonymous Go heap** — an
upstream regression where the new Proxy service APIs leak proxy connections
([longhorn#12575](https://github.com/longhorn/longhorn/issues/12575), also
reported as #12573/#12643/#12668; **fixed in v1.11.1+**). The leak is linear
and unbounded (~0.9 GiB/day on busy nodes, proportional to engine activity ×
pod age, NOT replica count): node-exporter showed `AnonPages` dominating
(mini-1: 55.6 GiB anon vs 2.7 GiB cached), and IM working sets tracked pod age
(74d-old IMs: gpu-1 72.5 GiB, mini-1 48.3 GiB; 4–10d-old IMs: 0.2–11.5 GiB).
Beware metric duplication: `sum by(pod)` over cadvisor series double-counts IM
memory (two series under the kubelet job) — use `max`.

When the leak exhausts a node, the kernel reclaim-thrashes the little file
cache that remains rather than OOM-killing the giant anonymous process, and
**no OOM kill ever fires**. Failure signature:

- Node `NotReady` (`NodeStatusUnknown`), but pings OK and Talos API responsive
- `talosctl service kubelet` → `HEALTH Fail`, `healthz context deadline exceeded`
- `talosctl memory` → AVAILABLE near zero; `talosctl stats` returns only
  system-namespace containers (CRI too wedged to answer)
- dmesg: iSCSI `ping timeout` / `critical medium error` on the Longhorn-attached
  `sd*` device — these are *downstream symptoms*, not a failing disk
- One wedged node fires every layer with a DaemonSet pod on it simultaneously
  (2026-06-04: L3 cilium, L4 longhorn, L5 NFD worker, L8 fluent-bit/node-exporter,
  L24 traefik — five layers, one root cause)

**Recovery:** `talosctl reboot` wedges in `cleanup/stopAllPods` (the teardown
needs the dead CRI; D-state I/O ignores SIGKILL). Give it ~5 min, then
physically power-cycle — safe on Talos (immutable OS partitions, journaled
EPHEMERAL), but confirm Longhorn volumes are healthy elsewhere first:
`kubectl -n longhorn-system get volumes.longhorn.io | grep -v healthy`.

**Durable fix (EXECUTED 2026-06-04/05, #467):** bump the Longhorn chart
`1.11.0 → 1.11.2` (`apps/root/templates/longhorn.yaml` targetRevision), then
per-volume engine live upgrade (`volumes.longhorn.io spec.image` patch) —
27/27 live-upgraded with zero I/O interruption.

**Old-IM retirement — what actually works (hard-won, three failed attempts):**
the live upgrade moves *replicas* to the new IM but **engines stay in the old
IM pod**, and — the key trap — **new engines started on a node JOIN the
still-existing old IM** on reattach. So plain `rollout restart` retires
nothing. The working per-node recipe:

1. Suspend **root** app selfHeal FIRST (root re-templates leaf Application
   specs and silently reverts leaf-level patches within its sync window),
   then patch each involved leaf app `"syncPolicy":{"automated":null}`
   (`selfHeal:false` alone did NOT keep scale-to-0 down), and scale operator
   owners to 0 (awx-operator, victoria-metrics-operator — their Deployments
   are themselves Argo-healed, so the app suspension must come first).
2. Scale ALL workloads whose engines live in the node's old IM to 0
   simultaneously; confirm replicas stay 0 for 30 s (resurrection check).
3. Wait for **natural** volume detach — it takes seconds once nothing
   recreates pods. **NEVER force-delete `VolumeAttachment` objects**: that
   yanks the block device from under a mounted ext4 (`JBD2: I/O error when
   updating journal superblock`, `EXT4-fs: shut down requested`) — it
   crash-looped ruflo with `EIO` until a clean reattach fsck'd the volume.
4. The old IM CR culls itself at 0 instances (delete its empty pod if it
   lingers); scale everything back; restore root selfHeal + one root sync —
   that single sync re-templates all suspended leaves back to git truth.

Also: `talosctl memory` rows begin with NODE — AVAILABLE is field `$8`,
`$7` is CACHE (this off-by-one faked two "memory not freed" scares).

**Defense-in-depth:** replica scheduling is disabled on raspi-1/raspi-2
(`spec.allowScheduling=false` on `nodes.longhorn.io` — manual op
`stor-longhorn-disable-pi-replica-scheduling`; re-apply when re-adding a Pi).
Volume *attachment* (e.g. Traefik's ACME PVC engine on the edge zone) remains
allowed. The `layer-1-node-memory-headroom` Grafana alert (`MemAvailable <
1 GiB` for 30m) is the early warning — an **absolute** floor, not a ratio:
6% of 64 GB (mini) is healthy, 9% of 4 GB (Pi) is pre-wedge.

Full timeline + forensics: `docs/investigations/2026-06-04--stor--raspi-1-memory-wedge-incident.md`.

## Graceful-node-shutdown pod tombstones look like a live CSI failure (2026-07-16)

Two Longhorn CSI pods — `csi-attacher-5557d89ccf-tq7ln` and
`csi-provisioner-857485dbfb-26tj7` — sat `0/1 Error`, IP `<none>`, age **41d**,
long after a gpu-1 hardware event, which made them look like a lingering casualty
of that outage. They are neither a CSI bug nor outage fallout: they are
**graceful-node-shutdown tombstones**.

Diagnosis (the fields that settle it):

```bash
kubectl -n longhorn-system get pod <name> -o jsonpath='{.status.phase}{" / "}{.status.reason}{" / "}{.status.message}{"\n"}'
# Failed / Terminated / Pod was terminated in response to imminent node shutdown.
kubectl -n longhorn-system get pod <name> -o jsonpath='{.status.containerStatuses[0].state.terminated.finishedAt}{"\n"}'
# 2026-07-11T17:35:50Z   <- the node's actual reboot time
```

What happened: **mini-1 rebooted 2026-07-11**. The kubelet's graceful-node-shutdown
manager SIGTERM'd the pods and left them in a terminal `Failed` phase with that
canonical message. The owning ReplicaSet immediately created healthy replacements
(the `5d1h`-old Running pods sharing the *same* ReplicaSet hash — Deployments read
`3/3`), but Kubernetes **does not garbage-collect the Failed pod objects**: PodGC's
`--terminated-pod-gc-threshold` defaults to `12500`, so a handful of tombstones
never trip it.

Two traps that make this look older/scarier than it is:

- **AGE is the Deployment's creation time, not the failure time.** Both tombstones
  showed `41d` (when the `csi-attacher`/`csi-provisioner` Deployments were created),
  so the age is *not* evidence they predate a recent reboot. The `finishedAt` /
  `startTime` fields are the real timeline.
- **Same-ReplicaSet, not a stale rollout.** The Error pod shares its ReplicaSet
  hash (`5557d89ccf`) with the Running ones — so it's a Failed member of the
  *current* ReplicaSet with a replacement beside it, not a leftover from an old
  revision.

**Cleanup** (harmless — the Deployment is already `3/3`):

```bash
kubectl -n longhorn-system delete pod csi-attacher-5557d89ccf-tq7ln csi-provisioner-857485dbfb-26tj7
# Generic sweep for the class (all namespaces):
kubectl get pods -A --field-selector=status.phase=Failed
```

This is **generic to any Deployment**, not Longhorn-specific — CSI just happens to
run several replicas on the rebooted node. Optional durable hardening (deferred,
not applied): lower PodGC's `terminated-pod-gc-threshold` via
`cluster.controllerManager.extraArgs` in Talos machine config so shutdown
tombstones auto-reap — a cluster-wide controller-manager change, so it deserves
its own decision rather than being bundled with a cosmetic cleanup.

## Standing rules

- Always `ServerSideApply=true` in ArgoCD sync options (avoids annotation size limits).
- Always `prune: false` in syncPolicy — manual pruning only to avoid accidental deletion.
- Always `ignoreDifferences` on Secret data (`/data` jsonPointer) so ArgoCD doesn't fight live mutations.
- SOPS/age encryption for secrets — never commit plaintext.
- Longhorn default replicaCount: 3 (matches 3 control-plane nodes).

## Config-in-Secret charts: values change syncs the Secret but the pod keeps serving OLD config

Some charts render their app configuration into a **Secret** consumed by an
init container at pod boot — gitea's `gitea-inline-config` (assembled into
`/data/gitea/conf/app.ini` by `init-app-ini`) is the canonical case here.

Observed 2026-07-20 while enabling Gitea Actions (`gitea.config.actions.ENABLED:
true`, frank#659): after merge + root sync, the live `gitea-inline-config`
Secret HAD the new `actions: ENABLED=true` key — but the pod was still the
Jul 15 one, live `app.ini` said `ENABLED = false`, and the Deployment's
`checksum/config` pod-template annotation was stale (pre-change value) while
ArgoCD showed the app **Synced/Healthy**. The chart's checksum-annotation
mechanism (which is what normally rolls the pod on config change) did not
propagate under our SSA + `RespectIgnoreDifferences` sync options.

Symptom pattern to recognize: **config-only values change, app Synced/Healthy,
Secret updated, behavior unchanged.** The app serves the old config until the
pod is recreated for any reason — which can be days later, making the config
change appear to "apply itself" mysteriously after an unrelated restart.

Fix (each time, after any config-only values change to such a chart):

```bash
kubectl -n gitea rollout restart deploy/gitea    # Recreate strategy: ~30s blip
kubectl -n gitea rollout status deploy/gitea
# verify INSIDE the pod, not via the Secret:
kubectl -n gitea exec deploy/gitea -- grep -A1 '\[actions\]' /data/gitea/conf/app.ini
```

The PodSecurity "restricted" warnings on restart are warn-level only
(pre-existing for this chart's init containers).

## ESO GithubAccessToken: the PEM must live in the CONSUMER's namespace

**Found 2026-07-25.** `frank-gitops-push` (ns `tekton-pipelines`) had been in
`SecretSyncedError` since 2026-07-18 — 1477 consecutive failures:

```
error processing spec.dataFrom[0].sourceRef.generatorRef, err: error using
generator: error getting GH pem from secret: secrets
"github-app-derio-key" not found
```

The `github-app-derio` ClusterGenerator names `github-app-derio-key`, and ESO
resolves `auth.privateKey.secretRef` **in the namespace of the consuming
ExternalSecret**, ignoring any `secretRef.namespace`. That PEM existed only in
`secure-agent-pod`, which has its own ExternalSecret for the same App.

### Why it stayed invisible

- ArgoCD is green — an ExternalSecret that never materialises is not an
  out-of-sync resource.
- The **sibling generator works**. `github-app-stoa-key` *is* in
  `tekton-pipelines`, so `stoa-github-mirror` syncs perfectly. "The other App
  token is fine" reads as evidence that the mechanism is healthy. It isn't.
- The only consumer at the time was `cnc-promotion`, which runs on merge to a
  cnc repo. Nothing exercised it daily, so **CNC staging/prod tag promotion
  into `derio-net/frank` was silently unable to authenticate** for a week.

### Recovery

```bash
# The PEM must exist in EVERY namespace that consumes the generator.
source .env
sops -d secrets/github-app/github-app-derio-key.yaml \
  | sed 's/namespace: secure-agent-pod/namespace: tekton-pipelines/' \
  | kubectl apply -f -

# ESO caches the failure; force a resync rather than waiting out refreshInterval.
kubectl -n tekton-pipelines annotate externalsecret frank-gitops-push \
  force-sync=$(date +%s) --overwrite

kubectl -n tekton-pipelines get externalsecret frank-gitops-push   # SecretSynced / True
```

Commit a durable SOPS copy targeting `tekton-pipelines` so a rebuild does not
regress it. Manual op: `cicd-frank-gitops-push-derio-key`.

### Generalisation

Before adding a consumer of an existing `GithubAccessToken` ClusterGenerator in
a **new namespace**, check the PEM is there:

```bash
kubectl get secret <generator-key-name> -A
```

An empty result in the target namespace means the ExternalSecret will fail
closed and quietly.

## A PR-branch ExternalSecret is absent, not slow (2026-07-27)

**Symptom.** You wire up a new ExternalSecret, apply its private key, then wait
for it to sync. It never does. `kubectl get externalsecret <name> -o
jsonpath='{.status.conditions[0].reason}'` returns nothing — not `SecretSyncedError`,
not `SecretSynced`, just empty — indefinitely. It reads as a slow or wedged
reconcile.

**Cause.** ArgoCD syncs `apps/**` from **`main`**. An ExternalSecret and its
ClusterGenerator that live only on a feature branch are **not on the cluster at
all**. There is nothing for ESO to reconcile, so there is no status to poll.

```console
$ kubectl -n tekton-pipelines get externalsecret derio-homelab-github-mirror
Error from server (NotFound): externalsecrets.external-secrets.io
  "derio-homelab-github-mirror" not found
```

The trap is that a verification script written as `kubectl annotate … || true`
followed by a status poll **swallows the `NotFound`** and then waits on a status
that can never appear. This is the same failure *shape* as the `frank-gitops-push`
incident: nothing is red, the object is simply absent, and absence has no status
field to look wrong.

**Verifying a new GitHub App credential before merge.** Split it in two.

*Without the cluster* — proves App id, installation id, private key and granted
permissions, which is everything that can actually be wrong at that point:

```bash
uv run --with 'pyjwt[crypto]' --with requests python3 - <<'EOF'
import time, jwt, requests
key = open("app.pem","rb").read()
now = int(time.time())
# iat backdated 60s: GitHub rejects a JWT whose iat is even slightly ahead of
# its own clock.
a = jwt.encode({"iat": now-60, "exp": now+540, "iss": "<APP_ID>"}, key, algorithm="RS256")
r = requests.post("https://api.github.com/app/installations/<INSTALL_ID>/access_tokens",
                  headers={"Authorization": f"Bearer {a}"})
print(r.status_code, r.json().get("token","")[:12])
EOF
```

*With the cluster* — `kubectl apply -f` the ClusterGenerator and ExternalSecret
out-of-band. They are headed for `main` anyway and ArgoCD adopts them on merge
via ServerSideApply.

**Always probe a PRIVATE repo.** A public repo reads with no token at all, so a
green probe against one proves nothing about the credential. Check the
installation's reach too — `GET /installation/repositories` should return
exactly the repos you scoped it to:

```console
$ curl -s -H "Authorization: Bearer $TOKEN" \
    https://api.github.com/installation/repositories | jq '.total_count'
1
```

**Related:** narrowing an installation's repository selection invalidates cached
tokens. After tightening scope, force a fresh mint
(`kubectl annotate externalsecret … force-sync=$(date +%s) --overwrite`) and
re-probe — otherwise you are testing a token issued under the old, wider scope.

## Longhorn's provisioning ceiling silently refuses PVC expansion (2026-07-27)

Expanding a bound Longhorn PVC is a one-line manifest change and a green
ArgoCD tile. It is also a change with **no failure surface**: if Longhorn
declines the expansion, nothing anywhere says so.

The chain is: you bump `spec.resources.requests.storage` in git → the API
server accepts it (the StorageClass sets `allowVolumeExpansion: true`) →
external-resizer calls `ControllerExpandVolume` → Longhorn evaluates each
replica's disk and refuses → `status.capacity.storage` stays at the old
value. ArgoCD compares spec to git, finds them identical, and reports
**Synced/Healthy**. The PVC is still `Bound`, the pod still `Running`, the
filesystem is still the old size. The only honest signal is:

```console
$ kubectl -n <ns> get pvc <name> -o jsonpath='{.status.capacity.storage}'
```

and, definitively, `df -h` inside the pod. **A Synced Application is not
evidence that a volume grew.**

### Why it refuses: declared size, not written bytes

Longhorn's scheduler gate (`IsSchedulableToDisk`) has two independent clauses:

1. `StorageAvailable - size > StorageMaximum * minimalAvailablePercentage/100`
   — the **physical** guard. Stops you actually filling a disk.
2. `size + StorageScheduled <= (StorageMaximum - StorageReserved) * overProvisioningPercentage/100`
   — the **accounting** guard. Counts every replica's *declared* size,
   whether or not those bytes were ever written.

Clause 2 is the one that bites, and it is entirely decoupled from real usage.
A node hosting large, sparsely-written volumes is "full" to Longhorn while
`df` on the underlying disk shows it half empty.

Measured on Frank 2026-07-27, with `storageOverProvisioningPercentage` left at
the chart default of 100 and a 30% reserve:

```
node       max   reserved  scheduled    ceiling   headroom   schedulable
mini-1    929Gi    279Gi      645Gi       650Gi        5Gi      True
mini-2    929Gi    279Gi      639Gi       650Gi       11Gi      True
mini-3    929Gi    279Gi      654Gi       650Gi       -4Gi      False   <- over
gpu-1    3724Gi      0Gi      725Gi      3724Gi     2999Gi      True
```

mini-3 was already past its ceiling and reporting it plainly, in a condition
nobody reads:

```
reason=DiskPressure
  Scheduling space condition failed: ScheduledTotal = 702361370624
  (Size + StorageScheduled) is greater than ProvisionedLimit = 698184790016
  (100% of StorageMax - StorageReserved)
```

Growing `hermes-agent-shell-home` by 20Gi needed 20Gi of headroom on *each* of
its three replicas' disks — gpu-1 (fine), mini-1 (5Gi), mini-3 (−4Gi). Two of
three would have refused.

### Diagnosing before you try

Compute headroom per node disk rather than trusting the `Schedulable`
condition alone (a node one GiB under the ceiling reports `True` and still
cannot absorb a 20Gi expansion):

```console
$ kubectl -n longhorn-system get nodes.longhorn.io -o json | jq -r '
    .items[] | .metadata.name as $n |
    (.status.diskStatus | to_entries[] |
      "\($n) scheduled=\((.value.storageScheduled/1073741824)|floor)Gi " +
      "max=\((.value.storageMaximum/1073741824)|floor)Gi")'
```

subtracting `.spec.disks[].storageReserved` to get the ceiling. Then find which
nodes actually host the volume's replicas — only those matter:

```console
$ kubectl -n longhorn-system get replicas.longhorn.io -o json \
    | jq -r --arg v "$VOL" '.items[]|select(.spec.volumeName==$v)|.spec.nodeID'
```

### Fixing it

In order of preference:

1. **Reclaim reservations.** Find volumes backing scaled-to-0 or deleted
   workloads. Reservations persist through detach — a detached volume still
   holds its full declared size. Note this only helps if the dead volumes
   have replicas on the *blocking* node; verify per-node before assuming.
2. **Raise the ceiling declaratively** —
   `defaultSettings.storageOverProvisioningPercentage` in
   `apps/longhorn/values.yaml`. This is what Frank did (100 → 150). It does
   not weaken safety: `storageMinimalAvailablePercentage: 15` still blocks
   scheduling on real disk pressure. Over-provisioning is policy;
   minimal-available is the safety net.
3. **Move the replica.** Delete the replica on the blocked node and let
   Longhorn rebuild it somewhere with room (safe while the other two stay
   healthy) — but it is an imperative fix that leaves no trace in git.

A chart-level `defaultSettings` change does not always reach an already-created
setting. Verify, and restart `longhorn-manager` if it did not take:

```console
$ kubectl -n longhorn-system get settings.longhorn.io \
    storage-over-provisioning-percentage -o jsonpath='{.value}'
```

### Related: reservations held by resources ArgoCD cannot see

The 75Gi that pushed mini-3 over its ceiling belonged to
`hermes-agent-shell-migrate` — a Deployment, Service, two Secrets and five
PVCs hand-created during the 2026-07-09 cutover and **never committed to
git**. With the app at `prune: false`, ArgoCD had no mechanism to remove
them; they were scaled to 0 and forgotten for 18 days.

Reading the manifests will not find these. Read the cluster instead, and
filter by ArgoCD's tracking annotation:

```console
$ kubectl -n <ns> get deploy,pvc,svc -o json | jq -r '.items[] |
    "\(.kind)/\(.metadata.name)\t\(.metadata.annotations."argocd.argoproj.io/tracking-id" // "UNTRACKED")"'
```

Untracked Secrets are expected and correct here (SOPS-applied bootstrap
secrets and ESO-generated Secrets both lack the annotation by design). An
untracked **workload or PVC** is the finding.
