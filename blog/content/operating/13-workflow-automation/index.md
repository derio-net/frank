---
title: "Operating on Workflow Automation"
date: 2026-03-29
draft: false
tags: ["operations", "n8n", "workflow", "automation", "postgresql"]
summary: "Day-to-day commands for managing n8n instances — health checks, database operations, adding new instances, upgrading, and common issues."
weight: 113
cover:
  image: cover.png
  alt: "Frank monitoring workflow dashboards and maintaining n8n conveyor belts"
  relative: true
---

This is the operational companion to [Workflow Automation with n8n]({{< relref "/building/20-workflow-automation" >}}). That post explains the architecture and deployment. This one is the day-to-day runbook for checking health, managing the database, adding instances, and troubleshooting.

## What "Healthy" Looks Like

A healthy n8n instance has:
- The n8n pod running (`1/1 Ready`) on gpu-1
- The PostgreSQL pod running (`1/1 Ready`) in the same namespace
- The LoadBalancer Service showing the assigned external IP
- The `/healthz` endpoint returning 200
- Metrics flowing at `/metrics`

## Observing State

### Pod Health

```bash
# Both pods in one view
kubectl -n n8n-01 get pods

# Detailed pod status (events, conditions)
kubectl -n n8n-01 describe pod -l app.kubernetes.io/name=n8n-01
```

### Service and Networking

```bash
# Verify LoadBalancer IP assignment
kubectl -n n8n-01 get svc n8n-01

# Quick health check
curl -s -o /dev/null -w "%{http_code}" http://192.168.55.216:5678/healthz

# Metrics endpoint
curl -s http://192.168.55.216:5678/metrics | head -10
```

### ArgoCD Sync Status

```bash
# Both apps at a glance
argocd app get n8n-01 --server 192.168.55.200 --insecure | head -10
argocd app get n8n-01-postgresql --server 192.168.55.200 --insecure | head -10
```

### Logs

```bash
# n8n application logs
kubectl -n n8n-01 logs -l app.kubernetes.io/name=n8n-01 -c n8n --tail=50

# PostgreSQL logs
kubectl -n n8n-01 logs -l app.kubernetes.io/name=n8n-01-postgresql --tail=50
```

## Database Operations

### Connect to PostgreSQL

```bash
# Port-forward to access psql
kubectl -n n8n-01 port-forward svc/n8n-01-postgresql 5432:5432 &

# Connect (password from SOPS secret)
PGPASSWORD=$(sops --decrypt secrets/n8n-01/n8n-01-secrets.yaml | grep "  password:" | head -1 | awk '{print $2}') \
  psql -h localhost -U n8n -d n8n
```

### Check Database Size

```sql
SELECT pg_size_pretty(pg_database_size('n8n'));
```

### List Workflow Executions

```sql
SELECT id, "workflowId", finished, "startedAt", "stoppedAt", status
FROM execution_entity
ORDER BY "startedAt" DESC
LIMIT 10;
```

### Clean Old Executions

n8n can accumulate execution history. To prune old entries:

```sql
DELETE FROM execution_entity
WHERE "startedAt" < NOW() - INTERVAL '30 days'
AND status = 'success';
```

## Adding a New Instance

Follow the duplication guide:

