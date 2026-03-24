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
