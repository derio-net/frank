# Ruflo Pod Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-02--orch--ruflo-pod-design.md`
**Status:** Not Started

**Type:** New layer in the `orch` capability domain (sibling to Paperclip). Per `repo-workflows.md`: standard layer workflow, includes NEW building/operating blog posts and a new homepage tile.

**Goal:** Deploy `ruflo` (the rebrand of ruvnet's `claude-flow`) as a 24/7 multi-agent orchestration pod on Frank, with the ruvocal web UI exposed at `https://ruflo.cluster.derio.net` behind Authentik forward-auth, an SSH+Mosh shell sidecar at `192.168.55.222`, and zero direct frontier-LLM provider keys (all traffic through the in-cluster LiteLLM gateway and OpenRouter).

**Why now:** Frank already runs Paperclip as a structured org-chart orchestrator. Ruflo provides a contrasting paradigm — more organic, more chaotic, swarm-shaped — and lets the cluster's "let competing paradigms decide via the work" philosophy continue past Paperclip into a second orchestrator. The shell-sidecar pattern is freshly proven (paperclip-shell-sidecar dispatched today), so the marginal cost of a second instance is low.

**Cross-repo coordination:**
- Phase 1 lands in [`derio-net/agent-images`](https://github.com/derio-net/agent-images) — two new directories (`ruflo-server/`, `ruflo-shell/`), CI smoke tests, one merged PR producing two GHCR tags.
- Phases 2–6 land in this repo (`derio-net/frank`).
- Phase 2 is blocked on Phase 1 producing both image SHAs.

---

## Phase 1: Build `ruflo-server` and `ruflo-shell` images (agent-images repo) [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/182 -->
**Depends on:** —

This phase ships two new container images. `ruflo-server` is a thin build from the upstream ruvocal Dockerfile. `ruflo-shell` is a near-clone of the just-shipped `paperclip-shell` image — same `agent-shell-base` lineage, same inventory installer pattern, different Layer-1 baked tools and slightly different rootfs metadata. Both ship in one PR with one CI run.

### Task 1: Investigate base image inheritance (shared with paperclip-shell)

Before writing anything, confirm the shell-base parent's defaults. The paperclip-shell PR established the canonical lookup pattern; reuse it.

- [x] **Step 1: Read `agent-shell-base` Dockerfile and rootfs layout**

```bash
gh repo clone derio-net/agent-images /tmp/agent-images && cd /tmp/agent-images
cat agent-shell-base/Dockerfile
ls agent-shell-base/rootfs/etc/cont-init.d/ 2>/dev/null
ls agent-shell-base/rootfs/etc/skel/ 2>/dev/null
```

  Capture: default `AGENT_USER` / `AGENT_HOME` build args, sshd port, MOTD plumbing location, whether `pam_motd` / `motd.dynamic` is wired up. The new `ruflo-shell` image relies on inheriting all of these unchanged.

- [x] **Step 2: Confirm s6-overlay non-root-mode fixes have landed**

  Check `agent-shell-base/Dockerfile` for `chown -R ${AGENT_UID}:${AGENT_GID} /run /var/run` (per the gotcha at `frank-gotchas.md` line 91) and the `with-contenv` shebang fix from observations 2469–2474. Both should be present after the paperclip-shell PR campaign. If either is missing, block this phase on the relevant agent-images PR; do not work around locally.

- [x] **Step 3: Read `paperclip-shell` rootfs to compare against**

```bash
ls /tmp/agent-images/paperclip-shell/rootfs/usr/local/lib/paperclip-shell/
cat /tmp/agent-images/paperclip-shell/Dockerfile
```

  The paperclip-shell helper scripts (`install-base-runtimes.sh`, `install-inventory.sh`, `notify-telegram.sh`) are the templates for ruflo-shell's equivalents. The two diverge only in the `paperclip-shell` ↔ `ruflo-shell` string and the Layer-1 baked tool list.

### Task 2: Investigate upstream ruvocal Dockerfile

- [x] **Step 1: Clone upstream ruvnet/ruflo at HEAD and read the ruvocal Dockerfile**

```bash
gh repo clone ruvnet/ruflo /tmp/ruflo && cd /tmp/ruflo
git rev-parse HEAD                                      # capture this SHA — pin to it
cat src/ruvocal/Dockerfile
```

  Capture: base image, default `CMD`/`ENTRYPOINT`, exposed port, workspace path, expected env vars (`MONGO_URL` / `MONGODB_URI` / similar), whether `INCLUDE_DB=false` is honored or always installs Mongo.

- [x] **Step 2: Decide build path** — record the decision in this plan's Deployment Notes:

  - **(a) Direct vendor build:** if `src/ruvocal/Dockerfile` cleanly accepts `INCLUDE_DB=false` (no Mongo install steps run), our `ruflo-server/Dockerfile` is just `FROM ruvocal:built ...` or replicates upstream with a pinned base. Cleanest.
  - **(b) Thin wrapper:** if `INCLUDE_DB=false` is broken/unhonored, our Dockerfile copies upstream's `src/ruvocal/` and builds it ourselves, skipping Mongo install layers.

  Step 1's Dockerfile read tells you which path is needed. Document the choice and the upstream SHA in Deployment Notes.

### Task 3: Add `ruflo-server/` directory

- [x] **Step 1: Create directory layout**

```
agent-images/ruflo-server/
├── Dockerfile
└── README.md
```

- [x] **Step 2: Write the Dockerfile** (use BEGIN/END markers because the file pins an upstream SHA inline)

```
BEGIN ruflo-server/Dockerfile
# Pinned to ruvnet/ruflo SHA <UPSTREAM_SHA_FROM_TASK_2_STEP_1>
ARG RUFLO_GIT_REF=<UPSTREAM_SHA_FROM_TASK_2_STEP_1>

FROM node:20-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN git clone --depth 1 https://github.com/ruvnet/ruflo.git . \
 && git fetch --depth 1 origin "${RUFLO_GIT_REF}" \
 && git checkout "${RUFLO_GIT_REF}"
WORKDIR /build/src/ruvocal
RUN npm ci --omit=dev

FROM node:20-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -u 1000 -m -s /bin/bash ruvocal
WORKDIR /app
COPY --from=builder --chown=ruvocal:ruvocal /build/src/ruvocal /app
USER ruvocal
EXPOSE 3000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "server.js"]
END ruflo-server/Dockerfile
```

  This is **option (b) thin-wrapper** as the default — replace with option (a) if Task 2 Step 2 chose differently. Specifically: if upstream's Dockerfile builds cleanly with `INCLUDE_DB=false`, replace the FROM/build steps above with a `FROM` against the upstream-built image plus a thin layer for tini and uid 1000. The exact CMD / EXPOSE / WORKDIR values come from Task 2 Step 1 — substitute the actual values, do not leave the placeholders.

- [x] **Step 3: Write `ruflo-server/README.md`**

  One page: image purpose, the `RUFLO_GIT_REF` build arg, expected runtime env vars (`MONGO_URL`, `OPENROUTER_API_KEY`, `EMAIL_RESEND_API_KEY`, `LITELLM_BASE_URL`), the workspace mount path, link back to this plan and the spec.

### Task 4: Add `ruflo-shell/` directory (clone of `paperclip-shell` with three diffs)

- [x] **Step 1: Copy `paperclip-shell/` to `ruflo-shell/` as a starting point**

```bash
cd /tmp/agent-images
cp -r paperclip-shell ruflo-shell
find ruflo-shell -type f \( -name '*.sh' -o -name 'Dockerfile' -o -name '40-shell-inventory' \) \
  -exec sed -i'' -e 's/paperclip-shell/ruflo-shell/g' {} +
mv ruflo-shell/rootfs/usr/local/lib/paperclip-shell ruflo-shell/rootfs/usr/local/lib/ruflo-shell
```

  Sanity-check after the rewrite:

```bash
grep -rn paperclip ruflo-shell/   # should return zero matches; ruflo-shell is independent of paperclip
```

- [x] **Step 2: Adjust `ruflo-shell/Dockerfile`** — add `@anthropic-ai/claude-code` to Layer-1 baked-in tools (the operator wants `claude` available immediately from the shell, before the inventory has been populated)

  Edit `ruflo-shell/Dockerfile` so the `RUN install-base-runtimes.sh` line is followed by:

```dockerfile
RUN /usr/local/lib/ruflo-shell/install-base-runtimes.sh \
 && npm install -g @anthropic-ai/claude-code \
 && ln -sf /usr/local/lib/ruflo-shell/install-inventory.sh /usr/local/bin/ruflo-shell-reconcile
```

  (Order matters: `install-base-runtimes.sh` brings in mise/rustup/pipx, so npm is already available via the system Node from agent-shell-base. Confirm in Task 1 Step 1 that agent-shell-base provides system `node`/`npm`. If not, the npm-global install fits more cleanly inside `install-base-runtimes.sh` itself.)

- [x] **Step 3: Adjust `/etc/skel/.bashrc`** to export `LITELLM_BASE_URL` and the operator-facing banner

```
BEGIN ruflo-shell/rootfs/etc/skel/.bashrc-ruflo
# Sourced from .bashrc — exposes ruflo-specific env and banner.
export LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://litellm.litellm-system:4000}"

if [[ -n "${SSH_CONNECTION:-}" && -z "${RUFLO_BANNER_SHOWN:-}" ]]; then
  cat <<'BANNER'
─────────────────────────────────────────
 ruflo-shell — operator side door for ruflo
   /workspace      ← shared with ruvocal (read/write)
   /home/agent     ← yours; persists across pod restarts
   ruflo-shell-reconcile  ← apply inventory changes without restart
─────────────────────────────────────────
BANNER
  export RUFLO_BANNER_SHOWN=1
fi
END ruflo-shell/rootfs/etc/skel/.bashrc-ruflo
```

  Append `[ -f ~/.bashrc-ruflo ] && source ~/.bashrc-ruflo` to the existing `/etc/skel/.bashrc` (do not overwrite — it likely contains tmux/mise/cargo PATH wiring inherited from agent-shell-base or paperclip-shell).

- [x] **Step 4: Verify `notify-telegram.sh` references `ruflo-shell`** in its alert title and `kubectl logs` hint (the sed in Task 4 Step 1 should have caught this; confirm by reading the file).

- [x] **Step 5: Update `ruflo-shell/README.md`** — same shape as paperclip-shell's README but pointing at this plan and noting the `claude-flow` is *not* baked in (it lives in the inventory, where it can be bumped without rebuilding the image).

### Task 5: Add CI matrix entries + smoke tests

- [x] **Step 1: Add `ruflo-server` to the build matrix** in `.github/workflows/build.yaml` (or whatever the agent-images CI workflow is named) alongside `secure-agent-kali`, `vk-local`, and `paperclip-shell`. Build pushes to `ghcr.io/derio-net/ruflo-server:<sha>`.

- [x] **Step 2: Add `ruflo-shell` to the same build matrix.** Build pushes to `ghcr.io/derio-net/ruflo-shell:<sha>`.

- [x] **Step 3: Add smoke test for `ruflo-shell`** mirroring paperclip-shell:

```bash
docker run --rm --user 1000:1000 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  ghcr.io/derio-net/ruflo-shell:${{ github.sha }} \
  bash -c '
    /init &
    for i in $(seq 1 30); do
      if ss -ltn 2>/dev/null | grep -q ":2222"; then echo "sshd up"; exit 0; fi
      sleep 1
    done
    echo "sshd never bound 2222"; exit 1
  '
```

  Also assert: `mise --version`, `pipx --version`, `rustup --version`, `claude --version`, `ruflo-shell-reconcile` (with empty inventory mount) all succeed.

- [x] **Step 4: Add smoke test for `ruflo-server`** — boot the container against a transient mongo and curl the healthcheck:

```bash
docker network create ruflo-test-net
docker run --rm -d --name ruflo-test-mongo --network ruflo-test-net \
  -e MONGO_INITDB_ROOT_USERNAME=test -e MONGO_INITDB_ROOT_PASSWORD=test \
  mongo:7
docker run --rm -d --name ruflo-test-server --network ruflo-test-net \
  -e MONGO_URL='mongodb://test:test@ruflo-test-mongo:27017/ruvocal?authSource=admin' \
  -p 13000:3000 \
  ghcr.io/derio-net/ruflo-server:${{ github.sha }}
for i in $(seq 1 30); do
  if curl -fsS http://localhost:13000/ >/dev/null; then echo "ruvocal up"; break; fi
  sleep 2
done
docker logs ruflo-test-server | tail -50
docker rm -f ruflo-test-server ruflo-test-mongo
docker network rm ruflo-test-net
```

  The `/` endpoint may serve the SPA — accept any 2xx/3xx as "up." If ruvocal exposes a proper `/healthz` or `/api/status`, switch to that.

### Task 6: Open PR, review, merge

- [x] **Step 1: Open PR titled `feat: add ruflo-server and ruflo-shell images`** with body linking to this plan. Wait for CI green on both images' smoke tests.

- [ ] **Step 2: Capture both merged image SHAs** — record in this plan's *Deployment Notes* as:

```
agent-images SHA: <sha>
ghcr.io/derio-net/ruflo-server:<sha>
ghcr.io/derio-net/ruflo-shell:<sha>
```

  Phase 2 references both.

---

## Phase 2: Frank manifests for ruflo + ruflo-db [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/183 -->
**Depends on:** Phase 1

All work in this repo (`derio-net/frank`). One PR, one ArgoCD sync. Adds two ArgoCD apps (`ruflo-db` synced first, then `ruflo`), ingress, Authentik blueprint, and homepage tile.

### Task 1: Pre-flight Infisical

```yaml
# manual-operation
id: ruflo-infisical-bootstrap
layer: orch
app: ruflo
plan: docs/superpowers/plans/2026-05-02--orch--ruflo-pod.md
when: before opening the Phase 2 PR
why_manual: Infisical entries are not reproducible from git; ESO needs the secret to exist before Phase 2 manifests reference it
commands:
  - description: Add RUFLO_DB_PASSWORD to Infisical
    command: |
      # Via Infisical UI at https://infisical.derio.net or `infisical secrets set`:
      # Path:  /shared (or whichever path apps/ruflo/manifests/externalsecret-db-credentials.yaml references)
      # Key:   RUFLO_DB_PASSWORD
      # Value: <generated 32+ char random>
  - description: Confirm OPENROUTER_API_KEY is reachable from a ruflo-system path
    command: |
      # Either copy the existing entry under /shared, or grant the ruflo-system ServiceAccount
      # access to the path that hosts it. Check apps/litellm/manifests/externalsecret-*.yaml
      # for the reference shape.
  - description: Confirm EMAIL_RESEND_API_KEY is reachable from a ruflo-system path
    command: |
      # Same pattern — see apps/paperclip/manifests/external-secret-resend.yaml for reference.
verify:
  - description: All three keys appear in Infisical for the path the ESOs will reference
    command: infisical secrets list --path /shared | grep -E 'RUFLO_DB_PASSWORD|OPENROUTER_API_KEY|EMAIL_RESEND_API_KEY'
status: pending
```

- [ ] **Step 1: Generate `RUFLO_DB_PASSWORD`** (32+ char random) and add to Infisical under the path the `apps/ruflo/manifests/externalsecret-db-credentials.yaml` ESO will reference.
- [ ] **Step 2: Confirm `OPENROUTER_API_KEY` and `EMAIL_RESEND_API_KEY` are accessible from a `ruflo-system`-permitted Infisical path.** If not, copy the entries under `/shared` (the path used by paperclip's ESOs) or extend ServiceAccount access.

### Task 2: Add `apps/ruflo-db/` ArgoCD sub-app

- [ ] **Step 1: Read `apps/paperclip-db/` to mirror its shape**

```bash
ls apps/paperclip-db/
cat apps/paperclip-db/values.yaml 2>/dev/null
cat apps/root/templates/paperclip-db.yaml
```

  Capture: chart name + version, repo source, secret structure, PVC sizing override pattern, sync wave/ordering.

- [ ] **Step 2: Create `apps/ruflo-db/values.yaml`** — copy paperclip-db's values, adjust naming (`paperclip` → `ruflo`), set PVC size to `20Gi`, set the secret reference to a new ESO-managed Secret name (`ruflo-db-credentials`).

- [ ] **Step 3: Create `apps/ruflo-db/manifests/externalsecret-db.yaml`** — ESO producing `ruflo-db-credentials` Secret in namespace `ruflo-system`, sourcing `RUFLO_DB_PASSWORD` from Infisical. Use `apps/paperclip-db/manifests/external-secret-*.yaml` (or paperclip's equivalent) as the template. Ensure the produced Secret also exposes the full `MONGO_URL` connection string (including the password) so ruvocal can consume it directly via `secretKeyRef`.

- [ ] **Step 4: Create `apps/root/templates/ruflo-db.yaml`** — Application CR mirroring `apps/root/templates/paperclip-db.yaml`. Same `syncPolicy`: `ServerSideApply=true`, `prune: false`, `selfHeal: true`. Sync wave should be **before** `ruflo` so Mongo is up when ruvocal connects on first boot.

### Task 3: Add `apps/ruflo/` namespace, PVCs, ConfigMap, ServiceAccount

- [ ] **Step 1: Create `apps/ruflo/manifests/namespace.yaml`**

```
BEGIN apps/ruflo/manifests/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ruflo-system
  labels:
    pod-security.kubernetes.io/enforce: baseline
END apps/ruflo/manifests/namespace.yaml
```

- [ ] **Step 2: Create `apps/ruflo/manifests/pvc-workspace.yaml`**

```
BEGIN apps/ruflo/manifests/pvc-workspace.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ruflo-workspace
  namespace: ruflo-system
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 50Gi
END apps/ruflo/manifests/pvc-workspace.yaml
```

- [ ] **Step 3: Create `apps/ruflo/manifests/pvc-shell-home.yaml`**

```
BEGIN apps/ruflo/manifests/pvc-shell-home.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ruflo-shell-home
  namespace: ruflo-system
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 20Gi
END apps/ruflo/manifests/pvc-shell-home.yaml
```

- [ ] **Step 4: Create `apps/ruflo/manifests/configmap-shell-inventory.yaml`** (initially empty arrays, populated in Phase 4)

```
BEGIN apps/ruflo/manifests/configmap-shell-inventory.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ruflo-shell-inventory
  namespace: ruflo-system
data:
  inventory.yaml: |
    # Layer-2 declarations — installed at boot via cont-init.d.
    # See docs/superpowers/specs/2026-05-02--orch--ruflo-pod-design.md
    mise: []
    npm-global: []
    pipx: []
    cargo: []
    removed:
      mise: []
      npm-global: []
      pipx: []
      cargo: []
END apps/ruflo/manifests/configmap-shell-inventory.yaml
```

- [ ] **Step 5: Create `apps/ruflo/manifests/serviceaccount.yaml`** — minimal SA for the pod and for ESO.

```
BEGIN apps/ruflo/manifests/serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ruflo
  namespace: ruflo-system
END apps/ruflo/manifests/serviceaccount.yaml
```

### Task 4: Add ExternalSecrets

- [ ] **Step 1: Read existing reference ESOs**

```bash
cat apps/paperclip/manifests/external-secret-resend.yaml
cat apps/secure-agent-pod/manifests/externalsecret-github-token.yaml
ls apps/litellm/manifests/ | grep -i external
```

  Capture: `secretStoreRef.name`/`kind`, the Infisical path convention, the `data:` vs `dataFrom:` shape, and how `agent-ssh-keys` is shaped where it currently exists.

- [ ] **Step 2: Create `apps/ruflo/manifests/externalsecret-openrouter.yaml`** producing Secret `ruflo-openrouter` with key `OPENROUTER_API_KEY` from Infisical.

- [ ] **Step 3: Create `apps/ruflo/manifests/externalsecret-resend.yaml`** producing Secret `ruflo-resend` with key `EMAIL_RESEND_API_KEY` from Infisical. Use the paperclip resend ESO as the literal template.

- [ ] **Step 4: Create `apps/ruflo/manifests/externalsecret-shell-ssh-keys.yaml`** producing Secret `ruflo-shell-ssh-keys` from the same Infisical entries that `agent-ssh-keys` uses (shared with secure-agent-pod and paperclip-shell).

- [ ] **Step 5: Create `apps/ruflo/manifests/externalsecret-shell-alerts.yaml`** producing Secret `ruflo-shell-alerts` with `FRANK_C2_TELEGRAM_BOT_TOKEN` and `FRANK_C2_TELEGRAM_CHAT_ID`. Mirror paperclip-shell's equivalent (which Phase 2 of that plan introduces — copy from there if it has merged by the time this phase runs; otherwise create from scratch using the same Infisical source).

### Task 5: Add the Web UI ClusterIP Service

- [ ] **Step 1: Create `apps/ruflo/manifests/service-web.yaml`**

```
BEGIN apps/ruflo/manifests/service-web.yaml
apiVersion: v1
kind: Service
metadata:
  name: ruflo-web
  namespace: ruflo-system
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: ruflo
    app.kubernetes.io/component: server
  ports:
    - { name: http, port: 80, targetPort: 3000, protocol: TCP }
END apps/ruflo/manifests/service-web.yaml
```

  `targetPort: 3000` is the working assumption from the spec's plan-time investigation. If Task 2 of Phase 1 surfaced a different port from upstream's Dockerfile, substitute that value here and in `deployment.yaml` (Task 7) consistently.

### Task 6: Add the Shell SSH+Mosh LoadBalancer Service

- [ ] **Step 1: Confirm `192.168.55.222` is free**

```bash
kubectl get svc -A -o jsonpath='{range .items[*]}{.status.loadBalancer.ingress[0].ip}{"\n"}{end}' \
  | sort -u | grep -F 192.168.55.222 \
  || echo "192.168.55.222 is free"
```

  If `paperclip-shell` (the in-flight neighbouring plan) has already taken `.222` instead of `.221`, allocate the next free IP and update this plan + the spec accordingly.

- [ ] **Step 2: Create `apps/ruflo/manifests/service-shell.yaml`**

```
BEGIN apps/ruflo/manifests/service-shell.yaml
apiVersion: v1
kind: Service
metadata:
  name: ruflo-shell
  namespace: ruflo-system
  annotations:
    lbipam.cilium.io/ips: 192.168.55.222
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: ruflo
    app.kubernetes.io/component: server
  ports:
    - { name: ssh, port: 22, targetPort: 2222, protocol: TCP }
    - { name: mosh-60016, port: 60016, protocol: UDP }
    - { name: mosh-60017, port: 60017, protocol: UDP }
    - { name: mosh-60018, port: 60018, protocol: UDP }
    - { name: mosh-60019, port: 60019, protocol: UDP }
    - { name: mosh-60020, port: 60020, protocol: UDP }
    - { name: mosh-60021, port: 60021, protocol: UDP }
    - { name: mosh-60022, port: 60022, protocol: UDP }
    - { name: mosh-60023, port: 60023, protocol: UDP }
    - { name: mosh-60024, port: 60024, protocol: UDP }
    - { name: mosh-60025, port: 60025, protocol: UDP }
    - { name: mosh-60026, port: 60026, protocol: UDP }
    - { name: mosh-60027, port: 60027, protocol: UDP }
    - { name: mosh-60028, port: 60028, protocol: UDP }
    - { name: mosh-60029, port: 60029, protocol: UDP }
    - { name: mosh-60030, port: 60030, protocol: UDP }
    - { name: mosh-60031, port: 60031, protocol: UDP }
END apps/ruflo/manifests/service-shell.yaml
```

### Task 7: Write the Deployment with both containers

- [ ] **Step 1: Investigate the ruvocal container's expected workspace path** (informational; locks the volumeMount paths)

  From Phase 1 Task 2's Dockerfile read, you already know the workspace path. If it's not `/workspace`, decide between:
  - **(a)** Mount the workspace PVC at the path ruvocal expects and accept asymmetry between containers (e.g., `/app/workspace` in ruvocal, `/workspace` in ruflo-shell) — confusing for the operator.
  - **(b)** Override ruvocal's expected path via env var if upstream supports it, mounting at `/workspace` in both. Strongly preferred.

  If neither is possible, document the asymmetric mount in Deployment Notes and update the spec's "shell `cd /workspace` matches ruvocal's view" success criterion.

- [ ] **Step 2: Create `apps/ruflo/manifests/deployment.yaml`** with both containers

```
BEGIN apps/ruflo/manifests/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ruflo
  namespace: ruflo-system
  labels:
    app.kubernetes.io/name: ruflo
    app.kubernetes.io/component: server
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: ruflo
      app.kubernetes.io/component: server
  template:
    metadata:
      labels:
        app.kubernetes.io/name: ruflo
        app.kubernetes.io/component: server
    spec:
      serviceAccountName: ruflo
      nodeSelector:
        zone: core
      securityContext:
        fsGroup: 1000
      shareProcessNamespace: true
      containers:
        - name: ruflo
          image: ghcr.io/derio-net/ruflo-server:<SHA-FROM-PHASE-1>
          imagePullPolicy: IfNotPresent
          env:
            - name: LITELLM_BASE_URL
              value: http://litellm.litellm-system:4000
            - name: MONGO_URL
              valueFrom:
                secretKeyRef: { name: ruflo-db-credentials, key: MONGO_URL }
          envFrom:
            - secretRef: { name: ruflo-openrouter, optional: false }
            - secretRef: { name: ruflo-resend, optional: false }
          ports:
            - { name: http, containerPort: 3000, protocol: TCP }
          volumeMounts:
            - { name: workspace, mountPath: /workspace }
          resources:
            requests: { cpu: 500m, memory: 1Gi }
            limits:   { cpu: "4",  memory: 8Gi }
          readinessProbe:
            httpGet: { path: /, port: 3000 }
            initialDelaySeconds: 15
            periodSeconds: 30
          livenessProbe:
            httpGet: { path: /, port: 3000 }
            initialDelaySeconds: 60
            periodSeconds: 60
        - name: ruflo-shell
          image: ghcr.io/derio-net/ruflo-shell:<SHA-FROM-PHASE-1>
          imagePullPolicy: IfNotPresent
          ports:
            - { name: ssh,         containerPort: 2222,  protocol: TCP }
            - { name: mosh-60016,  containerPort: 60016, protocol: UDP }
            - { name: mosh-60017,  containerPort: 60017, protocol: UDP }
            - { name: mosh-60018,  containerPort: 60018, protocol: UDP }
            - { name: mosh-60019,  containerPort: 60019, protocol: UDP }
            - { name: mosh-60020,  containerPort: 60020, protocol: UDP }
            - { name: mosh-60021,  containerPort: 60021, protocol: UDP }
            - { name: mosh-60022,  containerPort: 60022, protocol: UDP }
            - { name: mosh-60023,  containerPort: 60023, protocol: UDP }
            - { name: mosh-60024,  containerPort: 60024, protocol: UDP }
            - { name: mosh-60025,  containerPort: 60025, protocol: UDP }
            - { name: mosh-60026,  containerPort: 60026, protocol: UDP }
            - { name: mosh-60027,  containerPort: 60027, protocol: UDP }
            - { name: mosh-60028,  containerPort: 60028, protocol: UDP }
            - { name: mosh-60029,  containerPort: 60029, protocol: UDP }
            - { name: mosh-60030,  containerPort: 60030, protocol: UDP }
            - { name: mosh-60031,  containerPort: 60031, protocol: UDP }
          env:
            - { name: RUFLO_SHELL_USER,         value: agent }
            - { name: MOSH_SERVER_NETWORK_TMOUT, value: "3600" }
          envFrom:
            - secretRef: { name: ruflo-shell-alerts, optional: true }
          volumeMounts:
            - { name: shell-home,      mountPath: /home/agent }
            - { name: workspace,       mountPath: /workspace }
            - { name: shell-ssh-keys,  mountPath: /etc/ssh-keys, readOnly: true }
            - { name: shell-inventory, mountPath: /etc/ruflo-shell, readOnly: true }
          securityContext:
            runAsUser: 1000
            runAsGroup: 1000
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
          resources:
            requests: { cpu: 500m, memory: 1Gi }
            limits:   { cpu: "2",  memory: 4Gi }
          readinessProbe:
            tcpSocket: { port: 2222 }
            initialDelaySeconds: 10
            periodSeconds: 30
          livenessProbe:
            tcpSocket: { port: 2222 }
            initialDelaySeconds: 30
            periodSeconds: 60
      volumes:
        - name: workspace
          persistentVolumeClaim: { claimName: ruflo-workspace }
        - name: shell-home
          persistentVolumeClaim: { claimName: ruflo-shell-home }
        - name: shell-ssh-keys
          secret: { secretName: ruflo-shell-ssh-keys, defaultMode: 0400 }
        - name: shell-inventory
          configMap: { name: ruflo-shell-inventory }
END apps/ruflo/manifests/deployment.yaml
```

  Substitute `<SHA-FROM-PHASE-1>` with the actual SHA from Phase 1 Task 6. The `MONGO_URL` Secret key is produced by the `ruflo-db` sub-app's ESO (Phase 2 Task 2 Step 3) — confirm the key name matches what that ESO writes.

### Task 8: Add Application CRs to `apps/root/templates/`

- [ ] **Step 1: Create `apps/root/templates/ruflo-db.yaml`** — Application CR mirroring paperclip-db's; sync wave ordered before ruflo.

- [ ] **Step 2: Create `apps/root/templates/ruflo.yaml`** — Application CR mirroring paperclip's. Source path `apps/ruflo/manifests`, destination namespace `ruflo-system`. Include `ServerSideApply=true`, `prune: false`, `selfHeal: true`, and `ignoreDifferences` on Secret `/data` jsonPointer (per the standard pattern in `frank-argocd.md`).

### Task 9: Wire web UI to Traefik + Authentik

- [ ] **Step 1: Add IngressRoute to `apps/traefik/manifests/ingressroutes.yaml`**

  Append a new route for `ruflo.cluster.derio.net` referencing the `authentik-forwardauth` middleware and the `ruflo-web` Service in `ruflo-system`. Use an existing entry (e.g., the n8n-01 or paperclip web IngressRoute) as the literal template.

- [ ] **Step 2: Add proxy provider entry to `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml`**

  Follow the existing pattern: `forward_single` mode, include `invalidation_flow`, set `redirect_uris` to the list-of-objects shape. Name the provider `ruflo` and reference `https://ruflo.cluster.derio.net`.

### Task 10: Add the homepage tile

- [ ] **Step 1: Edit `apps/homepage/manifests/configmap-services.yaml`**

  Add a tile for ruflo under the existing "AI Agents" or "Orchestration" category (whichever paperclip lives in — match exactly). Fields: name, icon (look for a relevant Simple Icons / mdi icon; the homepage skill can help if invoked), category, description (one sentence), `href: https://ruflo.cluster.derio.net`.

### Task 11: Add operator client-setup files

- [ ] **Step 1: Create `apps/ruflo/client-setup/laptop/`** mirroring `apps/paperclip/client-setup/laptop/` (or `apps/secure-agent-pod/client-setup/laptop/`):

  - `ssh-config.snippet` — `Host ruflo` block with `HostName 192.168.55.222`, `Port 22`, `User agent`, `IdentityFile ~/.ssh/<your_private_key>`.
  - `mosh-wrapper.sh` — invokes `mosh --server="mosh-server new -p 60016:60031" agent@192.168.55.222`.
  - `README.md` — explains both, points at the secure-agent-pod README for shared identity rotation.

### Task 12: Open frank PR

- [ ] **Step 1: Open PR titled `feat(orch): add ruflo pod (manifests, ruflo-db sub-app, ingress, Authentik)`** with body linking to this plan and the spec. Note: the inventory ConfigMap is empty — Phase 4 populates it; the Authentik outpost provider assignment is a manual op in Phase 3.

- [ ] **Step 2: Wait for ArgoCD auto-sync after merge**

```bash
kubectl -n argocd get application ruflo-db -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'
kubectl -n argocd get application ruflo    -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'
# expect both: Synced Healthy
```

  If `ruflo` is `OutOfSync` waiting for `ruflo-db`, that's the intended sync ordering — give it a minute, then re-check.

---

## Phase 3: First-deploy validation [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/184 -->
**Depends on:** Phase 2

Confirms ruflo-db is healthy, both ruflo containers come up, the Authentik wiring is complete (after the manual outpost step), SSH/Mosh work from the laptop, and the Telegram alert path fires on induced failure.

### Task 1: ruflo-db health

- [ ] **Step 1: Mongo pod Ready, PVC bound**

```bash
kubectl -n ruflo-system get pod -l app.kubernetes.io/name=mongodb \
  -o jsonpath='{range .items[*]}{.metadata.name}: {.status.phase} ready={.status.containerStatuses[0].ready}{"\n"}{end}'
kubectl -n ruflo-system get pvc
```

- [ ] **Step 2: ruvocal can connect** — verify by reading the ruvocal container's logs once Phase 3 Task 2 confirms ruflo is up:

```bash
kubectl -n ruflo-system logs deploy/ruflo -c ruflo | grep -iE 'mongo|connect|ready|listen' | head -20
```

  Expect a successful mongo connection log line and a "listening on 3000" or equivalent.

### Task 2: ruflo pod-level health

- [ ] **Step 1: Both containers Ready**

```bash
kubectl -n ruflo-system get pod -l app.kubernetes.io/name=ruflo \
  -o jsonpath='{range .items[0].status.containerStatuses[*]}{.name}: ready={.ready} restarts={.restartCount}{"\n"}{end}'
# expect both 'ruflo' and 'ruflo-shell' with ready=true
```

- [ ] **Step 2: Confirm shareProcessNamespace works**

```bash
kubectl -n ruflo-system exec -c ruflo-shell deploy/ruflo -- ps -ef | grep -E 'node|sshd' | head -10
# expect to see ruvocal's node process AND sshd
```

- [ ] **Step 3: Confirm `/workspace` is shared and writable from both containers**

```bash
kubectl -n ruflo-system exec -c ruflo-shell deploy/ruflo -- touch /workspace/.shell-write-test
kubectl -n ruflo-system exec -c ruflo        deploy/ruflo -- ls -la /workspace/.shell-write-test
kubectl -n ruflo-system exec -c ruflo-shell deploy/ruflo -- rm /workspace/.shell-write-test
```

  If permission denied, escalate to a UID/GID investigation: ruvocal's image (Phase 1 Task 3) was built with `useradd -u 1000`, so `fsGroup: 1000` should make this work. If not, document in Deployment Notes and decide between (a) initContainer chowning `/workspace`, (b) overriding ruvocal's `runAsUser` if upstream supports it.

### Task 3: Authentik outpost provider assignment (manual)

```yaml
# manual-operation
id: ruflo-authentik-outpost-assign
layer: orch
app: ruflo
plan: docs/superpowers/plans/2026-05-02--orch--ruflo-pod.md
when: after Phase 2 ArgoCD sync makes the 'ruflo' proxy provider exist; before browser SSO will work
why_manual: Authentik blueprints cannot manage outpost provider assignments without replacing existing assignments — must add via Django ORM
commands:
  - description: Add ruflo proxy provider to the embedded outpost
    command: |
      kubectl exec -n authentik deploy/authentik-server -- python -c "
      import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','authentik.root.settings')
      import django; django.setup()
      from authentik.providers.proxy.models import ProxyProvider
      from authentik.outposts.models import Outpost
      outpost = Outpost.objects.get(name='authentik Embedded Outpost')
      provider = ProxyProvider.objects.get(name='ruflo')
      outpost.providers.add(provider)
      print(f'Added {provider.name} to {outpost.name}')
      "
verify:
  - description: 'ruflo' is now in the embedded outpost's provider list
    command: |
      kubectl exec -n authentik deploy/authentik-server -- python -c "
      import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','authentik.root.settings')
      import django; django.setup()
      from authentik.outposts.models import Outpost
      o = Outpost.objects.get(name='authentik Embedded Outpost')
      print([p.name for p in o.providers.all()])
      " | grep -q ruflo && echo OK
status: pending
```

- [ ] **Step 1: Run the Django ORM command** above to add the ruflo proxy provider to the embedded outpost.

- [ ] **Step 2: Verify the outpost provider list includes `ruflo`** via the verify command.

### Task 4: Web UI loads through Authentik SSO

- [ ] **Step 1: Curl confirms Authentik intercepts unauthenticated requests**

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' -L --max-redirs 0 https://ruflo.cluster.derio.net/
# expect 302 redirect to authentik (or 401 from forward-auth middleware before redirect)
```

- [ ] **Step 2: Browser SSO and confirm ruvocal UI loads**

  In a browser on a laptop with Authentik session cookies (or fresh login flow): open `https://ruflo.cluster.derio.net/`. Expect: redirect → Authentik login → redirect back → ruvocal UI renders (dashboard / hive list / blank state).

  If the page loads but assets 404 or the API fails, capture the failing URL and check whether ruvocal expects to be served from `/` or from a subpath. May require `Headers` middleware tweaks in the Traefik IngressRoute.

### Task 5: SSH connectivity from operator laptop

- [ ] **Step 1: Service has the LB IP**

```bash
kubectl -n ruflo-system get svc ruflo-shell -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
# expect: 192.168.55.222
```

- [ ] **Step 2: SSH connects and lands in /home/agent**

```bash
ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/<your_private_key> agent@192.168.55.222 \
  'whoami; hostname; cat /etc/os-release | head -3; ls -la ~; echo $LITELLM_BASE_URL'
# expect: whoami=agent, /home/agent populated from /etc/skel, LITELLM_BASE_URL exported
```

- [ ] **Step 3: `claude` is on PATH** (Layer-1 baked-in)

```bash
ssh agent@192.168.55.222 -- 'command -v claude; claude --version'
```

- [ ] **Step 4: `cd /workspace` shows ruvocal's view**

```bash
ssh agent@192.168.55.222 -- 'ls -la /workspace'
```

  Should match what `kubectl exec -c ruflo deploy/ruflo -- ls -la /workspace` shows (in Phase 3 Task 2).

- [ ] **Step 5: Mosh connects**

```bash
mosh agent@192.168.55.222 -- echo 'mosh ok'
# expect 'mosh ok' over UDP
```

- [ ] **Step 6: tmux session persists across reattach**

```bash
ssh agent@192.168.55.222 -- tmux new-session -d -s test 'sleep 600'
ssh agent@192.168.55.222 -- tmux ls
ssh agent@192.168.55.222 -- tmux kill-session -t test
```

### Task 6: MOTD shows last-reconcile summary

- [ ] **Step 1: Fresh login banner**

  SSH in interactively (no `--` command). Expect to see:
  - The ruflo-shell banner from `/etc/skel/.bashrc-ruflo` (the workspace/home/reconcile reminder).
  - The MOTD line `✓ ruflo-shell: 0 installed, 0 already present, 0 removed @ 2026-05-…` from the empty-inventory installer.

  If the MOTD line is missing, check whether `agent-shell-base`'s sshd config enables `pam_motd` and the dynamic motd plumbing — log as a follow-up against Phase 1 rather than blocking here.

### Task 7: Telegram alert path (induced failure)

- [ ] **Step 1: Add a known-bad entry to the inventory**

  Edit `apps/ruflo/manifests/configmap-shell-inventory.yaml`:

```yaml
data:
  inventory.yaml: |
    npm-global:
      - "@anthropic-ai/this-package-does-not-exist-XXXX"
    # other sections unchanged (still empty)
```

  Commit, push, ArgoCD syncs.

- [ ] **Step 2: Run reconcile**

```bash
ssh agent@192.168.55.222 -- ruflo-shell-reconcile
```

- [ ] **Step 3: Verify Telegram alert arrived** in the configured chat with format `⚠ ruflo-shell: 1 install(s) failed on boot`.

- [ ] **Step 4: Verify MOTD shows the failure** on next SSH login.

- [ ] **Step 5: Revert the inventory change** — remove the bogus entry, commit, push, run reconcile again. MOTD should flip to the success line. No Telegram message expected on success.

### Task 8: Confirm zero direct frontier-LLM traffic from the pod

- [ ] **Step 1: From inside the ruflo container, confirm there's no `ANTHROPIC_API_KEY`**

```bash
kubectl -n ruflo-system exec -c ruflo deploy/ruflo -- env | grep -iE 'anthropic|openai|gemini' || echo "none — good"
# expect "none" — only OPENROUTER_API_KEY, EMAIL_RESEND_API_KEY, LITELLM_BASE_URL, MONGO_URL should be present
```

- [ ] **Step 2: Confirm LiteLLM is reachable**

```bash
kubectl -n ruflo-system exec -c ruflo deploy/ruflo -- curl -fsS http://litellm.litellm-system:4000/health
```

- [ ] **Step 3: Confirm OpenRouter is reachable** (without exposing the key in logs)

```bash
kubectl -n ruflo-system exec -c ruflo deploy/ruflo -- bash -c 'curl -fsS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/models'
# expect 200
```

  Egress restriction is intentionally not in scope — wide egress is required for swarm runs. This step confirms the gateway endpoints work, not that everything else is locked down.

---

## Phase 4: Populate inventory and verify reconcile [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/185 -->
**Depends on:** Phase 3

Move from "the wiring works" to "the operator's day-to-day toolset is installed." `claude-flow` is the headliner — that's the actual reason this pod exists.

### Task 1: Curate initial inventory

- [ ] **Step 1: Edit `apps/ruflo/manifests/configmap-shell-inventory.yaml`** to declare the operator's expected toolset. Suggested starting set (refine after a discovery week):

```yaml
data:
  inventory.yaml: |
    mise:
      - python@3.12
      - node@20
      - rust@stable
    npm-global:
      - "claude-flow@alpha"
      - "@openai/codex"
    pipx:
      - black
      - ruff
    cargo:
      - ripgrep
      - eza
    removed:
      mise: []
      npm-global: []
      pipx: []
      cargo: []
```

  Commit and push. ArgoCD syncs the ConfigMap.

  *Note on `claude-flow@alpha`:* the upstream package name is the npm tag for ruflo's CLI ([myaiguide.co/repos/ruflo](https://myaiguide.co/repos/ruflo)). Verify the exact package name during Phase 1 Task 2's upstream Dockerfile read — if upstream now publishes under `ruflo` directly, use that name instead.

### Task 2: Run reconcile and verify

- [ ] **Step 1:**

```bash
ssh agent@192.168.55.222 -- ruflo-shell-reconcile
```

  Expect log lines for each tool, ending with `summary: installed=N already=0 removed=0 failed=0`.

- [ ] **Step 2: Verify each manager reports the tool present**

```bash
ssh agent@192.168.55.222 -- bash -lc '
  mise ls
  npm ls -g --depth=0 | grep -E "claude-flow|codex|claude-code"
  pipx list --short
  cargo install --list
'
```

- [ ] **Step 3: Confirm `claude-flow` (or `ruflo`) CLI works against the running ruvocal**

```bash
ssh agent@192.168.55.222 -- 'claude-flow --version || ruflo --version'
ssh agent@192.168.55.222 -- 'claude-flow status || ruflo status'   # whatever the canonical "is it talking to my ruvocal?" command is
```

  Document the canonical health-check command in Deployment Notes for future operating-post reference.

### Task 3: Persistence test across pod restart

- [ ] **Step 1: Force a pod bounce**

```bash
kubectl -n ruflo-system rollout restart deploy/ruflo
kubectl -n ruflo-system rollout status deploy/ruflo --timeout=120s
```

- [ ] **Step 2: Reconnect and verify everything still present**

```bash
ssh agent@192.168.55.222 -- bash -lc '
  cargo install --list | grep -E "ripgrep|eza"
  pipx list --short
  ls ~/.cargo/bin
  ls /workspace
'
# expect: tools present on PV; /workspace files unchanged; ruvocal still serving the UI
```

  Confirm MOTD on this fresh login reads `installed=0 already=N removed=0 failed=0` — proves the installer ran on boot and committed no work.

- [ ] **Step 3: Confirm ruvocal Mongo state survived** — open the web UI, the previously-created hive(s)/runs (if any) should still be there.

### Task 4: Interactive install drift test

- [ ] **Step 1: Manually install something not in the inventory**

```bash
ssh agent@192.168.55.222 -- cargo install fd-find
```

- [ ] **Step 2: Confirm it persists across pod bounce** (same restart + reconnect flow). Demonstrates Layer-3 escape hatch works.

- [ ] **Step 3: Document the drift policy** in this plan's *Deployment Notes*: interactive installs are intentional during discovery; promote to inventory ConfigMap if you want survival across PV migrations or to share with the next operator.

---

## Phase 5: Documentation [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/186 -->
**Depends on:** Phase 4

This is a **new layer** (sibling to Paperclip in `orch`), so it gets new building + operating blog posts and a roadmap update — not appendices to existing posts.

### Task 1: Update CLAUDE.md rules

- [ ] **Step 1: Update `.claude/rules/frank-infrastructure.md`** Frank Cluster Services table

```
| Ruflo Web UI            | (via Traefik)  | IngressRoute (ruflo.cluster.derio.net)             |
| Ruflo Shell (SSH+Mosh)  | 192.168.55.222 | Cilium L2 LoadBalancer (port 22/SSH, UDP 60016-60031/Mosh) |
```

- [ ] **Step 2: Add gotchas to `.claude/rules/frank-gotchas.md`** — only patterns that actually surfaced during Phases 1–4. Possible candidates (verify each was actually hit):
  - ruvocal's exact `MONGO_URL` env-var name and any quirks getting `INCLUDE_DB=false` to behave
  - Workspace-path mismatch handling between containers, if encountered
  - Traefik subpath/headers handling for ruvocal SPA, if needed
  - Any UID/GID surprises from the ruvocal container

### Task 2: Write the building blog post

- [ ] **Step 1: Run `/blog-post`** to scaffold `blog/content/docs/building/<NN>-ruflo/index.md`. Choose `<NN>` so it follows the most recently published `building/` post in numeric order.

- [ ] **Step 2: Write the post.** Suggested narrative:
  - The why: Paperclip is structured org-chart orchestration; ruflo is the chaotic-swarm counterpoint. Frank's "let competing paradigms decide via the work" continues.
  - The shape: hybrid pod (ruvocal + shell sidecar), separate Mongo sub-app, single LoadBalancer for SSH+Mosh, Traefik+Authentik for the web UI.
  - The reuse: shell sidecar is the second instance of the agent-shell-base + inventory-ConfigMap pattern; what changed and what stayed identical.
  - The principle: zero direct frontier-LLM keys in the pod; LiteLLM gateway as the kill switch; OpenRouter as the deliberate escape hatch.
  - The gotchas (whatever surfaced).

- [ ] **Step 3: Update series index** `blog/content/docs/building/00-overview/index.md` — add ruflo to the Series Index and Capability Map.

- [ ] **Step 4: Update roadmap shortcode** `blog/layouts/shortcodes/cluster-roadmap.html` — add the new layer entry.

### Task 3: Write the operating blog post

- [ ] **Step 1: Run `/blog-post`** to scaffold `blog/content/docs/operating/<NN>-ruflo/index.md`.

- [ ] **Step 2: Write the post.** Sections:
  - Connecting (laptop `~/.ssh/config` snippet, mosh wrapper, accessing the web UI)
  - Adding/removing tools (ConfigMap edit flow vs interactive `mise install` / `cargo install`)
  - Reading the install log / interpreting the Telegram alert
  - When to bump `ruflo-shell` image vs add to inventory
  - When to bump `ruflo-server` image (pinning to a new ruvnet/ruflo upstream SHA)
  - Backup and recovery (Longhorn snapshot policy on the three PVCs; how to restore)
  - Rough swarm-run cookbook: a worked example of running an actual `claude-flow orchestrate` against the running ruvocal — minimum pieces an operator needs

- [ ] **Step 3: Update operating series index** in `blog/content/docs/building/00-overview/index.md`.

### Task 4: Run `/update-readme`

- [ ] **Step 1:** Run the skill. Verify:
  - Service Access table includes `192.168.55.222` and `ruflo.cluster.derio.net`.
  - Repository Structure section reflects the new `apps/ruflo/` and `apps/ruflo-db/` directories.
  - Current Status reflects the new layer.

### Task 5: Sync runbook

- [ ] **Step 1: Run `/sync-runbook`.** This plan introduces two manual-operation blocks (Infisical bootstrap in Phase 2 Task 1, Authentik outpost assignment in Phase 3 Task 3). The skill picks them up and merges into `docs/runbooks/manual-operations.yaml`.

### Task 6: Update plan status

- [ ] **Step 1:** Set `**Status:** Deployed` at the top of this plan.

---

## Phase 6: Post-Deploy Checklist [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/187 -->
**Depends on:** Phase 5

Confirms each canonical step happened or was rationally skipped.

- [ ] **Step 1: Expose externally** — done in Phase 2 Task 9 (Traefik IngressRoute) and Phase 2 Task 10 (homepage tile). Confirm by opening the homepage at `https://master.cluster.derio.net` and clicking the ruflo tile.
- [ ] **Step 2: Building blog post** — done in Phase 5 Task 2. Confirm post is published and series index updated.
- [ ] **Step 3: Operating blog post** — done in Phase 5 Task 3. Confirm post is published and operating series index updated.
- [ ] **Step 4: Update README** — done in Phase 5 Task 4. Confirm.
- [ ] **Step 5: Sync runbook** — done in Phase 5 Task 5. Confirm `docs/runbooks/manual-operations.yaml` contains both `ruflo-infisical-bootstrap` and `ruflo-authentik-outpost-assign` entries.
- [ ] **Step 6: Update plan status** — done in Phase 5 Task 6. Confirm `**Status:** Deployed`.

---

## Deployment Notes

*(Populated as phases run. Each row records the date, phase, and the concrete value or decision recorded at that step.)*

| Date | Phase | Note |
|------|-------|------|
| 2026-05-02 | P1.T1 | `agent-shell-base` confirmed: defaults `AGENT_USER=agent`, `AGENT_HOME=/home/agent`, UID/GID 1000, sshd port 2222, MOTD via `/etc/profile.d` (UsePAM=no). `chown -R /run /var/run` to agent UID present (line 70). `#!/command/with-contenv bash` shebang convention confirmed in `40-skel`. agent-base already installs `@anthropic-ai/claude-code` globally — ruflo-shell's npm install -g of it is a redundant pin/upgrade, kept to make intent explicit. |
| 2026-05-02 | P1.T2 | Upstream pinned: `ruvnet/ruflo` SHA `9b169814849b75bdee4b75e7d3d85a0db567802d`. Path correction: Dockerfile is at `ruflo/src/ruvocal/Dockerfile` (one extra `ruflo/` prefix vs the plan). Base `node:24-slim`, builder `node:24`, port `3000` hardcoded in `entrypoint.sh`. `INCLUDE_DB=false` is honored cleanly via multi-stage `local_db_${INCLUDE_DB}` selector. **Major spec deviation: ruvocal now uses PostgreSQL** via `DATABASE_URL` and OpenAI-compatible inference via `OPENAI_BASE_URL` (LiteLLM-compatible). MongoDB env vars are explicitly tagged "Legacy MongoDB vars (unused — kept for reference)" in upstream `.env`. **Phase 2 must replace `apps/ruflo-db/` Mongo plan with Postgres** (e.g., CloudNativePG cluster) and inject `DATABASE_URL` instead of `MONGO_URL`. Phase 1 image build is unaffected. |
| 2026-05-02 | P1.T2 | **Build path decision: option (b) thin-wrapper.** Our Dockerfile clones upstream at the pinned SHA in an `alpine/git` `source` stage, builds in a `node:24` `builder` stage matching upstream, and assembles a `node:24-slim` `runtime` stage that omits the `local_db_true` Mongo install layer. Justification: option (a) (`FROM ruvocal:built`) requires CI to first build upstream's Dockerfile and then ours, harder to express in `docker/build-push-action`. The wrapper is self-contained and pin-stable. |
| 2026-05-02 | P1.T4 | `/etc/skel/.bashrc-ruflo` approach replaced with `/etc/profile.d/60-ruflo-shell-banner.sh` to match the existing 40-paths / 50-motd profile.d pattern in paperclip-shell. Same effect (banner + LITELLM_BASE_URL default), idiomatic for sshd UsePAM=no setup. |
| 2026-05-02 | P1 | PR branch based on `feat/paperclip-shell` (PR derio-net/agent-images#46) so the ruflo-shell rootfs can ship alongside paperclip-shell without merge conflicts on `.github/workflows/build.yaml`. After PR #46 merges, this PR rebases cleanly onto main. |
