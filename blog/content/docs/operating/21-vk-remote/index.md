---
title: "Operating on VK Remote"
date: 2026-04-13
draft: false
tags: ["operations", "agents", "vibekanban", "postgresql", "electricsql", "troubleshooting"]
summary: "Day-to-day commands for the self-hosted VK Remote stack — PostgreSQL health, ElectricSQL sync status, API verification, and troubleshooting."
weight: 127
---

This is the operational companion to [VK Remote — Self-Hosting the Kanban Backend Before the Cloud Dies]({{< relref "/docs/building/26-vk-remote-self-host" >}}). That post explains the architecture and deployment. This one is the day-to-day runbook.

## What "Healthy" Looks Like

A healthy VK Remote stack has:
- Three pods running in the `agents` namespace: `postgres-vk`, `electric`, `vk-remote`
- PostgreSQL accepting connections with `wal_level=logical`
- ElectricSQL connected to the PG replication stream
- vk-remote responding on port 8081 with a healthy API
- The init Job (`postgres-vk-init-electric`) in Completed state
- Browser access working at `https://vk.cluster.derio.net` through Authentik SSO

## Observing State

### Pod Health

```bash
# All pods in the agents namespace
kubectl -n agents get pods -o wide

# Specifically check the three VK components
kubectl -n agents get pods -l 'app in (postgres-vk, electric, vk-remote)'
```

```console
$ kubectl get pods -n agents -o wide
NAME                              READY   STATUS      RESTARTS   AGE   IP              NODE     NOMINATED NODE   READINESS GATES
electric-6c5f6487d7-prswg         1/1     Running     0          8d    10.244.12.187   mini-1   <none>           <none>
postgres-vk-557b4b6b7-9xvwq       1/1     Running     0          8d    10.244.13.229   mini-2   <none>           <none>
postgres-vk-init-electric-pgqzp   0/1     Completed   0          21h   10.244.12.96    mini-1   <none>           <none>
vk-remote-7949d8bb66-vpgpx        2/2     Running     0          21h   10.244.13.68    mini-2   <none>           <none>
```

### PostgreSQL

```bash
# Check PG is running and WAL level
kubectl -n agents exec deploy/postgres-vk -- \
  psql -U remote -d remote -c "SHOW wal_level;"
# Expected: logical

# Check replication slots (ElectricSQL creates one)
kubectl -n agents exec deploy/postgres-vk -- \
  psql -U remote -d remote -c "SELECT slot_name, active FROM pg_replication_slots;"
```

```console
$ kubectl -n agents exec deploy/postgres-vk -- psql -U remote -d remote -c 'SHOW wal_level;'
 wal_level 
-----------
 logical
(1 row)


$ kubectl -n agents exec deploy/postgres-vk -- psql -U remote -d remote -c 'SELECT slot_name, active FROM pg_replication_slots;'
       slot_name       | active 
-----------------------+--------
 electric_slot_default | t
(1 row)
```

```bash
# Check the electric role exists
kubectl -n agents exec deploy/postgres-vk -- \
  psql -U remote -d remote -c "SELECT rolname FROM pg_roles WHERE rolname = 'electric';"
```

### ElectricSQL

```bash
# ElectricSQL logs — look for "Connected to Postgres" and shape sync activity
kubectl -n agents logs deploy/electric --tail=20

# Check ElectricSQL health
kubectl -n agents exec deploy/vk-remote -- \
  wget -qO- http://electric:3000/v1/health 2>/dev/null || echo "unreachable"
```

### VK Remote API

```bash
# Health endpoint (from inside the cluster)
kubectl -n agents exec deploy/vk-remote -- \
  wget -qO- http://localhost:8081/v1/health

# Health endpoint (via Traefik — will redirect through Authentik if not authenticated)
curl -s -o /dev/null -w "%{http_code}" https://vk.cluster.derio.net/v1/health
```

### Init Job Status

```bash
# Check if the init job completed
kubectl -n agents get jobs
# Expected: postgres-vk-init-electric — Completions: 1/1
```

### Service Endpoints

```bash
# Verify all services have endpoints
kubectl -n agents get endpoints postgres-vk electric vk-remote
```

## Common Operations

### Restart VK Remote

```bash
kubectl -n agents rollout restart deploy/vk-remote
kubectl -n agents rollout status deploy/vk-remote
```

### Restart PostgreSQL

Since PostgreSQL uses Recreate strategy (RWO PVC), the restart will cause brief downtime for the entire stack:

```bash
kubectl -n agents rollout restart deploy/postgres-vk
kubectl -n agents rollout status deploy/postgres-vk
```

After PG restarts, ElectricSQL will automatically reconnect to the replication stream. No manual intervention needed.

### Restart ElectricSQL

