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

## Standing rules

- Always `ServerSideApply=true` in ArgoCD sync options (avoids annotation size limits).
- Always `prune: false` in syncPolicy — manual pruning only to avoid accidental deletion.
- Always `ignoreDifferences` on Secret data (`/data` jsonPointer) so ArgoCD doesn't fight live mutations.
- SOPS/age encryption for secrets — never commit plaintext.
- Longhorn default replicaCount: 3 (matches 3 control-plane nodes).
