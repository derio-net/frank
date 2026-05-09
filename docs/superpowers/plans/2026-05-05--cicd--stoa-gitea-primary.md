# Stoa Org Gitea-Primary Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-04--cicd--stoa-gitea-primary-design.md`
**Status:** In Progress

**Type:** Fix/extension of the `cicd` layer (extends `2026-03-29--cicd--platform`). Per `repo-workflows.md`: same layer code, no new blog posts (update layer-19 posts only if a meaningfully new operational pattern emerges).

**Goal:** Onboard `agentic-stoa/hum` and `agentic-stoa/content-factory` onto Frank's Gitea + Tekton stack as Gitea-primary repos with GitHub backup. Establish a reusable pattern (per-repo CI pipeline + shared backup-sync pipeline + branch protection) for future repos in the org.

**Why now:** New private business org needs local-first development on Frank; existing repos at `agentic-stoa/*` on GitHub need migration. Layer-19 CI/CD platform is deployed and idle for this use case.

**Cross-repo coordination:** Single-repo plan (`derio-net/frank`). Paperclip-side wiring (where agents discover Stoa repos and consume `STOA_GITEA_TOKEN`) is out of scope — addressed in a separate plan if/when needed.

---

## Phase 0: Prerequisites — secrets, org, bot account [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/229 -->
**Depends on:** —

Operator-driven setup. All steps interact with external systems (GitHub, Gitea UI, Infisical). Phases 1 and 2 cannot start until secrets exist in Infisical.

### Task 1: Push outstanding local WIP to GitHub

The Phase 3 migration starts with `git clone --mirror` from existing GitHub repos. Anything not on GitHub at that moment is lost.

- [x] **Step 1: Inspect each local clone for uncommitted work**

```bash
for d in ~/repos/hum ~/repos/content-factory; do
  echo "=== $d ==="
  cd "$d" && git status --short && git stash list
done
```

  Resolve any uncommitted state: stage + commit, or stash + commit on a WIP branch — operator's call.

- [x] **Step 2: Push every local branch to GitHub**

```bash
for d in ~/repos/hum ~/repos/content-factory; do
  cd "$d"
  git push origin --all
  git push origin --tags
done
```

  Expected: every `vk/*`, `claude/*`, and feature branch lands on GitHub. The mirror clone in Phase 3 will pick them all up.

- [x] **Step 3: Verify GitHub has every local ref**

```bash
for d in ~/repos/hum ~/repos/content-factory; do
  cd "$d"
  diff <(git for-each-ref --format='%(refname:short)' refs/heads | sort) \
       <(git ls-remote --heads origin | awk '{sub("refs/heads/","",$2); print $2}' | sort)
done
```

  Empty diff = local and GitHub branches match.

### Task 2: Create agentic-stoa Gitea org and stoa-bot service account

```yaml
# manual-operation
id: stoa-gitea-org-create
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary.md
when: "Before any repo migration"
why_manual: "Gitea org creation is a UI/API operation; operator-owned"
commands:
  - "Gitea UI (https://gitea.cluster.derio.net) → + → New Organization → Name: agentic-stoa, visibility: private"
  - "Add operator's Authentik-mapped account as owner"
verify:
  - "curl -H 'Authorization: token $STOA_GITEA_TOKEN' http://192.168.55.209:3000/api/v1/orgs/agentic-stoa | jq .username — returns agentic-stoa"
status: pending
```

- [x] **Step 1: Create the org via Gitea UI** (per manual-op block above)

- [x] **Step 2: Create stoa-bot user**

```yaml
# manual-operation
id: stoa-bot-user-create
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary.md
when: "After agentic-stoa org exists"
why_manual: "Gitea user + token creation requires UI/API interaction"
commands:
  - "Gitea UI → Site Administration → User Accounts → Create (username: stoa-bot, email: stoa@frank.local)"
  - "Add stoa-bot to agentic-stoa org → Teams → Owners (or a custom Write team)"
  - "Sign in as stoa-bot → Settings → Applications → Generate Token (name: paperclip-agent, scopes: write:repository, write:issue, read:organization, no expiry)"
  - "In Infisical, create folder /agentic-stoa under the prod env if it does not exist (UI: Secrets → Add Folder), then store the token there as STOA_GITEA_TOKEN. All future stoa-org secrets live under this folder, separate from frank infra secrets at /."
verify:
  - "Infisical UI: /agentic-stoa/STOA_GITEA_TOKEN exists with non-empty value"
  - "curl -s -o /dev/null -w '%{http_code}\\n' -H 'Authorization: token $STOA_GITEA_TOKEN' http://192.168.55.209:3000/api/v1/orgs/agentic-stoa/members/stoa-bot — returns 204 (stoa-bot is a member of agentic-stoa). 404 means not a member; any 4xx other than 404 means scope mismatch on the token."
  - "curl -H 'Authorization: token $STOA_GITEA_TOKEN' http://192.168.55.209:3000/api/v1/orgs/agentic-stoa/teams | jq -r '.[].name' — lists the org's teams (Owners, plus any custom). Confirms read:organization scope works."
  - "Note: /api/v1/user and /api/v1/user/orgs require read:user scope, which is intentionally NOT in the requested token scopes. Use the org-membership probe above for self-membership checks instead."
status: pending
```

### Task 3: Create GitHub fine-grained PAT

```yaml
# manual-operation
id: stoa-github-mirror-pat
layer: cicd
app: tekton
plan: docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary.md
when: "Before deploying github-backup-sync pipeline; recurs annually"
why_manual: "GitHub fine-grained PATs are UI-generated and cap at 1y TTL; rotation automation is a deferred Open Item in the spec"
commands:
  - "GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token"
  - "Token name: frank-stoa-backup-mirror"
  - "Resource owner: agentic-stoa; Repository access: Only select repositories → hum, content-factory (update when adding repos later)"
  - "Repository permissions: Contents → Read and write; Metadata → Read"
  - "Expiration: 1 year (max). Set a calendar reminder 2 weeks before expiry."
  - "Store token value in Infisical under /agentic-stoa as STOA_GITHUB_MIRROR_TOKEN (same folder as STOA_GITEA_TOKEN; create the folder via Secrets → Add Folder if it does not yet exist)."
verify:
  - "Infisical → /agentic-stoa/STOA_GITHUB_MIRROR_TOKEN exists and not expired"
  - "curl -H 'Authorization: token $STOA_GITHUB_MIRROR_TOKEN' https://api.github.com/repos/agentic-stoa/hum | jq -r .full_name — returns agentic-stoa/hum"
  - "curl -H 'Authorization: token $STOA_GITHUB_MIRROR_TOKEN' https://api.github.com/repos/agentic-stoa/content-factory | jq -r .full_name — returns agentic-stoa/content-factory"
status: pending
```

