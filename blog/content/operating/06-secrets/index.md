---
title: "Operating on Secrets"
date: 2026-03-13
draft: false
tags: ["operations", "infisical", "external-secrets", "sops", "security"]
summary: "Day-to-day commands for managing secrets in Infisical, checking ESO sync status, and handling SOPS-encrypted bootstrap secrets."
weight: 106
cover:
  image: cover.png
  alt: "Frank carefully handling encrypted data capsules during self-surgery"
  relative: true
---

This is the operational companion to [Secrets Management -- Infisical + External Secrets Operator]({{< relref "/building/09-secrets" >}}). That post covers the architecture and deployment of Infisical + ESO. This one covers the commands you reach for when you need to add a secret, check sync status, or figure out why an application is not picking up a rotated credential.

## Overview

Secrets on Frank flow through two layers:

**Runtime secrets** live in Infisical (192.168.55.204:8080). Applications never touch them directly. External Secrets Operator watches `ExternalSecret` resources, fetches values from Infisical via the `ClusterSecretStore`, and materializes them as native Kubernetes Secrets. The refresh interval (typically 5 minutes) controls how quickly changes propagate.

**Bootstrap secrets** are the credentials that Infisical and ESO themselves need to start -- database passwords, Redis passwords, Machine Identity credentials. These are SOPS-encrypted with age, stored in `secrets/`, and applied manually with `sops --decrypt | kubectl apply -f -`. They exist outside ArgoCD because ArgoCD cannot decrypt SOPS secrets during ServerSideApply.

The rule is simple: if a secret is needed before Infisical is running, it is a SOPS bootstrap secret. Everything else goes into Infisical.

## Observing State

### ESO Sync Status

The first thing to check is whether ESO is successfully syncing secrets from Infisical:

```bash
kubectl get externalsecrets -A
```

Every `ExternalSecret` should show `STATUS: SecretSynced` and `READY: True`. If any show `SecretSyncedError` or `False`, something is broken between ESO and Infisical.

To inspect a specific ExternalSecret in detail:

```bash
kubectl describe externalsecret <name> -n <namespace>
```

The `Events` section at the bottom will show the most recent sync attempts and any error messages.

### ClusterSecretStore Health

The `ClusterSecretStore` is the single connection point between ESO and Infisical. If it is unhealthy, no secrets sync:

```bash
kubectl get clustersecretstore
```

You want `READY: True` and `STATUS: Valid`. If the store shows `SecretStoreError`, the Infisical API is unreachable or the Machine Identity credentials are wrong.

For more detail:

```bash
kubectl describe clustersecretstore infisical
```

### Infisical UI

The Infisical dashboard at `http://192.168.55.204:8080` shows all secrets in the `frank-cluster` project, organized by environment. The audit log (under Project Settings) records who changed what and when. This is the fastest way to verify a secret's current value or check rotation history.

## Routine Operations

### Adding a New Secret

1. Go to the Infisical UI, navigate to the `frank-cluster` project, `prod` environment
2. Add the key-value pair
3. Create an `ExternalSecret` manifest in the consuming app's manifests directory:

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

4. Commit and push -- ArgoCD syncs the ExternalSecret, ESO fetches the value from Infisical

### Rotating a Secret

Update the value in the Infisical UI. ESO picks up the change on the next refresh cycle. If the consuming pod reads secrets from environment variables (not files), it needs a restart to see the new value:

```bash
kubectl rollout restart deployment/<app> -n <namespace>
```

If you cannot wait for the refresh interval, force an immediate sync:

```bash
kubectl annotate externalsecret <name> -n <namespace> \
  force-sync=$(date +%s) --overwrite
```

### Applying SOPS Bootstrap Secrets

Bootstrap secrets are applied manually whenever they change or after a fresh cluster build:

```bash
sops --decrypt secrets/infisical/infisical-secrets.yaml | kubectl apply -f -
sops --decrypt secrets/infisical/eso-credentials.yaml | kubectl apply -f -
```

To verify a SOPS-encrypted file decrypts correctly without applying it:

```bash
sops --decrypt secrets/infisical/infisical-secrets.yaml
```

## Debugging

### ESO Sync Failed

If an ExternalSecret shows `SecretSyncedError`:

1. **Check the ClusterSecretStore** -- if it is unhealthy, all syncs fail:
   ```bash
   kubectl get clustersecretstore
   kubectl describe clustersecretstore infisical
   ```

2. **Check the ESO controller logs** for API errors:
   ```bash
   kubectl logs -n external-secrets deployment/external-secrets --tail=50
   ```

3. **Verify Infisical is reachable** from the cluster:
   ```bash
   kubectl run curl-test --rm -it --image=curlimages/curl -- \
     curl -s http://192.168.55.204:8080/api/status
   ```

4. **Check the Machine Identity credentials** -- the `infisical-credentials` Secret in the `external-secrets` namespace must contain valid `clientId` and `clientSecret` values:
   ```bash
   kubectl get secret infisical-credentials -n external-secrets -o yaml
   ```

### Secret Not Updating After Rotation

If you changed a value in Infisical but the Kubernetes Secret still has the old value:

1. **Check the refresh interval** on the ExternalSecret -- the default is 5 minutes:
   ```bash
   kubectl get externalsecret <name> -n <namespace> -o yaml | grep refreshInterval
   ```

2. **Force a sync** to rule out timing:
   ```bash
   kubectl annotate externalsecret <name> -n <namespace> \
     force-sync=$(date +%s) --overwrite
   ```

3. **Check whether the pod needs a restart** -- environment variables are read at startup, not live-reloaded:
   ```bash
   kubectl rollout restart deployment/<app> -n <namespace>
   ```

### SOPS Decrypt Errors

If `sops --decrypt` fails with an age-related error:

1. **Check that the age key is available** -- SOPS looks for the key in `$SOPS_AGE_KEY_FILE` or `~/.config/sops/age/keys.txt`:
   ```bash
   echo $SOPS_AGE_KEY_FILE
   ls -la ~/.config/sops/age/keys.txt
   ```

2. **Verify the `.sops.yaml` config** points to the correct age public key:
   ```bash
   cat .sops.yaml
   ```

3. **Check that the file was encrypted for the right key** -- the age recipient in the file header must match your key:
   ```bash
   head -5 secrets/infisical/infisical-secrets.yaml
   ```

### Project Slug Issues

If the ClusterSecretStore returns 404 errors, the project slug is likely wrong. Infisical auto-generates slugs that differ from the project display name. The slug for `frank-cluster` is `frank-cluster-iwpg`.

To find the correct slug: open the Infisical UI, go to Project Settings, and check the General tab. The slug is displayed there. Update `apps/infisical/manifests/cluster-secret-store.yaml` with the correct value.

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

- [Infisical Documentation](https://infisical.com/docs) -- Self-hosted setup, Machine Identities, audit logs
- [External Secrets Operator Documentation](https://external-secrets.io/latest/) -- ClusterSecretStore, ExternalSecret v1 API
- [ESO Infisical Provider](https://external-secrets.io/latest/provider/infisical/) -- Provider-specific configuration and auth
- [SOPS Documentation](https://github.com/getsops/sops) -- age encryption, `.sops.yaml` configuration
- [Secrets Management -- Infisical + ESO]({{< relref "/building/09-secrets" >}}) -- Building post covering architecture and deployment
