# Accessing Infisical-synced secrets from inside a Frank pod

This reference documents the pattern in place for the
`secure-agent-pod` namespace. Adapt the names when adding new
workloads.

## Pipeline

```
Infisical  (UI: https://infisical.frank.derio.net, project: frank-cluster, env: prod)
   │
   │ ClusterSecretStore 'infisical'   (ESO auth: Universal Auth token)
   ▼
ExternalSecret 'agent-secrets-tier2'  (refreshInterval: 5m)
   │   manifest: apps/secure-agent-pod/manifests/externalsecret-github-token.yaml
   ▼
K8s Secret agent-secrets-tier2  (namespace: secure-agent-pod)
   │
   │ envFrom on the deployment
   ▼
PID 1 environ in the pod
   │
   │ /opt/bashrc re-exports selected keys into interactive shells
   ▼
$GITHUB_TOKEN, $GEMINI_API_KEY, …
```

## How a pod reads its own secrets

The secure-agent-pod ServiceAccount (`agent-sa`) has cluster-admin,
which is broader than necessary but acceptable for this tier. The
**recommended in-pod read path** is through the SA's kubeconfig at
`/home/claude/.kube/config`:

```bash
kubectl -n secure-agent-pod get secret agent-secrets-tier2 \
  -o jsonpath='{.data.KEY_NAME}' | base64 -d
```

Interactive shells can also use the re-exported env vars (`/opt/bashrc`
sources `/proc/1/environ`), but those only cover the keys explicitly
listed in `bashrc` — newly added keys need either a `bashrc` update or
the `kubectl` path.

## Adding a new key

The ExternalSecret uses `data[]`, **not** `dataFrom`, so adding a key
in Infisical alone does not propagate it.

1. **Infisical** — add the new key in project `frank-cluster` / env
   `prod`. Pick a remote name that is either identical to the in-pod
   env var (`GEMINI_API_KEY` → `GEMINI_API_KEY`) or namespaced with a
   scope prefix (`GITHUB_SECURE_AGENT_POD`, `KALI_C2_TELEGRAM_BOT_TOKEN`).
2. **Manifest** — append to
   `apps/secure-agent-pod/manifests/externalsecret-github-token.yaml`:

   ```yaml
       - secretKey: MY_NEW_KEY         # the env var name seen by the pod
         remoteRef:
           key: MY_NEW_KEY             # the Infisical key name
           conversionStrategy: Default
           decodingStrategy: None
           metadataPolicy: None
   ```

3. **Apply** — `kubectl apply -f …` (or the cluster's GitOps flow).
   ESO syncs within `refreshInterval` (5 minutes). Verify:

   ```bash
   kubectl -n secure-agent-pod get secret agent-secrets-tier2 -o json \
     | jq -r '.data | keys[]' | grep MY_NEW_KEY
   ```

4. **(Optional) re-export in `/opt/bashrc`** — only needed if the key
   should appear in interactive shells without requiring a `kubectl`
   call, and only after confirming that Claude Code sessions on the
   pod don't inherit envFrom (`reference_agent_pod_env.md` in
   willikins memory documents why).

## Why not give pods direct Infisical API access?

The ESO → K8s Secret indirection exists so that:

- Secrets rotate centrally without pod restarts (ESO re-renders the
  K8s Secret; apps pick it up on next read or on envFrom refresh).
- Pods don't need Infisical client credentials, only the K8s API.
- Audit trail lives in the cluster audit log for reads of K8s Secrets,
  not Infisical's.

A pod that hits the Infisical API directly would need its own
Universal Auth token mounted somewhere, which defeats the "only one
thing rotates" design.

## Related

- Willikins-side counterpart: `willikins/references/access.md`
- Security design: `willikins/docs/superpowers/specs/2026-03-30-willikins-agent-security-design.md`
- Template when cloning this pattern for a new namespace:
  `willikins/references/secure-pod-template.md`
