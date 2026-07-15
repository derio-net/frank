---
title: "Operating on Secrets"
series: ["operating"]
layer: secrets
date: 2026-03-13
draft: false
tags: ["operations", "infisical", "external-secrets", "sops", "security", "troubleshooting"]
summary: "Day-to-day commands for managing secrets in Infisical, checking ESO sync status, and handling SOPS-encrypted bootstrap secrets."
weight: 7
reader_goal: "Manage secrets through Infisical and ESO, check sync status, rotate credentials, apply SOPS bootstrap secrets, and debug sync failures — without the Infisical UI."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
---

{{< last-updated >}}

This is the operational companion to [Secrets Management — Infisical + External Secrets Operator]({{< relref "/docs/building/09-secrets" >}}). That post covers the architecture and deployment of Infisical + ESO. This one covers the commands you reach for when you need to add a secret, check sync status, or figure out why an application is not picking up a rotated credential.

Source your environment before running commands:

```bash
source .env   # sets KUBECONFIG
```

## Overview

Secrets on Frank flow through two layers:

**Runtime secrets** live in Infisical (`http://192.168.55.204:8080`). External Secrets Operator watches `ExternalSecret` resources, fetches values from Infisical via the `ClusterSecretStore`, and materializes them as native Kubernetes Secrets. Refresh interval is typically 5 minutes.

**Bootstrap secrets** are credentials that Infisical and ESO themselves need to start — database passwords, Machine Identity credentials. These are SOPS-encrypted with age, stored in `secrets/`, and applied manually with `sops --decrypt | kubectl apply -f -`. They exist outside ArgoCD because ArgoCD cannot decrypt SOPS secrets during ServerSideApply.

The rule: if a secret is needed before Infisical is running, it is a SOPS bootstrap secret. Everything else goes into Infisical.

### Verify

```bash
kubectl get externalsecrets -A
# All should show STATUS: SecretSynced, READY: True

kubectl get clustersecretstore
# Should show READY: True, STATUS: Valid
```

## Observing State

### ESO Sync Status

```bash
kubectl get externalsecrets -A
```

```console
$ kubectl get externalsecrets -A
NAMESPACE          NAME                       STORETYPE            STORE       REFRESH INTERVAL   STATUS         READY
agents             vk-remote-secrets          ClusterSecretStore   infisical   5m                 SecretSynced   True
gitea              gitea-secrets              ClusterSecretStore   infisical   5m                 SecretSynced   True
litellm            litellm-api-keys           ClusterSecretStore   infisical   5m                 SecretSynced   True
monitoring         grafana-alerting-secrets   ClusterSecretStore   infisical   5m                 SecretSynced   True
# ... (14 total ExternalSecrets, all SecretSynced)
```

To inspect a specific ExternalSecret:

```bash
kubectl describe externalsecret <name> -n <namespace>
```

The `Events` section shows recent sync attempts and errors.

### ClusterSecretStore Health

```bash
kubectl describe clustersecretstore infisical
```

If the store shows `SecretStoreError`, the Infisical API is unreachable or the Machine Identity credentials are wrong.

### Infisical UI

The dashboard at `http://192.168.55.204:8080` shows all secrets in the `frank-cluster` project. The audit log (Project Settings) records who changed what and when.

{{< screenshot src="infisical-project-prod.png" caption="Infisical prod environment for the frank-cluster project (secret values redacted)" >}}

## Routine Operations

### Adding a New Secret

1. Infisical UI → `frank-cluster` project → `prod` → add key-value pair.
2. Create an `ExternalSecret` manifest in the consuming app's manifests directory:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: my-app-secrets
  namespace: my-app
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: my-app-secrets
  data:
    - secretKey: MY_SECRET_KEY
      remoteRef:
        key: MY_SECRET_KEY
```

3. Commit and push — ArgoCD syncs the ExternalSecret, ESO fetches the value.

### Rotating a Secret

Update the value in Infisical. ESO picks it up on the next refresh. If the consuming pod uses env vars (not files), restart it:

```bash
kubectl rollout restart deployment/<app> -n <namespace>
```

To force an immediate sync:

```bash
kubectl annotate externalsecret <name> -n <namespace> \
  force-sync=$(date +%s) --overwrite
