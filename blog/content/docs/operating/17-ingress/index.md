---
title: "Operating on In-Cluster Ingress"
series: ["operating"]
layer: net
date: 2026-04-08
draft: false
tags: ["networking", "traefik", "ingress", "tls", "acme", "authentik", "homepage", "operations"]
summary: "Day-to-day commands for managing Traefik ingress, ACME certificates, IngressRoutes, Authentik forward-auth, and the Homepage dashboard."
weight: 18
---

Companion operations guide for [In-Cluster Ingress — Traefik, Wildcard TLS, and a Homepage Dashboard]({{< relref "/docs/building/24-in-cluster-ingress" >}}).

## Quick Health Check

```bash
# Traefik pod status and node placement
kubectl get pods -n traefik-system -o wide

# Homepage pod
kubectl get pods -n homepage -o wide

# ArgoCD app status
kubectl get applications -n argocd traefik traefik-extras homepage

# ACME cert file size (should be >3KB if cert is issued)
kubectl exec -n traefik-system deploy/traefik -- ls -la /data/acme.json
```

## ACME Certificate

### Check Certificate Status

```bash
# Look for ACME-related log entries
kubectl logs -n traefik-system deploy/traefik | grep -iE "acme|certif|renew"
```

Healthy output shows `Testing certificate renew...` followed by `Starting provider *acme.Provider` with no errors.

### Force Certificate Renewal

Delete the ACME storage and restart to force a fresh cert request:

```bash
kubectl exec -n traefik-system deploy/traefik -- rm /data/acme.json
kubectl delete pod -n traefik-system -l app.kubernetes.io/name=traefik
```

Note: the 60-second propagation delay means renewal takes ~90 seconds.

### Common ACME Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| `permission denied` on acme.json | Missing `fsGroup: 65532` in podSecurityContext | Add top-level `podSecurityContext.fsGroup: 65532` to values |
| `nonexistent certificate resolver` | acme.json unwritable at startup | Fix permissions, restart pod |
| `NXDOMAIN looking up TXT` | DNS propagation too fast | Increase `propagation.delayBeforeChecks` (default: 60s) |
| `NXDOMAIN` persistent | Cloudflare API token invalid | Check `CF_DNS_API_TOKEN` secret in `traefik-system` |

### Verify TLS From CLI

```bash
curl -sI https://argocd.cluster.derio.net 2>&1 | head -5
# Should show HTTP/2 200 or 302 with valid TLS
```

## IngressRoutes

### List All Routes

```bash
kubectl get ingressroutes -n traefik-system
```

### Add a New IngressRoute

1. Add the route to `apps/traefik/manifests/ingressroutes.yaml`
2. Add to `apps/homepage/manifests/configmap-services.yaml`
3. If forward-auth needed:
   - Add blueprint entry to `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml`
   - After deploy, assign provider to outpost (see Authentik section below)

### Debug a Route

```bash
# Check Traefik logs for a specific route
kubectl logs -n traefik-system deploy/traefik | grep "<hostname>"

# Test from inside the cluster (bypasses Traefik)
kubectl run -it --rm debug --image=busybox -- wget -qO- http://<service>.<namespace>:<port>/
```

## Authentik Forward-Auth

### Check Provider Assignment

```bash
kubectl exec -n authentik deploy/authentik-server -- python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','authentik.root.settings')
import django; django.setup()
from authentik.outposts.models import Outpost
outpost = Outpost.objects.get(name='authentik Embedded Outpost')
for p in outpost.providers.all():
    print(f'  {p.name}')
print(f'Total: {outpost.providers.count()} providers')
"
```

### Add a New Provider to the Outpost

After the Authentik blueprint creates the provider:

```bash
kubectl exec -n authentik deploy/authentik-server -- python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','authentik.root.settings')
import django; django.setup()
from authentik.providers.proxy.models import ProxyProvider
from authentik.outposts.models import Outpost
outpost = Outpost.objects.get(name='authentik Embedded Outpost')
provider = ProxyProvider.objects.get(name='<PROVIDER_NAME>')
outpost.providers.add(provider)
print(f'Added {provider.name} to {outpost.name}')
"
```

### Check Blueprint Status

```bash
kubectl exec -n authentik deploy/authentik-server -- python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','authentik.root.settings')
import django; django.setup()
from authentik.blueprints.models import BlueprintInstance
for b in BlueprintInstance.objects.filter(path__contains='proxy'):
    print(f'{b.name} status={b.status}')
"
```

### Force Blueprint Re-Apply

```bash
# Restart the worker (blueprints are processed by the worker, not server)
kubectl rollout restart deploy/authentik-worker -n authentik
```

### Common Forward-Auth Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| HTTP 404 from Authentik | Provider not assigned to outpost | Run the outpost assignment command above |
| HTTP 404 after deploy | Blueprint not applied (missing `invalidation_flow`) | Check worker logs for serializer errors |
| Forward-auth redirect to wrong URL | `AUTHENTIK_HOST` env var wrong | Check `global.env` in `apps/authentik/values.yaml` |

## Homepage Dashboard

{{< screenshot src="homepage-dashboard.png" caption="Homepage dashboard showing all cluster services" >}}

### Restart After ConfigMap Change

ArgoCD syncs the ConfigMap, but the Homepage pod needs a restart to pick up changes:

```bash
kubectl rollout restart deploy/homepage -n homepage
```

### Add a New Service

Edit `apps/homepage/manifests/configmap-services.yaml`:

```yaml
        - ServiceName:
            icon: icon-name    # si-* (Simple Icons) or mdi-* (Material Design)
            href: https://service.cluster.derio.net
            description: One-line description
            siteMonitor: http://service.namespace:port
```

Use `siteMonitor` (HTTP health check), not `ping` (ICMP doesn't work for ClusterIP).

### Check Health From Pod

```bash
# Verify Homepage can reach internal services
kubectl exec -n homepage deploy/homepage -- wget -qO- --timeout=3 http://argocd-server.argocd:80 | head -5
```

## Middleware CRDs

### List Middlewares

```bash
kubectl get middlewares -n traefik-system
```

Current middlewares:
- `security-headers` — HSTS, X-Frame-Options, CSP
- `ip-allowlist` — RFC 1918 ranges only
- `authentik-forwardauth` — Authentik embedded outpost

## Cloudflare DNS Token

The SOPS-encrypted secret is in `secrets/traefik-cloudflare-credentials.yaml`. To re-apply:

```bash
sops --decrypt secrets/traefik-cloudflare-credentials.yaml | kubectl apply -f -
```

## References

- [Traefik IngressRoute CRD](https://doc.traefik.io/traefik/routing/providers/kubernetes-crd/)
- [Traefik ACME Configuration](https://doc.traefik.io/traefik/https/acme/)
- [Authentik Proxy Provider](https://docs.goauthentik.io/docs/providers/proxy/)
- [gethomepage.dev Services Config](https://gethomepage.dev/configs/services/)
