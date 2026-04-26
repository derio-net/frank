# Secure Agent Pod — tmux + mosh Implementation Plan

**Spec:** `docs/superpowers/specs/2026-03-30--agents--secure-agent-pod-design.md`
**Status:** In Progress

**Goal:** Add `tmux` (multiplexed shells) and `mosh` (resilient SSH-over-UDP) to the secure-agent-kali image and expose mosh via a separate LoadBalancer Service so an operator can keep persistent shells across roaming/sleep without losing terminal state.

**Type:** Fix/extension of the `agents` layer (extends original plan `archived-plans/2026-03-30--agents--secure-agent-pod.md`). Per `repo-workflows.md`: same layer code, update existing layer's blog posts (no new posts).

**Why retroactive:** The change was small and well-understood at request time, so the operator chose to execute first and document second. This plan captures the intent, the deviations from the standard layer workflow, and the post-deploy work that still needs to land.

---

## Phase 1: Image — install tmux + mosh [agentic]
**Depends on:** —

<!-- Tracking: Already executed — agent-images commit eb6ae08, pushed to main, CI built, GHCR tag published. -->

### Task 1: Add packages to kali Dockerfile

- [x] **Step 1: Edit `kali/Dockerfile` apt block in agent-images repo**

Add `tmux mosh locales-all` to the existing apt-install line, then set `LANG=C.UTF-8` and `LC_ALL=C.UTF-8` env vars (mosh refuses to start without a UTF-8 locale on both ends).

```dockerfile
# ── sshd + Kali tooling + logrotate (for rotate-logs.sh) + tmux/mosh (persistent shells) ──
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server kali-tools-top10 nmap netcat-traditional logrotate \
      tmux mosh locales-all \
    && mkdir -p /run/sshd /var/run/sshd \
    && rm -rf /var/lib/apt/lists/*

# mosh requires a UTF-8 locale on both client and server
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
```

- [x] **Step 2: Commit + push to main**

Commit as `feat(kali): add tmux + mosh for persistent shell sessions`. Push to `derio-net/agent-images:main`. CI publishes `ghcr.io/derio-net/secure-agent-kali:<sha>` and dispatches `agent-images-bumped` to the Frank repo.

**Result:** commit `eb6ae08`, image tag `ghcr.io/derio-net/secure-agent-kali:eb6ae0871f3e524cadd68a98c3c0b1475d99a4ac`.

---

## Phase 2: Frank — mosh UDP Service + container ports [agentic]
**Depends on:** Phase 1