```

### Applying SOPS Bootstrap Secrets

```bash
sops --decrypt secrets/infisical/infisical-secrets.yaml | kubectl apply -f -
sops --decrypt secrets/infisical/eso-credentials.yaml | kubectl apply -f -
```

To verify decryption without applying:

```bash
sops --decrypt secrets/infisical/infisical-secrets.yaml
```

## Runbook

### ESO Sync Failed

If an ExternalSecret shows `SecretSyncedError`:

1. **Check ClusterSecretStore:**
   ```bash
   kubectl get clustersecretstore
   kubectl describe clustersecretstore infisical
   ```

2. **Check ESO controller logs:**
   ```bash
   kubectl logs -n external-secrets deployment/external-secrets --tail=50
   ```

3. **Verify Infisical is reachable:**
   ```bash
   kubectl run curl-test --rm -it --image=curlimages/curl -- \
     curl -s http://192.168.55.204:8080/api/status
   ```

4. **Check Machine Identity credentials:**
   ```bash
   kubectl get secret infisical-credentials -n external-secrets -o yaml
   ```

### Secret Not Updating After Rotation

1. **Check refresh interval:**
   ```bash
   kubectl get externalsecret <name> -n <namespace> -o yaml | grep refreshInterval
   ```

2. **Force sync:**
   ```bash
   kubectl annotate externalsecret <name> -n <namespace> \
     force-sync=$(date +%s) --overwrite
   ```

3. **Restart the consuming pod** (env vars are read at startup, not live-reloaded):
   ```bash
   kubectl rollout restart deployment/<app> -n <namespace>
   ```

### SOPS Decrypt Errors

1. **Check age key availability:**
   ```bash
   echo $SOPS_AGE_KEY_FILE
   ls -la ~/.config/sops/age/keys.txt
   ```

2. **Verify `.sops.yaml`:**
   ```bash
   cat .sops.yaml
   ```

3. **Check age recipient in file header:**
   ```bash
   head -5 secrets/infisical/infisical-secrets.yaml
   ```

### Project Slug Issues

If the ClusterSecretStore returns 404 errors, the project slug is wrong. Infisical auto-generates slugs that differ from the display name — `frank-cluster` has slug `frank-cluster-iwpg`.

Find the correct slug in the Infisical UI → Project Settings → General tab. Update `apps/infisical/manifests/cluster-secret-store.yaml`.

## Missteps

| What we assumed | Why it was wrong | What it cost |
|-----------------|------------------|-------------|
| ArgoCD can manage SOPS-encrypted Secrets through SSA | SOPS `.sops` metadata fields are rejected by ServerSideApply | All bootstrap secrets live outside ArgoCD, applied manually (`secrets/` directory). |
| The Infisical project slug matches the display name | Infisical appends a random suffix to slugs | `frank-cluster` has slug `frank-cluster-iwpg`. 404 errors until the correct slug was found in the UI. |
| Rotated secrets propagate immediately to pods | Env vars are read at container start, not live-reloaded | Pods must be restarted after rotation if they read secrets from env vars. |

## Quick Reference

| Command | What It Does |
|---------|-------------|
| `kubectl get externalsecrets -A` | Show all ExternalSecrets and their sync status |
| `kubectl describe externalsecret <name> -n <ns>` | Detailed sync status with events |
| `kubectl get clustersecretstore` | ClusterSecretStore health check |
| `kubectl describe clustersecretstore infisical` | Detailed store status and errors |
| `kubectl annotate es <name> -n <ns> force-sync=$(date +%s) --overwrite` | Force immediate ESO sync |
| `kubectl rollout restart deployment/<app> -n <ns>` | Restart pods to pick up rotated secrets |
| `kubectl logs -n external-secrets deployment/external-secrets --tail=50` | ESO controller logs |
| `sops --decrypt <file> \| kubectl apply -f -` | Apply a SOPS-encrypted bootstrap secret |
| `sops --decrypt <file>` | Verify SOPS decryption without applying |

## References

- [Infisical Documentation](https://infisical.com/docs) — Self-hosted setup, Machine Identities, audit logs
- [External Secrets Operator Documentation](https://external-secrets.io/latest/) — ClusterSecretStore, ExternalSecret v1 API
- [ESO Infisical Provider](https://external-secrets.io/latest/provider/infisical/) — Provider-specific configuration and auth
- [SOPS Documentation](https://github.com/getsops/sops) — age encryption, `.sops.yaml` configuration
- [Secrets Management — Infisical + ESO]({{< relref "/docs/building/09-secrets" >}}) — Building post covering architecture and deployment
