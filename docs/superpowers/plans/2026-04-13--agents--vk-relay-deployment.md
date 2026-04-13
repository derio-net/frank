# VK Relay Deployment Implementation Plan

> **For VK agents:** Use vk-execute to implement assigned phases.
> **For local execution:** Use subagent-driven-development or executing-plans.
> **For dispatch:** Use vk-dispatch to create Issues from this plan.

**Spec:** `docs/superpowers/specs/2026-04-13--agents--vk-relay-self-host-design.md`
**Status:** Not Started

**Goal:** Deploy the VK relay server as a sidecar in the vk-remote pod and configure the secure-agent-pod to connect to it, enabling the remote web UI to proxy API calls to the local VK server.
**Architecture:** Add relay sidecar to vk-remote deployment (same image, different entrypoint), split IngressRoute for relay paths, add `VK_SHARED_RELAY_API_BASE` to secure-agent-pod.
**Tech Stack:** Kubernetes manifests, Traefik IngressRoute, ArgoCD

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `apps/vk-remote/manifests/deployment.yaml` | Modify | Add relay sidecar container |
| `apps/vk-remote/manifests/service.yaml` | Create | Service with both ports (8081 + 8082) |
| `apps/traefik/manifests/ingressroutes.yaml` | Modify | Split VK route for relay paths |
| `apps/secure-agent-pod/manifests/deployment.yaml` | Modify | Add VK_SHARED_RELAY_API_BASE env var |

---

## Phase 0: Manifests [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/50 -->

### Task 1: Add relay sidecar to vk-remote deployment

**Files:**
- Modify: `apps/vk-remote/manifests/deployment.yaml`

- [ ] **Step 1: Add relay-server container**

Add a second container to the pod spec, after the existing `vk-remote` container:

```yaml
        - name: relay-server
          image: ghcr.io/derio-net/vk-remote:<IMAGE_SHA>
          command: ["/usr/local/bin/relay-server"]
          ports:
            - containerPort: 8082
              protocol: TCP
          env:
            - name: RELAY_LISTEN_ADDR
              value: "0.0.0.0:8082"
            - name: VIBEKANBAN_REMOTE_JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: VIBEKANBAN_REMOTE_JWT_SECRET
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: vk-remote-secrets
                  key: POSTGRES_PASSWORD
            - name: SERVER_DATABASE_URL
              value: "postgresql://remote:$(POSTGRES_PASSWORD)@postgres-vk:5432/remote?sslmode=disable"
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
          readinessProbe:
            tcpSocket:
              port: 8082
            initialDelaySeconds: 5
            periodSeconds: 15
          livenessProbe:
            tcpSocket:
              port: 8082
            initialDelaySeconds: 10
            periodSeconds: 30
```

Use the same image tag as the vk-remote container. Replace `<IMAGE_SHA>` with the SHA from the vibe-kanban plan's Phase 0 Task 3.

- [ ] **Step 2: Commit**

```bash
git add apps/vk-remote/manifests/deployment.yaml
git commit -m "feat(agents): add relay-server sidecar to vk-remote pod"
```

### Task 2: Create service with relay port

**Files:**
- Modify: `apps/vk-remote/manifests/deployment.yaml` (the Service is in the same file)

- [ ] **Step 1: Add relay port to the existing Service**

The Service definition is at the bottom of `deployment.yaml`. Add port 8082:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: vk-remote
  namespace: agents
spec:
  selector:
    app: vk-remote
  ports:
    - name: http
      port: 8081
      targetPort: 8081
    - name: relay
      port: 8082
      targetPort: 8082
```

- [ ] **Step 2: Commit**

```bash
git add apps/vk-remote/manifests/deployment.yaml
git commit -m "feat(agents): add relay port to vk-remote service"
```

### Task 3: Split IngressRoute for relay paths

**Files:**
- Modify: `apps/traefik/manifests/ingressroutes.yaml`

- [ ] **Step 1: Replace the existing vk-remote IngressRoute with two rules**

Find the existing VK IngressRoute block:

```yaml
    - match: Host(`vk.cluster.derio.net`)
      kind: Rule
      middlewares:
        - name: ip-allowlist
        - name: security-headers
      services:
        - name: vk-remote
          namespace: agents
          port: 8081