```bash
kubectl -n agents rollout restart deploy/electric
kubectl -n agents rollout status deploy/electric
```

### Login and Get JWT Token

```bash
# Get the local auth password
PASSWORD=$(kubectl -n agents get secret vk-remote-secrets \
  -o jsonpath='{.data.SELF_HOST_LOCAL_AUTH_PASSWORD}' | base64 -d)

# Login (from a pod with network access, or via port-forward)
kubectl -n agents port-forward svc/vk-remote 8081:8081 &
TOKEN=$(curl -s -X POST http://localhost:8081/v1/auth/local/login \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"admin@localhost\",\"password\":\"$PASSWORD\"}" | jq -r '.token')
echo "Token: $TOKEN"
```

### List Organizations and Projects

```bash
# List orgs
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8081/v1/organizations | jq

# List projects
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8081/v1/projects | jq
```

### Check PVC Usage

```bash
kubectl -n agents exec deploy/postgres-vk -- df -h /var/lib/postgresql/data
```

## Troubleshooting

### ElectricSQL Not Syncing

**Symptom:** The kanban board in the browser doesn't update in real-time when issues change.

**Check:** Is ElectricSQL connected to the replication stream?

```bash
kubectl -n agents logs deploy/electric --tail=30
```

If you see connection errors:
1. Verify the `electric` PG role exists: `kubectl -n agents exec deploy/postgres-vk -- psql -U remote -d remote -c "SELECT rolname FROM pg_roles WHERE rolname = 'electric';"`
2. If the role is missing, delete and re-trigger the init job: `kubectl -n agents delete job postgres-vk-init-electric` then sync ArgoCD
3. Restart ElectricSQL: `kubectl -n agents rollout restart deploy/electric`

### Init Job Failed

**Symptom:** `kubectl -n agents get jobs` shows `postgres-vk-init-electric` with failed completions.

**Check logs:**

```bash
kubectl -n agents logs job/postgres-vk-init-electric
```

Common causes:
- PostgreSQL wasn't ready in time — delete the job and let ArgoCD re-create it
- Password mismatch — verify the ExternalSecret has synced: `kubectl -n agents get externalsecret vk-remote-secrets`

### 502 on vk.cluster.derio.net

**Symptom:** Browser shows 502 Bad Gateway.

**Check:** Is the vk-remote pod running?

```bash
kubectl -n agents get pods -l app=vk-remote
kubectl -n agents logs deploy/vk-remote --tail=30
```

If the pod is in CrashLoopBackOff, check:
1. Database connectivity: the `SERVER_DATABASE_URL` uses variable substitution — if the Secret is missing, the env var resolves to an empty password
2. Secret sync: `kubectl -n agents get externalsecret vk-remote-secrets -o jsonpath='{.status.conditions}'`

### Cannot Login via API

**Symptom:** POST to `/v1/auth/local/login` returns 401 or 500.

**Check:**
1. Correct password: `kubectl -n agents get secret vk-remote-secrets -o jsonpath='{.data.SELF_HOST_LOCAL_AUTH_PASSWORD}' | base64 -d`
2. Correct email: must be `admin@localhost`
3. Database accessible: the login endpoint writes to PostgreSQL

### Authentik SSO Not Working

**Symptom:** Browser redirects to Authentik but loops or returns 403.

**Check:** Is the Authentik proxy provider assigned to the embedded outpost?

```bash
kubectl exec -n authentik deploy/authentik-server -- python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','authentik.root.settings')
import django; django.setup()
from authentik.outposts.models import Outpost
outpost = Outpost.objects.get(name='authentik Embedded Outpost')
print([p.name for p in outpost.providers.all()])
"
```

If `VK Remote (cluster)` is not in the list, assign it:

```bash
kubectl exec -n authentik deploy/authentik-server -- python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','authentik.root.settings')
import django; django.setup()
from authentik.providers.proxy.models import ProxyProvider
from authentik.outposts.models import Outpost
outpost = Outpost.objects.get(name='authentik Embedded Outpost')
provider = ProxyProvider.objects.get(name='VK Remote (cluster)')
outpost.providers.add(provider)
print(f'Added {provider.name} to {outpost.name}')
"
```

## ArgoCD Sync

```bash
# Check vk-remote app status
argocd app get vk-remote --port-forward --port-forward-namespace argocd

# Force sync if needed
argocd app sync vk-remote --port-forward --port-forward-namespace argocd
```

## References

- [Building Post: VK Remote Self-Host]({{< relref "/docs/building/26-vk-remote-self-host" >}})
- [Operating on VK Relay]({{< relref "/docs/operating/20-vk-relay" >}})
- [Operating on Secure Agent Pod]({{< relref "/docs/operating/14-secure-agent-pod" >}})
- [Operating on Authentication]({{< relref "/docs/operating/08-auth" >}})