- [x] **Step 1: Generate the PAT in GitHub UI** (per manual-op block)

- [x] **Step 2: Verify PAT works**

```bash
gh api -H "Authorization: token <PASTE_PAT>" repos/agentic-stoa/hum --jq .full_name
# Expect: agentic-stoa/hum
gh api -H "Authorization: token <PASTE_PAT>" repos/agentic-stoa/content-factory --jq .full_name
# Expect: agentic-stoa/content-factory
```

### Task 4: Verify all secrets are accessible

- [x] **Step 1: Confirm Infisical has both new keys under /agentic-stoa**

  In the Infisical UI (or via CLI), confirm `/agentic-stoa/STOA_GITEA_TOKEN` and `/agentic-stoa/STOA_GITHUB_MIRROR_TOKEN` are present in the prod environment with non-empty values. Both must live in the `/agentic-stoa` folder, not at `/` — frank infra secrets stay at `/`, stoa-org secrets stay scoped to their folder.

- [x] **Step 2: Confirm existing layer-19 secrets still healthy**

```bash
kubectl --context frank get externalsecret -n tekton-pipelines
# Expect: gitea-api-token, gitea-webhook-secret, zot-push-creds all SecretSynced=True
```

---

## Phase 1: Shared github-backup-sync pipeline [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/230 -->
**Depends on:** Phase 0

Deploys the shared backup-sync mechanism: ExternalSecret + Pipeline + Trigger. Pipeline pushes `main` and tags from any `agentic-stoa/*` repo to its GitHub counterpart on every Gitea push event matching the filter.

### Task 1: ExternalSecret for STOA_GITHUB_MIRROR_TOKEN

- [x] **Step 1: Confirm the ClusterSecretStore name**

```bash
kubectl --context frank get externalsecret -n tekton-pipelines gitea-api-token \
  -o jsonpath='{.spec.secretStoreRef.name}{"\n"}{.spec.secretStoreRef.kind}{"\n"}'
# Capture the exact ClusterSecretStore name (e.g., infisical-frank). Use it in Step 2.
```

- [x] **Step 2: Create the ExternalSecret manifest**

  Create `apps/tekton/manifests/externalsecret-stoa-github-mirror.yaml` (substitute `<STORE_NAME>` with the value from Step 1):

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: stoa-github-mirror
  namespace: tekton-pipelines
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: <STORE_NAME>
    kind: ClusterSecretStore
  target:
    name: stoa-github-mirror
    creationPolicy: Owner
  data:
    - secretKey: token
      remoteRef:
        # Absolute path required: the `infisical` ClusterSecretStore is scoped to
        # secretsPath: / (frank infra secrets). Stoa-org secrets live under
        # /agentic-stoa to keep them separated from cluster infra. Per ESO's
        # Infisical provider, any key outside the store's secretsPath must be
        # referenced by absolute path.
        key: /agentic-stoa/STOA_GITHUB_MIRROR_TOKEN
```

### Task 2: github-backup-sync Pipeline manifest

- [x] **Step 1: Create the Pipeline manifest**

  Create `apps/tekton/pipelines/github-backup-sync.yaml`:

```
BEGIN_FILE apps/tekton/pipelines/github-backup-sync.yaml
# Backup-sync: pushes main and tags from agentic-stoa/* repos in Gitea
# to their GitHub counterparts. Triggered by Gitea webhooks on main/tag pushes.
# See spec: docs/superpowers/specs/2026-05-04--cicd--stoa-gitea-primary-design.md
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: github-backup-sync
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-full-name
      type: string
      description: "Repo as owner/repo (e.g., agentic-stoa/hum)"
    - name: gitea-clone-url
      type: string
      description: "Gitea HTTP clone URL"
  workspaces:
    - name: shared-workspace
  tasks:
    - name: clone-mirror
      params:
        - name: gitea-clone-url
          value: $(params.gitea-clone-url)
      workspaces:
        - name: source
          workspace: shared-workspace
      taskSpec:
        workspaces:
          - name: source
        params:
          - name: gitea-clone-url
        steps:
          - name: clone
            image: alpine/git:2.47.2
            workingDir: $(workspaces.source.path)
            securityContext:
              allowPrivilegeEscalation: false
              runAsNonRoot: true
              runAsUser: 65534
              capabilities:
                drop: ["ALL"]
              seccompProfile:
                type: RuntimeDefault
            env:
              - name: HOME
                value: /tekton/home
              - name: GITEA_URL
                value: $(params.gitea-clone-url)
            computeResources:
              requests:
                cpu: 100m
                memory: 256Mi
              limits:
                memory: 1Gi
            script: |
              #!/bin/sh
              set -eu
              git config --global --add safe.directory '*'
              git clone --mirror "$GITEA_URL" repo.git
              cd repo.git
              echo "Refs cloned (first 20):"
              git for-each-ref --format='%(refname)' refs/heads refs/tags | head -20
    - name: push-github
      runAfter: ["clone-mirror"]
      params:
        - name: repo-full-name
          value: $(params.repo-full-name)
      workspaces:
        - name: source
          workspace: shared-workspace
      taskSpec:
        workspaces:
          - name: source
        params:
          - name: repo-full-name
        steps:
          - name: push
            image: alpine/git:2.47.2
            workingDir: $(workspaces.source.path)/repo.git
            securityContext:
              allowPrivilegeEscalation: false
              runAsNonRoot: true
              runAsUser: 65534
              capabilities:
                drop: ["ALL"]
              seccompProfile:
                type: RuntimeDefault
            env:
              - name: HOME
                value: /tekton/home
              - name: REPO_FULL_NAME
                value: $(params.repo-full-name)
              - name: GITHUB_TOKEN
                valueFrom:
                  secretKeyRef:
                    name: stoa-github-mirror
                    key: token
            computeResources:
              requests:
                cpu: 100m
                memory: 256Mi
              limits:
                memory: 512Mi
            script: |
              #!/bin/sh
              set -eu
              git config --global --add safe.directory '*'
              GITHUB_URL="https://oauth2:${GITHUB_TOKEN}@github.com/${REPO_FULL_NAME}.git"
              # Force-push main; --tags is additive (tag deletes don't propagate, by design)
              git push --force "$GITHUB_URL" refs/heads/main:refs/heads/main
              git push "$GITHUB_URL" --tags
              echo "Backup-sync OK for ${REPO_FULL_NAME}"