```

Replace with two rules:

```yaml
    - match: Host(`vk.cluster.derio.net`) && PathPrefix(`/v1/relay`)
      kind: Rule
      middlewares:
        - name: ip-allowlist
        - name: security-headers
      services:
        - name: vk-remote
          namespace: agents
          port: 8082
    - match: Host(`vk.cluster.derio.net`)
      kind: Rule
      middlewares:
        - name: ip-allowlist
        - name: security-headers
      services:
        - name: vk-remote
          namespace: agents
          port: 8081
```

The relay rule must come first — Traefik evaluates rules in order and the more specific PathPrefix match needs priority.

- [ ] **Step 2: Commit**

```bash
git add apps/traefik/manifests/ingressroutes.yaml
git commit -m "feat(agents): split vk IngressRoute for relay paths"
```

### Task 4: Add VK_SHARED_RELAY_API_BASE to secure-agent-pod

**Files:**
- Modify: `apps/secure-agent-pod/manifests/deployment.yaml`

- [ ] **Step 1: Add the env var**

In the kali container's `env` section, after `VK_SHARED_API_BASE`, add:

```yaml
            - name: VK_SHARED_RELAY_API_BASE
              value: "https://vk.cluster.derio.net"
```

- [ ] **Step 2: Commit**

```bash
git add apps/secure-agent-pod/manifests/deployment.yaml
git commit -m "feat(agents): add VK_SHARED_RELAY_API_BASE for relay connection"
```

### Task 5: Commit all and push

- [ ] **Step 1: Push to trigger ArgoCD sync**

```bash
git push origin main
```

---

## Phase 1: Deploy & Verify [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/51 -->

### Task 1: Verify ArgoCD sync

- [ ] **Step 1: Check vk-remote pod has two containers**

```bash
kubectl -n agents get pods -l app=vk-remote -o jsonpath='{.items[0].spec.containers[*].name}'
```

Expected: `vk-remote relay-server`

- [ ] **Step 2: Check relay-server container is running**

```bash
kubectl -n agents logs deploy/vk-remote -c relay-server --tail=10
```

Expected: `Relay server listening on 0.0.0.0:8082`

- [ ] **Step 3: Verify relay endpoint is reachable through Traefik**

```bash
curl -s -o /dev/null -w "%{http_code}" https://vk.cluster.derio.net/v1/relay/connect
```

Expected: 401 (Unauthorized — no token, but endpoint exists and routes correctly)

### Task 2: Verify local server connects to relay

- [ ] **Step 1: Check secure-agent-pod logs for relay registration**

```bash
kubectl -n secure-agent-pod logs deploy/secure-agent-pod -c kali --tail=50 | grep -i relay
```

Expected: Log line indicating relay client connected or host registered.

- [ ] **Step 2: Verify host appears in VK remote UI**

Open `https://vk.cluster.derio.net` in the browser. The local host should appear (possibly as "unpaired").

### Task 3: Pair browser with local server (one-time)

- [ ] **Step 1: Port-forward to the local VK server**

```bash
kubectl -n secure-agent-pod port-forward deploy/secure-agent-pod 8081:8081
```

- [ ] **Step 2: Generate pairing code**

Open `http://localhost:8081` in the browser. Go to Settings → Relay Settings → "Generate pairing code". Note the 6-digit code.

- [ ] **Step 3: Enter code in remote UI**

Open `https://vk.cluster.derio.net`. Go to Settings → "Pair host". Enter the 6-digit code.

Expected: Pairing completes, host status changes to "online".

- [ ] **Step 4: Verify workspace repos are visible**

Click into an active workspace in the remote UI.

Expected: Repos, sessions, and workspace details are now visible (proxied via relay from the local server).

- [ ] **Step 5: Stop the port-forward**

The port-forward is no longer needed — the relay handles all communication going forward.

---

## Phase 2: Post-Deploy Checklist [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/52 -->

- [ ] **Step 1: Write building blog post** — Use `/blog-post` skill. Update series index in `blog/content/building/00-overview/index.md` and cluster roadmap in `blog/layouts/shortcodes/cluster-roadmap.html`
- [ ] **Step 2: Write operating blog post** — Use `/blog-post` skill for the companion operating guide. Update operating series index in `blog/content/building/00-overview/index.md`
- [ ] **Step 3: Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status
- [ ] **Step 4: Sync runbook** — Run `/sync-runbook` if the plan contains any `# manual-operation` blocks
- [ ] **Step 5: Update plan status** — Set `**Status:**` to `Deployed`
