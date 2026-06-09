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

## Standing rules

- Always `ServerSideApply=true` in ArgoCD sync options (avoids annotation size limits).
- Always `prune: false` in syncPolicy — manual pruning only to avoid accidental deletion.
- Always `ignoreDifferences` on Secret data (`/data` jsonPointer) so ArgoCD doesn't fight live mutations.
- SOPS/age encryption for secrets — never commit plaintext.
- Longhorn default replicaCount: 3 (matches 3 control-plane nodes).
