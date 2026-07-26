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
1. Add the service to `apps/homepage/manifests/files/services.yaml` (icon, category, description, URL)
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

### Validating CM/Secret changes from a PR branch (without polluting main)

ArgoCD pulls from `main`, not from feature branches, so a one-shot validation that needs to mutate a ConfigMap/Secret managed by the Application can't go through commit/push/sync. The clean pattern is to suspend self-heal, patch live, capture evidence, then restore:

```bash
# 0. Read the CURRENT automated map first. `--type=merge` REPLACES a nested map
#    rather than merging into it, so patching selfHeal ALONE DELETES its
#    siblings — and `prune: false` above is exactly such a sibling. Dropping it
#    leaves the Application OutOfSync against its root template even after you
#    "restore", because the restore repeats the same mistake. Bit the www
#    rollout 2026-07-26; the drift is inert (ArgoCD defaults prune to false) and
#    therefore easy to leave behind for weeks.
kubectl get application <app> -n argocd -o jsonpath='{.spec.syncPolicy.automated}'

# 1. Suspend self-heal, passing the WHOLE map with only selfHeal flipped.
#    For a leaf app whose spec the root App-of-Apps re-templates, suspend
#    ROOT's selfHeal FIRST — otherwise the leaf patch reverts inside the sync
#    window and your scale-to-0 silently heals mid-measurement.
kubectl patch application <app> -n argocd --type=merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":false,"selfHeal":false}}}}'

# 2. Patch the live resource — for ConfigMaps, account for the kubelet
#    projection lag (~30–60s) before pods see the new value.
kubectl -n <ns> patch configmap <name> --type=merge -p '<patch>'
# wait until the pod sees the new content...
#
#    ...and remember the file landing in the pod is NOT the same as the process
#    using it. Caddy, act_runner and blackbox-exporter all parse config once at
#    boot, so a directory-mounted ConfigMap updates on disk while the process
#    serves the old config indefinitely, ArgoCD green throughout. Reload
#    (`caddy reload`, `kill -HUP 1`) or roll the pod, then verify by asking the
#    PROCESS, not by grepping the file.

# 3. Capture the evidence (logs, MOTD, Telegram message_id, etc.).

# 4. Re-enable self-heal AND force a manual sync to revert the live
#    resource to git ground truth in the same session — never leave
#    selfHeal=false at the end of a script. Restore the full map here too,
#    and restore ROOT last if you suspended it.
kubectl patch application <app> -n argocd --type=merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":false,"selfHeal":true}}}}'
kubectl patch application <app> -n argocd --type=merge \
  -p '{"operation":{"sync":{"revision":"HEAD","syncOptions":["ServerSideApply=true","RespectIgnoreDifferences=true"]}}}'

# 5. Confirm you left no drift — the app must be Synced, not just Healthy.
kubectl get application <app> -n argocd \
  -o custom-columns=SYNC:.status.sync.status,HEALTH:.status.health.status
```

Always pass `syncOptions` explicitly on the manual-sync patch — see the gotcha about manually-triggered syncs not inheriting `spec.syncPolicy.syncOptions`.