END_FILE
```

  Note on inline `taskSpec`: this Pipeline doesn't reuse the catalog `git-clone` Task because backup-sync needs `--mirror` semantics, not the depth-limited `git checkout` that `git-clone` does. The two inline steps stay self-contained inside the Pipeline rather than each being promoted to a top-level Task.

### Task 3: Add backup-sync Trigger and TriggerTemplate to gitea-listener

- [x] **Step 1: Read the current EventListener config**

```bash
sed -n '1,80p' apps/tekton/triggers/eventlistener.yaml
```

  Locate the end of the existing `gitea-pipeline-template` resource and the closing of the `triggers:` list in the EventListener.

- [x] **Step 2: Append the new TriggerTemplate**

  At the bottom of `apps/tekton/triggers/eventlistener.yaml`, append:

```yaml
---
# Backup-sync: fires only for agentic-stoa/* on main or tag pushes
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: agentic-stoa-backup-template
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-full-name
    - name: gitea-clone-url
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: stoa-backup-
        namespace: tekton-pipelines
      spec:
        pipelineRef:
          name: github-backup-sync
        params:
          - name: repo-full-name
            value: $(tt.params.repo-full-name)
          - name: gitea-clone-url
            value: $(tt.params.gitea-clone-url)
        taskRunTemplate:
          podTemplate:
            securityContext:
              fsGroup: 65534
        workspaces:
          - name: shared-workspace
            volumeClaimTemplate:
              spec:
                accessModes:
                  - ReadWriteOnce
                storageClassName: longhorn-cicd
                resources:
                  requests:
                    storage: 1Gi
```

- [x] **Step 3: Add the new Trigger inside the EventListener spec.triggers list**

  Inside the EventListener (`metadata.name: gitea-listener`), append a new entry to `spec.triggers` (after the existing `gitea-push` entry):

```yaml
    - name: agentic-stoa-backup
      interceptors:
        - ref:
            name: "cel"
          params:
            - name: "filter"
              value: >-
                header.match('X-Gitea-Event', 'push') &&
                body.repository.full_name.startsWith('agentic-stoa/') &&
                (body.ref == 'refs/heads/main' || body.ref.startsWith('refs/tags/'))
      bindings:
        - ref: gitea-push-binding
        - name: gitea-clone-url
          value: $(body.repository.clone_url)
      template:
        ref: agentic-stoa-backup-template
```

  Note: the existing `gitea-push-binding` doesn't expose a `gitea-clone-url` param, so we add an inline binding.

### Task 4: Commit, sync, and verify backup pipeline is healthy

- [x] **Step 1: Commit changes**

```bash
cd ~/repos/frank
git add apps/tekton/manifests/externalsecret-stoa-github-mirror.yaml \
        apps/tekton/pipelines/github-backup-sync.yaml \
        apps/tekton/triggers/eventlistener.yaml
git commit -m "feat(cicd): add github-backup-sync pipeline for agentic-stoa repos"
git push
```

- [x] **Step 2: Wait for ArgoCD sync and verify resources**

```bash
sleep 30
kubectl --context frank get application -n argocd tekton-extras \
  -o jsonpath='{.status.sync.status}{" "}{.status.health.status}{"\n"}'
# Expect: Synced Healthy

kubectl --context frank get pipeline -n tekton-pipelines github-backup-sync
# Expect: returns the resource

kubectl --context frank get externalsecret -n tekton-pipelines stoa-github-mirror \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# Expect: True

kubectl --context frank get secret -n tekton-pipelines stoa-github-mirror \
  -o jsonpath='{.data.token}' | base64 -d | wc -c
# Expect: > 50 (a real PAT length); does not print the token itself
```

- [x] **Step 3: Confirm EventListener picked up the new trigger**

```bash
kubectl --context frank get eventlistener -n tekton-pipelines gitea-listener \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# Expect: True

kubectl --context frank logs -n tekton-pipelines deploy/el-gitea-listener --tail=20 | grep -iE "error|panic|cel" || echo "no errors"
```

  If the EventListener pod restarted (it does on Trigger config changes), give it ~30s and retry. The CEL parser is strict — invalid expressions show up here.

---

## Phase 2: Per-repo CI pipelines [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/231 -->
**Depends on:** Phase 0

Per-repo CI Pipelines for `hum` (Node) and `content-factory` (Python) plus their Triggers. Independent of Phase 1 — runs in parallel.

### Task 1: hum-ci Pipeline

- [x] **Step 1: Create the Pipeline manifest**

  Create `apps/tekton/pipelines/hum-ci.yaml`:

```
BEGIN_FILE apps/tekton/pipelines/hum-ci.yaml
# CI for agentic-stoa/hum: npm install + typecheck + test across workspaces.
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: hum-ci
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-url
      type: string
    - name: revision
      type: string
    - name: repo-full-name
      type: string
  workspaces:
    - name: shared-workspace
  tasks:
    - name: clone
      taskRef:
        name: git-clone
      params:
        - name: url
          value: $(params.repo-url)
        - name: revision
          value: $(params.revision)
      workspaces:
        - name: output
          workspace: shared-workspace
    - name: test
      runAfter: ["clone"]
      workspaces:
        - name: source
          workspace: shared-workspace
      taskSpec:
        workspaces:
          - name: source
        steps:
          - name: npm-test
            image: node:22-alpine
            workingDir: $(workspaces.source.path)
            securityContext:
              allowPrivilegeEscalation: false
              runAsNonRoot: true
              runAsUser: 1000
              capabilities:
                drop: ["ALL"]
              seccompProfile:
                type: RuntimeDefault
            env:
              - name: HOME
                value: /tekton/home
              - name: npm_config_cache
                value: /tekton/home/.npm
            computeResources:
              requests:
                cpu: 500m
                memory: 1Gi
              limits:
                memory: 2Gi
            script: |
              #!/bin/sh
              set -eu
              run_in() {
                d="$1"
                echo "=== $d ==="
                cd "$d"
                if [ -f package-lock.json ]; then npm ci; else npm install; fi
                npm pkg get scripts.typecheck >/dev/null 2>&1 && npm run typecheck || echo "no typecheck script in $d"
                npm pkg get scripts.test >/dev/null 2>&1 && npm test || echo "no test script in $d"
                cd - >/dev/null
              }
              run_in .
              for ws in backend shared; do
                [ -f "$ws/package.json" ] && run_in "$ws"
              done
  finally:
    - name: report-success
      when:
        - input: $(tasks.status)
          operator: in
          values: ["Succeeded", "Completed"]
      taskRef:
        name: gitea-status
      params:
        - name: repo-full-name
          value: $(params.repo-full-name)
        - name: revision
          value: $(params.revision)
        - name: state
          value: "success"
        - name: description
          value: "All checks passed"
        - name: context
          value: "tekton/ci"
    - name: report-failure
      when:
        - input: $(tasks.status)
          operator: notin
          values: ["Succeeded", "Completed"]
      taskRef:
        name: gitea-status
      params:
        - name: repo-full-name
          value: $(params.repo-full-name)
        - name: revision
          value: $(params.revision)
        - name: state
          value: "failure"
        - name: description
          value: "CI failed"
        - name: context
          value: "tekton/ci"
