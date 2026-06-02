---
name: expose-service
description: Expose a Frank service externally via Traefik at <name>.cluster.derio.net with TLS, optional SSO, and a homepage tile
user-invocable: true
disable-model-invocation: false
arguments:
  - name: hostname
    description: Subdomain under cluster.derio.net (e.g. "ruflo" → ruflo.cluster.derio.net)
    required: true
  - name: auth
    description: "none (app has its own login) or forwardauth (Authentik SSO in front of an app with no auth)"
    required: false
    default: none
---

# Expose a Service via Traefik

Publish a cluster service at `$ARGUMENTS.hostname.cluster.derio.net` with a
wildcard TLS cert, optional Authentik forward-auth, and a homepage dashboard
tile. This is Step 1 of the Post-Deploy Checklist (`plan-post-deploy-checklist.md`).

> **Domain convention:** new in-cluster services use `*.cluster.derio.net`
> (current). `*.frank.derio.net` is legacy; `omni.frank.derio.net` is a special
> certbot case — don't route new services through them.
> Read first: `agents/rules/frank-gotchas.md` → **Networking** + **Other apps**
> (homepage subPath), and `agents/rules/frank-argocd.md` → Homepage Dashboard.

## Prerequisites

- The backend `Service` exists (`kubectl get svc -n <ns> <name>`); note its name, namespace, port.
- DNS is wildcard: `*.cluster.derio.net` resolves to the Traefik LB `192.168.55.220`. **No per-host DNS step** is needed — adding a subdomain is automatic.

## Steps

### 1. Add the IngressRoute

Append a route to `apps/traefik/manifests/ingressroutes.yaml`. **Copy an existing
route block** from that file rather than writing one — they encode the canonical
shape (`entryPoints: [websecure]`, `certResolver: cloudflare`,
`domains: [{main: "*.cluster.derio.net"}]`, middleware chain).

- `auth=none` → copy a no-auth route (middlewares: `ip-allowlist`, `security-headers`).
- `auth=forwardauth` → copy a route that also lists the `authentik-forwardauth`
  middleware (namespace `authentik`).

Set `match: Host(\`$ARGUMENTS.hostname.cluster.derio.net\`)` and point
`services` at your backend (`name`, `namespace`, `port`).

### 2. (forwardauth only) Wire the Authentik proxy provider

Forward-auth needs a proxy provider **and a manual outpost assignment** — this is
fully documented; follow it, don't re-derive:

1. Add a `forward_single` proxy provider entry to
   `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml`
   (follow the existing entries; include `invalidation_flow`).
2. Confirm the ConfigMap is registered in `apps/authentik/values.yaml`
   → `blueprints.configMaps`.
3. **Manual outpost step (Django ORM):** run the exact snippet in
   `agents/rules/frank-argocd.md` → "Manual step (outpost assignment)". Blueprints
   cannot manage the outpost provider list. Record it as a `# manual-operation`
   and `/sync-runbook`.

### 3. Add the homepage tile

Edit `apps/homepage/manifests/files/services.yaml` (kustomize
`configMapGenerator` — the hash-suffixed name rolls the pod automatically; do
**not** rely on a plain ConfigMap edit, subPath mounts go stale — see Other-apps
gotcha). Add under the right category:

```yaml
    - Display Name:
        icon: <mdi-name-or-url>          # use /homepage-icon-finder if unsure
        href: https://$ARGUMENTS.hostname.cluster.derio.net
        description: One-line description
        siteMonitor: http://<backend-svc>.<backend-ns>:<port>
```

### 4. Commit & sync

```bash
git add apps/traefik/manifests/ingressroutes.yaml apps/homepage/manifests/files/services.yaml
# + the authentik blueprint if auth=forwardauth
git commit -m "feat(net): expose $ARGUMENTS.hostname.cluster.derio.net via Traefik"
```

ArgoCD auto-syncs `traefik`/`traefik-extras` and `homepage`.

### 5. Verify

- DNS: `nslookup $ARGUMENTS.hostname.cluster.derio.net` → `192.168.55.220`
- TLS + reachable: `curl -k -sI https://$ARGUMENTS.hostname.cluster.derio.net` (no 502/503)
- `auth=forwardauth`: `curl -k -i https://$ARGUMENTS.hostname.cluster.derio.net` → 302 to the Authentik host
- Homepage tile appears with a green health dot at `master.cluster.derio.net`

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| 502 Bad Gateway | wrong backend name/port in the route | `kubectl get svc -n <ns>`; match `services[].port` exactly |
| 404 from Traefik | Host rule mismatch | exact FQDN in backticks; request `https://`, full subdomain |
| TLS bad-certificate / handshake error | ACME (Cloudflare DNS-01) hasn't issued | check Traefik logs; cert is wildcard so usually already present |
| forward-auth redirect loop / `0.0.0.0:9000` | outpost missing `AUTHENTIK_HOST`, or step 2.3 skipped | Authentik gotcha + redo the manual outpost step |
| Homepage tile stale / no health dot | subPath staleness, or wrong `siteMonitor` URL | kustomize rolls it; verify `siteMonitor` host:port |

## Summary

Show: route added, auth mode, blueprint + manual outpost step (if any), homepage
tile, and verification output. Point the user at the rest of the Post-Deploy
Checklist (blog post, README, runbook sync).
