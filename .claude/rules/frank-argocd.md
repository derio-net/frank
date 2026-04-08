## Adding a New ArgoCD App for Frank Cluster 

1. Create `apps/<app-name>/values.yaml` with Helm values
2. Create `apps/root/templates/<app-name>.yaml` with the Application CR
3. (Optional) Create `apps/<app-name>/manifests/` for raw manifests
4. Commit and push — ArgoCD auto-syncs via the root App-of-Apps

### Application Template Pattern

Copy an existing template from `apps/root/templates/` and adapt. Key decisions:

- **Helm chart**: Multi-source — upstream chart + `$values/apps/<app>/values.yaml` ref
- **Raw manifests**: Single source — `path: apps/<app>/manifests`
- **Always include**: `ServerSideApply=true`, `prune: false`, `selfHeal: true`
- **Secrets**: Add `ignoreDifferences` on `/data` jsonPointer

### Homepage Dashboard

When adding a new outward-facing service with an IngressRoute:
1. Add the service to `apps/homepage/manifests/configmap-services.yaml` (icon, category, description, URL)
2. Add the IngressRoute to `apps/traefik/manifests/ingressroutes.yaml`
3. If the service uses Authentik forward-auth (`authentik-forwardauth` middleware):
   a. Add a proxy provider entry to `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml` (follow existing pattern: `forward_single` mode, include `invalidation_flow`)
   b. Register the ConfigMap in `apps/authentik/values.yaml` → `blueprints.configMaps` (already done for the cluster blueprint)
   c. **Manual step (outpost assignment):** After the blueprint is applied, add the new provider to the embedded outpost via Django ORM:
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
      This is required because Authentik blueprints cannot manage outpost provider lists without replacing existing assignments.