END_FILE
```

  Note: the `tekton/ci` context name matches the required-status-check pattern referenced by Gitea branch protection in Phase 3 Task 7.

### Task 2: content-factory-ci Pipeline

- [x] **Step 1: Create the Pipeline manifest**

  Create `apps/tekton/pipelines/content-factory-ci.yaml`:

```
BEGIN_FILE apps/tekton/pipelines/content-factory-ci.yaml
# CI for agentic-stoa/content-factory: pip install + pytest.
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: content-factory-ci
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-url
      type: string
    - name: revision
      type: string
    - name: repo-full-name
      type: string
  workspaces:
    - name: shared-workspace
  tasks:
    - name: clone
      taskRef:
        name: git-clone
      params:
        - name: url
          value: $(params.repo-url)
        - name: revision
          value: $(params.revision)
      workspaces:
        - name: output
          workspace: shared-workspace
    - name: test
      runAfter: ["clone"]
      workspaces:
        - name: source
          workspace: shared-workspace
      taskSpec:
        workspaces:
          - name: source
        steps:
          - name: pytest
            image: python:3.13-slim
            workingDir: $(workspaces.source.path)
            securityContext:
              allowPrivilegeEscalation: false
              runAsNonRoot: true
              runAsUser: 1000
              capabilities:
                drop: ["ALL"]
              seccompProfile:
                type: RuntimeDefault
            env:
              - name: HOME
                value: /tekton/home
              - name: PIP_CACHE_DIR
                value: /tekton/home/.pip-cache
            computeResources:
              requests:
                cpu: 500m
                memory: 512Mi
              limits:
                memory: 2Gi
            script: |
              #!/bin/sh
              set -eu
              python -m venv /tekton/home/venv
              . /tekton/home/venv/bin/activate
              pip install --upgrade pip
              [ -f requirements.txt ] && pip install -r requirements.txt
              [ -f requirements-dev.txt ] && pip install -r requirements-dev.txt || true
              pytest -v
  finally:
    - name: report-success
      when:
        - input: $(tasks.status)
          operator: in
          values: ["Succeeded", "Completed"]
      taskRef:
        name: gitea-status
      params:
        - name: repo-full-name
          value: $(params.repo-full-name)
        - name: revision
          value: $(params.revision)
        - name: state
          value: "success"
        - name: description
          value: "All checks passed"
        - name: context
          value: "tekton/ci"
    - name: report-failure
      when:
        - input: $(tasks.status)
          operator: notin
          values: ["Succeeded", "Completed"]
      taskRef:
        name: gitea-status
      params:
        - name: repo-full-name
          value: $(params.repo-full-name)
        - name: revision
          value: $(params.revision)
        - name: state
          value: "failure"
        - name: description
          value: "CI failed"
        - name: context
          value: "tekton/ci"
END_FILE
```

### Task 3: Per-repo CI TriggerTemplates

- [x] **Step 1: Append two new TriggerTemplates to eventlistener.yaml**

  At the bottom of `apps/tekton/triggers/eventlistener.yaml` (after `agentic-stoa-backup-template` from Phase 1), append:

```yaml
---
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: hum-ci-template
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-url
    - name: revision
    - name: repo-full-name
    - name: branch
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: hum-ci-
        namespace: tekton-pipelines
      spec:
        pipelineRef:
          name: hum-ci
        params:
          - name: repo-url
            value: $(tt.params.repo-url)
          - name: revision
            value: $(tt.params.revision)
          - name: repo-full-name
            value: $(tt.params.repo-full-name)
        taskRunTemplate:
          podTemplate:
            securityContext:
              fsGroup: 65534
        workspaces:
          - name: shared-workspace
            volumeClaimTemplate:
              spec:
                accessModes:
                  - ReadWriteOnce
                storageClassName: longhorn-cicd
                resources:
                  requests:
                    storage: 2Gi
---
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: content-factory-ci-template
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-url
    - name: revision
    - name: repo-full-name
    - name: branch
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: content-factory-ci-
        namespace: tekton-pipelines
      spec:
        pipelineRef:
          name: content-factory-ci
        params:
          - name: repo-url
            value: $(tt.params.repo-url)
          - name: revision
            value: $(tt.params.revision)
          - name: repo-full-name
            value: $(tt.params.repo-full-name)
        taskRunTemplate:
          podTemplate:
            securityContext:
              fsGroup: 65534
        workspaces:
          - name: shared-workspace
            volumeClaimTemplate:
              spec:
                accessModes:
                  - ReadWriteOnce
                storageClassName: longhorn-cicd
                resources:
                  requests:
                    storage: 2Gi
```

### Task 4: Per-repo CI Triggers

- [x] **Step 1: Append the two CI Triggers inside spec.triggers**

  In the EventListener's `spec.triggers` list (after `agentic-stoa-backup` from Phase 1), append:

```yaml
    - name: agentic-stoa-hum-ci
      interceptors:
        - ref:
            name: "cel"
          params:
            - name: "filter"
              value: >-
                header.match('X-Gitea-Event', 'push') &&
                body.repository.full_name == 'agentic-stoa/hum'
            - name: "overlays"
              value:
                - key: branch_name
                  expression: "body.ref.split('/')[2]"
        - ref:
            name: "cel"
          params:
            - name: "filter"
              value: >-
                extensions.branch_name != ''
      bindings:
        - ref: gitea-push-binding
      template:
        ref: hum-ci-template
    - name: agentic-stoa-content-factory-ci
      interceptors:
        - ref:
            name: "cel"
          params:
            - name: "filter"
              value: >-
                header.match('X-Gitea-Event', 'push') &&
                body.repository.full_name == 'agentic-stoa/content-factory'
            - name: "overlays"
              value:
                - key: branch_name
                  expression: "body.ref.split('/')[2]"
        - ref:
            name: "cel"
          params:
            - name: "filter"
              value: >-
                extensions.branch_name != ''
      bindings:
        - ref: gitea-push-binding
      template:
        ref: content-factory-ci-template