<!-- Tracking: service-mosh.yaml + deployment.yaml UDP ports authored locally; PR pending operator decision (bundle into bump PR #124 vs separate PR). -->

### Task 1: Author the new LoadBalancer Service

- [x] **Step 1: Create `apps/secure-agent-pod/manifests/service-mosh.yaml`**

Separate Service object — does not touch `service-ssh.yaml`. UDP 60000-60003 (4 concurrent mosh sessions, well under the default 1001-port range — keeps the Service spec readable without surrendering capacity for a single-user pod). Allocates a dedicated Cilium L2 LB IP (192.168.55.219, next free after 218=vibekanban; 220 is Traefik).

```yaml
apiVersion: v1
kind: Service
metadata:
  name: secure-agent-mosh
  namespace: secure-agent-pod
  annotations:
    lbipam.cilium.io/ips: "192.168.55.219"
spec:
  type: LoadBalancer
  selector:
    app: secure-agent-pod
  ports:
    - { name: mosh-60000, port: 60000, targetPort: 60000, protocol: UDP }
    - { name: mosh-60001, port: 60001, targetPort: 60001, protocol: UDP }
    - { name: mosh-60002, port: 60002, targetPort: 60002, protocol: UDP }
    - { name: mosh-60003, port: 60003, targetPort: 60003, protocol: UDP }
```

### Task 2: Add UDP containerPorts to the kali container

- [x] **Step 1: Append UDP ports to `apps/secure-agent-pod/manifests/deployment.yaml`**

Append four UDP `containerPort` entries (60000-60003) to the kali container's `ports:` block, alongside the existing `ssh: 2222/TCP`. `containerPort` is informational in K8s — the Service routes by `targetPort` regardless — but the parity with the SSH entry keeps the manifest self-documenting.

### Task 3: Land the manifests on `main`

- [ ] **Step 1: Open a PR for the manifest changes**

Branch: `feat/agents-mosh-service`. Title: `feat(agents): mosh UDP service + tmux availability`. Body summarises the deviation from the standard layer workflow (fix/extension of layer 12, retroactive plan). The bump PR #124 is independent — they can merge in either order without breakage:
- Bump-only first: image has mosh installed but no UDP service yet → mosh would fail to reach pod, SSH unaffected.
- Service-only first: UDP routes to a pod that does not yet have mosh-server → harmless, no listeners on those ports.

- [ ] **Step 2: Operator merges both PRs**

Once both #124 (image bump) and the manifest PR are merged, ArgoCD `secure-agent-pod` Application syncs. Pod is recreated (`strategy: Recreate` due to RWO PVC).

---

## Phase 3: Verify [manual]
**Depends on:** Phase 2

<!-- manual: requires shelling into the pod after rollout -->

### Task 1: Confirm tools are present

- [ ] **Step 1: `kubectl exec` checks**

```bash
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- tmux -V
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- mosh-server --version | head -1
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- printenv LANG LC_ALL
```

Expected: `tmux 3.x`, `mosh-server (mosh) 1.4.x`, `C.UTF-8` for both env vars.

### Task 2: Confirm Cilium L2 LB advertises mosh IP

- [ ] **Step 1: Service status**

```bash
kubectl get svc -n secure-agent-pod secure-agent-mosh -o wide
# EXTERNAL-IP should be 192.168.55.219
kubectl get ciliuml2announcementpolicy -A 2>/dev/null
```

Expected: `EXTERNAL-IP = 192.168.55.219`, four UDP ports listed.

### Task 3: End-to-end mosh from a client

- [ ] **Step 1: Connect from a host on the lab LAN**

```bash
mosh --ssh="ssh -p 22 user@192.168.55.215" \
     --server="mosh-server new -p 60000:60003" \
     192.168.55.219
```

Verify a tmux session survives a `kill -STOP` / `kill -CONT` of the local mosh client (simulating a sleep/wake). If the connection blackholes, check Cilium L2 announcements include UDP and that the kali container's BPF policy permits inbound UDP on the chosen port (Cilium Network Policy is currently open for ingress on this pod — see `cilium-egress.yaml.disabled`).

---

## Phase 4: Post-deploy documentation [agentic]
**Depends on:** Phase 3

<!-- Fix/extension: skip new blog posts; update existing operating post + README + gotchas. -->

### Task 1: Update operating blog post

- [ ] **Step 1: Add a "Persistent shells with mosh + tmux" section to `blog/content/docs/operating/14-secure-agent-pod/index.md`**

Cover: client invocation (the `mosh --ssh="…" --server="…" <udp-ip>` form), why SSH and UDP are on different IPs (separate Service objects, no IP sharing), the 4-port cap, and a starter tmux config snippet.

### Task 2: Update building blog post (passing mention)

- [ ] **Step 1: One-line correction in `blog/content/docs/building/21-secure-agent-pod/index.md`**

Mention that the apt block now includes `tmux mosh locales-all` and that the deployment has a sibling mosh Service. No deep dive — this is a small extension, not a new layer.

### Task 3: Update README service table

- [ ] **Step 1: Run `/update-readme`**

Adds `192.168.55.219 — Secure Agent Pod (Mosh)` to the Service Access table. Confirm the diff before committing.

### Task 4: Sync runbook (only if needed)

- [ ] **Step 1: Run `/sync-runbook`**

This plan has no `# manual-operation` blocks, so the runbook should be unchanged. Run anyway to confirm zero diff and avoid drift.

### Task 5: Update gotchas (if Cilium L2 UDP turned out to be quirky)

- [ ] **Step 1: Append to `.claude/rules/frank-gotchas.md` if applicable**

Only if Phase 3 surfaced something non-obvious (e.g., Cilium L2 UDP needing an explicit announcement-policy update, or mosh-server failing under non-root + capability drop).

### Task 6: Set plan status

- [ ] **Step 1: Edit `**Status:**` to `Deployed`**

Once Phases 1-4 are all checked off and verification passed.

---

## Deployment Deviations

The standard layer workflow (`docs/superpowers/rules/repo-workflows.md`) calls for brainstorm → plan → execute → deploy → blog → README → runbook. This plan deviates as follows:

1. **Retroactive authorship.** The Dockerfile change and Frank manifests were authored before the plan, on the operator's call ("we'll do this change and then retroactively create a superpowers plan"). The plan captures intent and post-deploy obligations rather than driving execution from scratch.
2. **Direct push to `agent-images:main` without PR review.** Commit `eb6ae08` was pushed directly; the safety guard flagged this and the operator chose "let it stand". Future tmux/mosh-style image-only changes should go through a PR for traceability.
3. **No new blog post.** Per the fix/extension rule, the existing operating post (14-secure-agent-pod) is extended in place; the building post (21-secure-agent-pod) gets a passing mention. No standalone post.
4. **Mosh client UX trade-off.** SSH and mosh-UDP are on separate LB IPs (215 vs 219), so the client invocation needs explicit `--ssh="…"` and `<udp-ip>` arguments. A future iteration could use `lbipam.cilium.io/sharing-key` to put both Services on a single IP, restoring `mosh user@host` ergonomics — but that requires touching `service-ssh.yaml`, which the operator deferred.