```bash
# 1. Copy manifests
cp -r apps/n8n-01 apps/n8n-02
cp -r apps/n8n-01-postgresql apps/n8n-02-postgresql

# 2. Find-replace in all files
find apps/n8n-02 apps/n8n-02-postgresql -type f -exec sed -i '' 's/n8n-01/n8n-02/g' {} +

# 3. Copy Application CRs
for tmpl in ns-n8n-01 n8n-01 n8n-01-postgresql; do
  new=$(echo $tmpl | sed 's/n8n-01/n8n-02/g')
  cp apps/root/templates/${tmpl}.yaml apps/root/templates/${new}.yaml
  sed -i '' 's/n8n-01/n8n-02/g' apps/root/templates/${new}.yaml
done

# 4. Update the IP (pick next available, e.g. 192.168.55.217)
sed -i '' 's/192.168.55.216/192.168.55.217/g' apps/n8n-02/manifests/service.yaml

# 5. Add Authentik proxy provider entries to blueprints-proxy-providers.yaml
# (copy the n8n-01 block, replace n8n-01 → n8n-02, update external_host)

# 6. Create SOPS secret
mkdir -p secrets/n8n-02
# Create secrets/n8n-02/n8n-02-secrets.yaml with new passwords
sops --encrypt --in-place secrets/n8n-02/n8n-02-secrets.yaml

# 7. Apply and push
sops --decrypt secrets/n8n-02/n8n-02-secrets.yaml | kubectl apply -f -
git add apps/n8n-02 apps/n8n-02-postgresql apps/root/templates/*n8n-02* secrets/n8n-02
git commit -m "feat(agents): add n8n-02 instance"
git push
```

## Upgrading n8n

Check the [n8n releases](https://github.com/n8n-io/n8n/releases) for the latest stable version, then update the image tag in the deployment:

```bash
# Current version
kubectl -n n8n-01 get deploy n8n-01 -o jsonpath='{.spec.template.spec.containers[0].image}'

# Update (edit the deployment manifest)
# In apps/n8n-01/manifests/deployment.yaml, change:
#   image: docker.io/n8nio/n8n:2.13.4
# To:
#   image: docker.io/n8nio/n8n:<new-version>

# Commit and push — ArgoCD syncs, Recreate strategy replaces the pod
```

**Before upgrading:** Check the release notes for breaking changes, especially database migrations. n8n runs migrations automatically on startup.

## Restarting

```bash
# Restart n8n (Recreate strategy — brief downtime)
kubectl -n n8n-01 rollout restart deployment n8n-01

# Restart PostgreSQL
kubectl -n n8n-01 rollout restart statefulset n8n-01-postgresql
```

## Troubleshooting

### Pod Stuck in CreateContainerConfigError

The SOPS secret hasn't been applied to the namespace. The pod can't mount the `n8n-01-secrets` Secret.

```bash
# Apply the secret
sops --decrypt secrets/n8n-01/n8n-01-secrets.yaml | kubectl apply -f -
```

### n8n Shows "Secure Cookie" Error

n8n requires TLS for secure cookies. If accessing over plain HTTP:

```bash
# Verify N8N_SECURE_COOKIE is set to false
kubectl -n n8n-01 get deploy n8n-01 -o jsonpath='{.spec.template.spec.containers[0].env}' | python3 -m json.tool | grep -A1 SECURE_COOKIE
```

If missing, add `N8N_SECURE_COOKIE: "false"` to the deployment env vars. Remove it once TLS is configured.

### PostgreSQL Connection Refused

```bash
# Check if PostgreSQL pod is running
kubectl -n n8n-01 get pods -l app.kubernetes.io/name=n8n-01-postgresql

# Check PostgreSQL logs for auth errors
kubectl -n n8n-01 logs -l app.kubernetes.io/name=n8n-01-postgresql --tail=20
```

Common cause: the `existingSecret` key names don't match what Bitnami expects (`postgres-password` for admin, `password` for the app user).

### Workflows Not Triggering on Schedule

Check that `WEBHOOK_URL` is set correctly in the deployment env. n8n uses this to construct callback URLs for webhooks and scheduled triggers. If it's wrong or unreachable, scheduled workflows may silently fail.

```bash
kubectl -n n8n-01 get deploy n8n-01 -o jsonpath='{.spec.template.spec.containers[0].env}' | python3 -m json.tool | grep -A1 WEBHOOK
```

## References

- [n8n self-hosting documentation](https://docs.n8n.io/hosting/)
- [n8n environment variables](https://docs.n8n.io/hosting/configuration/environment-variables/)
- [n8n security bulletin (Feb 2026)](https://community.n8n.io/t/security-bulletin-february-6-2026/261682)