```

### Task 5: Scope existing gitea-push trigger to non-stoa repos

The existing `gitea-push` trigger has no repo filter, so a push to `agentic-stoa/*` would fire it (running default-`gitea-ci` with echo "no tests"). Adding a negative filter avoids the duplicate run.

- [x] **Step 1: Add agentic-stoa exclusion to existing trigger filter**

  In `apps/tekton/triggers/eventlistener.yaml`, find the existing `gitea-push` trigger's first CEL filter:

```yaml
            - name: "filter"
              value: >-
                header.match('X-Gitea-Event', 'push')
```

  Replace with:

```yaml
            - name: "filter"
              value: >-
                header.match('X-Gitea-Event', 'push') &&
                !body.repository.full_name.startsWith('agentic-stoa/')
```

### Task 6: Commit, sync, and verify

- [x] **Step 1: Commit changes**

```bash
cd ~/repos/frank
git add apps/tekton/pipelines/hum-ci.yaml \
        apps/tekton/pipelines/content-factory-ci.yaml \
        apps/tekton/triggers/eventlistener.yaml
git commit -m "feat(cicd): per-repo CI pipelines for agentic-stoa hum and content-factory"
git push
```

- [x] **Step 2: Verify resources synced**

```bash
sleep 30
kubectl --context frank get pipeline -n tekton-pipelines hum-ci content-factory-ci
# Expect: both returned

kubectl --context frank get triggertemplate -n tekton-pipelines | grep -E "hum-ci-template|content-factory-ci-template|agentic-stoa-backup-template"
# Expect: 3 templates listed (backup from Phase 1, plus two CI from this phase)

kubectl --context frank get eventlistener -n tekton-pipelines gitea-listener \
  -o jsonpath='{range .spec.triggers[*]}{.name}{"\n"}{end}'
# Expect: gitea-push, agentic-stoa-backup, agentic-stoa-hum-ci, agentic-stoa-content-factory-ci
```

- [x] **Step 3: Confirm EventListener pod healthy after re-render**

```bash
kubectl --context frank logs -n tekton-pipelines deploy/el-gitea-listener --tail=30 | grep -iE "error|panic|cel" || echo "no errors"
```

---

## Phase 3: Migration of hum and content-factory [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/232 -->
**Depends on:** Phase 1, Phase 2

Operator-driven migration. Tasks are per-repo; both repos run in parallel — execute each task for both `hum` and `content-factory` before moving to the next task.

### Task 1: Create empty Gitea repos

- [x] **Step 1: Create agentic-stoa/hum on Gitea**

  Gitea UI → + → New Repository → Owner: agentic-stoa, Name: hum, Visibility: Private, Initialize: NO (must stay empty for the mirror push). Default branch: `main`.

- [x] **Step 2: Create agentic-stoa/content-factory on Gitea**

  Same procedure with name `content-factory`.

- [x] **Step 3: Verify both empty repos exist**

```bash
for r in hum content-factory; do
  curl -s -H "Authorization: token $STOA_GITEA_TOKEN" \
    http://192.168.55.209:3000/api/v1/repos/agentic-stoa/$r | jq -r '.full_name + " empty=" + (.empty|tostring)'
done
# Expect:
# agentic-stoa/hum empty=true
# agentic-stoa/content-factory empty=true
```

### Task 2: Mirror clone GitHub → Gitea

```yaml
# manual-operation
id: stoa-repo-migrate-mirror-clone
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary.md
when: "Per repo, after empty Gitea repo created and operator's local WIP is pushed to GitHub (Phase 0 Task 1)"
why_manual: "git clone --mirror runs from operator workstation, not in-cluster"
commands:
  - "Run for each repo: hum, content-factory"
  - "git clone --mirror https://github.com/agentic-stoa/<repo>.git /tmp/<repo>.git"
  - "cd /tmp/<repo>.git && git remote set-url --push origin git@gitea-ssh.cluster.derio.net:agentic-stoa/<repo>.git"
  - "git push --mirror"
  - "cd / && rm -rf /tmp/<repo>.git"
verify:
  - "Gitea UI → agentic-stoa/<repo> → Branches tab: every original GitHub branch present"
  - "Gitea UI → agentic-stoa/<repo> → Tags tab: every original GitHub tag present"
status: pending
```

- [ ] **Step 1: Mirror-clone hum**

**SSH prerequisites (operator workstation, one-time):**
- Tailscale must accept LAN routes: `sudo tailscale up --accept-routes` (or `sudo tailscale set --accept-routes` on an already-registered client). Health-check signal: `tailscale status` prints `Some peers are advertising routes but --accept-routes is false` when the flag is missing.
- The hostname `gitea-ssh.cluster.derio.net` (defined in Headscale's `extra_records`) resolves to `192.168.55.209` (the Gitea LB IP) and is what answers SSH on port 2222. Do NOT use `gitea.cluster.derio.net` for SSH — that resolves to Traefik (`192.168.55.220`), which is HTTPS-only.
- Operator's SSH public key must be registered with a Gitea user that has write access to `agentic-stoa/*` (e.g. an admin account or `stoa-bot`). Use Gitea UI → Settings → SSH/GPG Keys.
- `~/.ssh/config` Host entry: `Host gitea-ssh.cluster.derio.net` with `Port 2222` and `IdentityFile <key>`.

```bash
git clone --mirror https://github.com/agentic-stoa/hum.git /tmp/hum.git
cd /tmp/hum.git
git remote set-url --push origin git@gitea-ssh.cluster.derio.net:agentic-stoa/hum.git
git push --mirror
cd / && rm -rf /tmp/hum.git
```

  Expected: many branches and refs pushed, no errors. Verify in Gitea UI: branch count matches GitHub's pre-migration count.

- [ ] **Step 2: Mirror-clone content-factory**

  Same procedure with `content-factory`.

### Task 3: Add Gitea webhook (per repo)

```yaml
# manual-operation
id: stoa-repo-webhook
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary.md
when: "Per repo, after CI pipeline manifests are deployed (Phase 2)"
why_manual: "Gitea per-repo webhook config is UI-only"
commands:
  - "For each repo (hum, content-factory) in Gitea UI:"
  - "Repo → Settings → Webhooks → Add Webhook → Gitea"
  - "Target URL: http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080"
  - "HTTP Method: POST; Content type: application/json"
  - "Secret: $GITEA_WEBHOOK_SECRET (paste value from Infisical)"
  - "Trigger On: Push events; Branch filter: empty (all branches)"
  - "Active: yes"
verify:
  - "Webhook list shows green checkmark on Test Delivery"
status: pending
```

- [ ] **Step 1: Add webhook on hum** (per manual-op block)

- [ ] **Step 2: Add webhook on content-factory** (per manual-op block)

### Task 4: Smoke test CI pipelines

- [ ] **Step 1: Push a no-op feature-branch commit to hum**

```bash
cd ~/repos/hum
# Add a temporary remote pointing at Gitea (origin still points at GitHub until Task 8)
git remote add gitea git@gitea-ssh.cluster.derio.net:agentic-stoa/hum.git 2>/dev/null || true
git checkout -b test/ci-smoke
echo "" >> README.md
git add README.md && git commit -m "test: ci smoke"
git push gitea test/ci-smoke
```

- [ ] **Step 2: Verify hum-ci PipelineRun fired**

```bash
sleep 10
kubectl --context frank get pipelinerun -n tekton-pipelines --sort-by=.metadata.creationTimestamp \
  -l tekton.dev/pipeline=hum-ci | tail -3
# Expect: a hum-ci-XXXXX PipelineRun in Running or Succeeded state

PR=$(kubectl --context frank get pipelinerun -n tekton-pipelines -l tekton.dev/pipeline=hum-ci \
       -o name --sort-by=.metadata.creationTimestamp | tail -1)
kubectl --context frank logs -n tekton-pipelines $PR -f --all-containers --max-log-requests 6 2>&1 | tail -40
```

- [ ] **Step 3: Verify Gitea PR view shows commit status**

  Gitea UI → agentic-stoa/hum → branch test/ci-smoke → most recent commit: should show a status check with context "tekton/ci".

  Open a PR from `test/ci-smoke` to `main`. Leave it open — Task 5 will merge it as the backup-sync smoke test.

- [ ] **Step 4: Repeat Steps 1–3 for content-factory**

```bash
cd ~/repos/content-factory
git remote add gitea git@gitea-ssh.cluster.derio.net:agentic-stoa/content-factory.git 2>/dev/null || true
git checkout -b test/ci-smoke
echo "" >> README.md && git add README.md && git commit -m "test: ci smoke"
git push gitea test/ci-smoke
sleep 10
kubectl --context frank get pipelinerun -n tekton-pipelines \
  -l tekton.dev/pipeline=content-factory-ci --sort-by=.metadata.creationTimestamp | tail -3
```

  Open the PR on Gitea side; leave it open for Task 5.

### Task 5: Smoke test backup-sync

- [ ] **Step 1: Merge the test PR on hum (Gitea UI)**

  Gitea UI → agentic-stoa/hum → Pull Requests → test/ci-smoke → "Merge Pull Request" (squash). Note: branch protection from Phase 3 Task 7 isn't yet enabled, so the merge will succeed without the operator-only gate. We'll verify protection separately.

  This produces a push to `refs/heads/main` and should fire the `agentic-stoa-backup` trigger.

- [ ] **Step 2: Verify backup PipelineRun fired and pushed to GitHub**

```bash
sleep 10
kubectl --context frank get pipelinerun -n tekton-pipelines \
  -l tekton.dev/pipeline=github-backup-sync --sort-by=.metadata.creationTimestamp | tail -3
# Expect: a stoa-backup-XXXXX PipelineRun in Succeeded state

PR=$(kubectl --context frank get pipelinerun -n tekton-pipelines -l tekton.dev/pipeline=github-backup-sync \
       -o name --sort-by=.metadata.creationTimestamp | tail -1)
kubectl --context frank logs -n tekton-pipelines $PR --all-containers --max-log-requests 4 2>&1 | tail -20
# Expect last line: "Backup-sync OK for agentic-stoa/hum"

# Confirm GitHub got the new main commit
GITEA_HEAD=$(curl -s -H "Authorization: token $STOA_GITEA_TOKEN" \
  http://192.168.55.209:3000/api/v1/repos/agentic-stoa/hum/branches/main | jq -r .commit.id)
GITHUB_HEAD=$(gh api repos/agentic-stoa/hum/branches/main --jq .commit.sha)
[ "$GITEA_HEAD" = "$GITHUB_HEAD" ] && echo "✅ in sync ($GITEA_HEAD)" || echo "❌ drift: gitea=$GITEA_HEAD github=$GITHUB_HEAD"
```

- [ ] **Step 3: Confirm a non-main push does NOT trigger backup-sync**

```bash
cd ~/repos/hum
git checkout test/ci-smoke
echo "" >> README.md && git commit -am "test: non-main push should not trigger backup"
git push gitea test/ci-smoke

sleep 15
COUNT_BEFORE=$(kubectl --context frank get pipelinerun -n tekton-pipelines \
  -l tekton.dev/pipeline=github-backup-sync --no-headers | wc -l)
sleep 30
COUNT_AFTER=$(kubectl --context frank get pipelinerun -n tekton-pipelines \
  -l tekton.dev/pipeline=github-backup-sync --no-headers | wc -l)
[ "$COUNT_BEFORE" = "$COUNT_AFTER" ] && echo "✅ backup did not fire" || echo "❌ unexpected backup PipelineRun"
```

- [ ] **Step 4: Repeat Steps 1–3 for content-factory**

  Merge the content-factory PR, verify backup ran for it, verify non-main push doesn't trigger.

### Task 6: Prune non-main branches from GitHub

```yaml
# manual-operation
id: stoa-prune-github-non-main
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary.md
when: "Per repo, after backup smoke test confirms main propagation"
why_manual: "One-time deletion of legacy branches on GitHub; operator-owned"
commands:
  - "gh auth login   # operator's GitHub identity, NOT the mirror PAT"
  - "for r in hum content-factory; do for b in $(gh api repos/agentic-stoa/$r/branches --jq '.[].name' | grep -v '^main$'); do gh api -X DELETE repos/agentic-stoa/$r/git/refs/heads/$b; done; done"
verify:
  - "gh api repos/agentic-stoa/hum/branches --jq '.[].name' returns only main"
  - "gh api repos/agentic-stoa/content-factory/branches --jq '.[].name' returns only main"
  - "Tags retained: gh api repos/agentic-stoa/<repo>/tags shows pre-migration tag list intact"
status: pending
```

- [ ] **Step 1: Authenticate gh CLI as operator**

```bash
gh auth status || gh auth login
```

- [ ] **Step 2: Delete non-main branches on hum**

```bash
for b in $(gh api repos/agentic-stoa/hum/branches --jq '.[].name' | grep -v '^main$'); do
  echo "Deleting $b"
  gh api -X DELETE repos/agentic-stoa/hum/git/refs/heads/$b
done
gh api repos/agentic-stoa/hum/branches --jq '.[].name'
# Expect: only main
```

- [ ] **Step 3: Delete non-main branches on content-factory**

```bash
for b in $(gh api repos/agentic-stoa/content-factory/branches --jq '.[].name' | grep -v '^main$'); do
  echo "Deleting $b"
  gh api -X DELETE repos/agentic-stoa/content-factory/git/refs/heads/$b
done
gh api repos/agentic-stoa/content-factory/branches --jq '.[].name'
# Expect: only main
```

- [ ] **Step 4: Verify tags retained**

```bash
for r in hum content-factory; do
  GITEA=$(curl -s -H "Authorization: token $STOA_GITEA_TOKEN" \
    http://192.168.55.209:3000/api/v1/repos/agentic-stoa/$r/tags | jq -r '.[].name' | sort | wc -l)
  GITHUB=$(gh api repos/agentic-stoa/$r/tags --jq '.[].name' | sort | wc -l)
  echo "$r: gitea=$GITEA github=$GITHUB"
done
# Expect: counts match per repo
```

### Task 7: Enable Gitea branch protection on main

```yaml
# manual-operation
id: stoa-gitea-branch-protection
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary.md
when: "Per repo, after migration verified"
why_manual: "Branch protection is UI-configured per-repo; defines operator-only merge policy"
commands:
  - "For each repo (hum, content-factory) in Gitea UI:"
  - "Repo → Settings → Branches → Branch Protection Rules → Add Rule"
  - "Branch name pattern: main"
  - "Enable Push (Whitelisted): operator's username only (not stoa-bot)"
  - "Require Pull Request: yes; Required approvals: 1"
  - "Restrict approvals to user/team: operator's user (not stoa-bot)"
  - "Required status checks: tekton/ci (must match the Pipeline gitea-status context)"
  - "Block on rejected reviews: yes"
verify:
  - "As stoa-bot, attempt direct push to main → rejected"
  - "Open a PR as stoa-bot → merge button disabled until CI passes AND operator approves"
status: pending
```

- [ ] **Step 1: Enable branch protection on hum** (per manual-op block)

- [ ] **Step 2: Enable branch protection on content-factory** (per manual-op block)

- [ ] **Step 3: Verify protection blocks direct push as stoa-bot**

```bash
# In a scratch directory:
cd /tmp
git clone https://stoa-bot:${STOA_GITEA_TOKEN}@gitea.cluster.derio.net/agentic-stoa/hum.git /tmp/hum-bot-test
cd /tmp/hum-bot-test
git checkout main
echo "" >> README.md
git -c user.email=stoa-bot@frank.local -c user.name=stoa-bot commit -am "test: should be rejected"
if git push origin main 2>&1 | grep -iE "protected|denied|cannot push"; then
  echo "✅ direct push to main blocked for stoa-bot"
else
  echo "❌ direct push to main was NOT blocked"
fi
cd / && rm -rf /tmp/hum-bot-test
```

### Task 8: Update local clone remotes

```yaml
# manual-operation
id: stoa-local-clone-remap
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary.md
when: "Per repo, after Phase 3 Tasks 1–7 verified"
why_manual: "Operator's local clones live outside the cluster"
commands:
  - "cd ~/repos/<repo>"
  - "git remote set-url origin git@gitea-ssh.cluster.derio.net:agentic-stoa/<repo>.git"
  - "git remote remove gitea  # remove the temp remote added in Task 4 if present"
  - "git fetch origin --prune"
verify:
  - "git remote -v shows gitea-ssh.cluster.derio.net as origin"
  - "git pull works"
status: pending
```

- [ ] **Step 1: Update hum clone remote**

```bash
cd ~/repos/hum
git remote set-url origin git@gitea-ssh.cluster.derio.net:agentic-stoa/hum.git
git remote remove gitea 2>/dev/null || true
git fetch origin --prune
git remote -v
# Expect: origin → gitea-ssh.cluster.derio.net
```

- [ ] **Step 2: Update content-factory clone remote**

```bash
cd ~/repos/content-factory
git remote set-url origin git@gitea-ssh.cluster.derio.net:agentic-stoa/content-factory.git
git remote remove gitea 2>/dev/null || true
git fetch origin --prune
git remote -v
```

- [ ] **Step 3: Final sanity push**

```bash
cd ~/repos/hum
git checkout -b test/post-migration
echo "" >> README.md && git commit -am "post-migration smoke" && git push origin test/post-migration
# Expect: push succeeds; CI fires; PR can be opened against main
git checkout main
git push origin :test/post-migration  # delete the temporary branch on Gitea
git branch -D test/post-migration
```

---

## Phase 4: Post-Deploy Checklist [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/233 -->
**Depends on:** Phase 3

Auto-appended checklist, scoped for the fix/extension nature of this plan.

- [ ] **Step 1: Expose externally** — N/A. Gitea is already exposed via existing Traefik IngressRoute and homepage tile. No new external service.

- [ ] **Step 2: Write building blog post** — SKIP per fix/extension policy. Update layer-19 building post (`blog/content/docs/building/19-cicd-platform/index.md`) only if a meaningfully new operational pattern emerges from execution (e.g., a section on "Gitea-primary repos" referencing this spec).

- [ ] **Step 3: Write operating blog post** — SKIP. Update layer-19 operating post only if new day-to-day commands need documenting (mirror clone runbook, branch-protection-rotation runbook).

- [ ] **Step 4: Update README** — Likely no change. Run `/update-readme`; if it surfaces a Service Access table or repo list that mentions Stoa, accept the update; otherwise leave alone.

- [ ] **Step 5: Sync runbook** — REQUIRED. This plan introduces 8 manual-operation IDs (`stoa-gitea-org-create`, `stoa-bot-user-create`, `stoa-github-mirror-pat`, `stoa-repo-migrate-mirror-clone`, `stoa-repo-webhook`, `stoa-prune-github-non-main`, `stoa-gitea-branch-protection`, `stoa-local-clone-remap`). Run `/sync-runbook`.

- [ ] **Step 6: Update plan status** — Set `**Status:** Deployed` in this plan file once the migration is verified end-to-end.

---

## Deployment Deviations

(Append entries here if the implementation deviates from the spec or this plan during execution.)

### Phase 1 — implementation tweaks (PR #238, 2026-05-09)

- **ExternalSecret apiVersion**: plan body specifies `external-secrets.io/v1beta1`; implementation uses `external-secrets.io/v1` to match the canonical convention used by every other tekton-namespace ExternalSecret in this repo (`externalsecret-gitea-token.yaml`, `externalsecret-cosign.yaml`, etc.). Also added `deletionPolicy: Retain` for symmetry with those siblings.
- **Token leakage hardening on `push-github`**: instead of inlining `https://oauth2:${GITHUB_TOKEN}@github.com/` into the remote URL (which would surface the token in git's stderr on push failure, persisting in TaskRun logs indefinitely), the credential is plumbed via `git config --global url."https://oauth2:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"`. The push then targets the bare `https://github.com/<repo>.git` and git resolves credentials internally without echoing the token in error paths.
- **Workspace storage**: bumped from `1Gi` to `5Gi` to leave headroom for `git clone --mirror` on repos with non-trivial blob history. Stoa repos are small today; cheap insurance.
- **Phase-1/Phase-2 double-firing window**: until Phase 2 Task 5 lands, every push to `agentic-stoa/*` fires *both* the existing `gitea-push` trigger (running `gitea-ci`, which has no required checks defined for these repos and will no-op or fail loudly with no side effects) *and* the new `agentic-stoa-backup` trigger. Acceptable because `gitea-ci` has no destructive steps without an `image` param, and Phase 2 closes the window. Operating note for the reviewer: ignore stray `gitea-ci-*` PipelineRuns labeled with `agentic-stoa/*` repo names during this transition.

### Phase 1 — post-merge verification (2026-05-09, merge commit `2da205b`)

T4.S2 / T4.S3 ran cleanly after the explicit ArgoCD sync trigger landed `2da205b`:

- `Pipeline/github-backup-sync` exists in `tekton-pipelines`.
- `ExternalSecret/stoa-github-mirror`: `Ready=True`, projected `Secret/stoa-github-mirror` token is 93 bytes (matches a real fine-grained PAT).
- `EventListener/gitea-listener`: `Ready=True`; `spec.triggers` lists `gitea-push` and `agentic-stoa-backup`. EL pod logs scrubbed for `error|panic|cel` returned nothing.

**Cosmetic OutOfSync drift on tekton-extras** (acceptable, pre-existing): `kubectl get application tekton-extras` shows `OutOfSync Healthy` even after a successful sync (`status.operationState.phase=Succeeded`), because the Tekton API server defaults fields the source manifest doesn't set (empty `metadata: {}`, `spec: null`, `type: string` on bare param entries, alphabetized key order, etc.). This affects every pre-existing Pipeline and Task in `apps/tekton/` (`gitea-ci`, `git-clone`, `build-push`, `cosign-sign`) identically, not just the new `github-backup-sync` — confirmed via `diff` between live and source. Treat `OutOfSync Healthy` on tekton-extras as the steady state for now; the `phase=Succeeded` on the operation is the authoritative "did the manifest land?" signal. Manifests-vs-API normalization is a separate cleanup, not in scope here.

End-to-end smoke (clone → force-push to GitHub → token kept out of stderr) is exercised in **Phase 3 Task 5** when the first real `agentic-stoa/hum` PR merges to `main`.

### Phase 2 — implementation tweaks (PR #239, 2026-05-09)

Code-review feedback (PR #239 review pass) applied as a follow-up commit on the same PR before merge:

- **UID alignment with `git-clone`**: both `hum-ci` and `content-factory-ci` test steps now run as `runAsUser: 65534` (matching `Task/git-clone`'s UID, which writes the workspace), instead of the original `1000`. The TriggerTemplate `fsGroup: 65534` already matched, but a cross-UID handoff on the RWO PVC still depended on group-write bits being preserved by `git-clone`'s umask — fragile. Aligning the UIDs removes the ambiguity entirely.
- **Shell pipeline robustness in the Node script**: replaced `&&||` chains around `npm run typecheck` / `npm test` with explicit `if/else` blocks. Inside `&&||` chains `set -eu` does not propagate, so a real `npm run typecheck` failure (exit 1 — the actual case the script exists to catch) would have taken the `|| echo "no typecheck script"` branch and the run would have continued green. Also switched the script-presence check from `npm pkg get … >/dev/null && …` (`npm pkg get` exits 0 even for missing keys, returning literal `"{}"`) to `[ "$(npm pkg get scripts.X)" != "{}" ]`.
- **Unused `branch` param dropped** from `hum-ci-template` and `content-factory-ci-template`. `gitea-push-binding` still supplies it; Tekton silently accepts the extra binding param.
- **Python step env**: added `PIP_DISABLE_PIP_VERSION_CHECK=1` and `PYTHONDONTWRITEBYTECODE=1`; dropped `pip install --upgrade pip` (network round-trip on every CI run, no benefit on a pinned `python:3.13-slim` base).

### Phase 2 — post-merge verification (2026-05-09, merge commit `5e5558c`)

T6.S2 / T6.S3 ran cleanly after the explicit ArgoCD sync trigger landed `5e5558c`:

- `Pipeline/hum-ci` and `Pipeline/content-factory-ci` exist in `tekton-pipelines`.
- `TriggerTemplate` list contains all three expected entries: `agentic-stoa-backup-template` (Phase 1), `hum-ci-template`, `content-factory-ci-template`.
- `EventListener/gitea-listener`: `Ready=True`; `spec.triggers` lists exactly the four expected entries in order — `gitea-push` (now narrowed with `!body.repository.full_name.startsWith('agentic-stoa/')`), `agentic-stoa-backup`, `agentic-stoa-hum-ci`, `agentic-stoa-content-factory-ci`. Each routes to the correct template ref.
- `el-gitea-listener` pod: `1/1 Ready`, `RESTARTS=0` (no restart on EL spec change — the controller reloads triggers in-process), no `error|panic|cel` matches in logs since the spec change.
- ArgoCD `tekton-extras` Application: `phase=Succeeded` on the manual sync to `5e5558c`. Cosmetic `OutOfSync Healthy` drift continues per the same Tekton-defaulting note logged for Phase 1; the operation phase is the authoritative signal that the manifests landed.

End-to-end CI smoke (real Gitea push → CI pipeline runs → `tekton/ci` status posted to Gitea) is exercised in **Phase 3 Task 4** when `agentic-stoa/hum` and `agentic-stoa/content-factory` are imported and a test push lands.
