# Paperclip Shell Sidecar Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-02--orch--paperclip-shell-sidecar-design.md`
**Status:** Not Started

**Type:** Fix/extension of the `orch` layer (extends `2026-03-14--orch--paperclip-design`). Per `repo-workflows.md`: same layer code, retroactively update existing layer's blog posts (no new posts).

**Goal:** Add an SSH-able shell sidecar (`paperclip-shell`) to the `paperclip` pod, with a persistent home PVC, declarative software inventory, and fail-open Telegram alerting on install failure. Keep the upstream Paperclip container completely unmodified.

**Why now:** Operator workflow requires SSH-with-mosh (not `kubectl exec`) for 24/7 agentic work, plus the ability to install/update tools without rebuilding the upstream Paperclip image.

**Cross-repo coordination:**
- Phase 1 lands in [`derio-net/agent-images`](https://github.com/derio-net/agent-images) (new `paperclip-shell/` directory, CI smoke test).
- Phases 2–5 land in this repo (`derio-net/frank`).
- Phase 2 is blocked on Phase 1 producing a GHCR image SHA.

---

## Phase 1: Build `paperclip-shell` image (agent-images repo) [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/175 -->
**Depends on:** —

This phase ships a new container image based on `agent-shell-base` that adds Layer-1 runtime managers (`mise`, `rustup`, `pipx`), the `cont-init.d` inventory installer, and the Telegram notify helper. No frank-side changes here.

### Task 1: Investigate base image inheritance

Before writing the Dockerfile, confirm the parent image's defaults so we don't override unnecessarily.

- [x] **Step 1: Read agent-shell-base Dockerfile and rootfs layout**

```bash
gh repo clone derio-net/agent-images /tmp/agent-images && cd /tmp/agent-images
cat agent-shell-base/Dockerfile
ls agent-shell-base/rootfs/etc/cont-init.d/ 2>/dev/null
ls agent-shell-base/rootfs/etc/skel/ 2>/dev/null
```

  Capture: default `AGENT_USER` / `AGENT_HOME` build args, sshd port, where MOTD plumbing lives, whether PAM `motd.dynamic` is wired up. The new image relies on inheriting all of these unchanged.

- [x] **Step 2: Confirm the s6-overlay non-root-mode fix has landed**

  Check `agent-shell-base/Dockerfile` for `chown -R ${AGENT_UID}:${AGENT_GID} /run /var/run` (per gotcha line 91) and the `with-contenv` shebang fix (observation 2469-2472). If either is still in flight, block this phase on the relevant agent-images PR; do not work around it locally.

### Task 2: Add `paperclip-shell/` directory

- [x] **Step 1: Create directory layout**

```
agent-images/paperclip-shell/
├── Dockerfile
├── README.md
└── rootfs/
    ├── etc/cont-init.d/40-shell-inventory
    └── usr/local/lib/paperclip-shell/
        ├── install-base-runtimes.sh
        ├── install-inventory.sh
        ├── notify-telegram.sh
        └── lib.sh                          # shared helpers (logging, motd write)
```

- [x] **Step 2: Write the Dockerfile** (use BEGIN/END markers because the file embeds shell scripts)

```
BEGIN paperclip-shell/Dockerfile
ARG AGENT_SHELL_BASE_TAG=latest
FROM ghcr.io/derio-net/agent-shell-base:${AGENT_SHELL_BASE_TAG}

# Inherit AGENT_USER=agent, AGENT_HOME=/home/agent from base — do not override.

USER root
COPY --chown=root:root rootfs/ /

RUN chmod +x \
      /etc/cont-init.d/40-shell-inventory \
      /usr/local/lib/paperclip-shell/install-base-runtimes.sh \
      /usr/local/lib/paperclip-shell/install-inventory.sh \
      /usr/local/lib/paperclip-shell/notify-telegram.sh \
 && /usr/local/lib/paperclip-shell/install-base-runtimes.sh \
 && ln -sf /usr/local/lib/paperclip-shell/install-inventory.sh \
            /usr/local/bin/paperclip-shell-reconcile

USER ${AGENT_USER}
END paperclip-shell/Dockerfile
```

- [x] **Step 3: Write `install-base-runtimes.sh`** — installs the *managers* (slow-changing, image-baked)

```
BEGIN paperclip-shell/rootfs/usr/local/lib/paperclip-shell/install-base-runtimes.sh
#!/usr/bin/env bash
set -euo pipefail

# mise — asdf-style multi-runtime version manager. Installed system-wide so
# all users benefit; per-user state lives under $HOME/.local/share/mise.
curl -fsSL https://mise.run | MISE_INSTALL_PATH=/usr/local/bin/mise sh

# rustup — installed system-wide; toolchains live under $HOME/.rustup on PV.
curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs \
  | sh -s -- -y --default-toolchain none --no-modify-path
mv /root/.cargo/bin/rustup /usr/local/bin/rustup
rm -rf /root/.cargo /root/.rustup

# pipx — installed via apt (lightweight wrapper around venv). Per-user state
# under $HOME/.local/pipx on PV.
apt-get update && apt-get install -y --no-install-recommends pipx
rm -rf /var/lib/apt/lists/*
END paperclip-shell/rootfs/usr/local/lib/paperclip-shell/install-base-runtimes.sh
```

- [x] **Step 4: Write `install-inventory.sh`** — the heart of Layer 2; idempotent, fail-open, fires Telegram on failure

```
BEGIN paperclip-shell/rootfs/usr/local/lib/paperclip-shell/install-inventory.sh
#!/usr/bin/env bash
# Layer-2 inventory installer. Idempotent. Fail-open.
# Source of truth: /etc/paperclip-shell/inventory.yaml (mounted ConfigMap).
set -uo pipefail  # NOT -e — failures are accumulated, not propagated.

INVENTORY=/etc/paperclip-shell/inventory.yaml
LOG=/var/log/cont-init.d/40-shell-inventory.log
MOTD_DROPIN=/var/lib/paperclip-shell/last-reconcile.motd
NOTIFY=/usr/local/lib/paperclip-shell/notify-telegram.sh

mkdir -p "$(dirname "$LOG")" "$(dirname "$MOTD_DROPIN")"
exec > >(tee -a "$LOG") 2>&1

echo "=== paperclip-shell-reconcile @ $(date -Iseconds) ==="

if [[ ! -f "$INVENTORY" ]]; then
  echo "WARN: $INVENTORY missing; nothing to do"
  printf '⚠ paperclip-shell: inventory file missing\n' > "$MOTD_DROPIN"
  exit 0
fi

declare -i installed=0 already=0 removed=0 failed=0
declare -a failures=()

run() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "✓ $label"; return 0
  else
    echo "✗ $label (rc=$?)"; failures+=("$label"); failed+=1; return 1
  fi
}

yaml_list() { python3 -c "import yaml; d=yaml.safe_load(open('$INVENTORY'));
[print(x) for x in (d.get('$1') or [])]"; }
yaml_removed_list() { python3 -c "import yaml; d=yaml.safe_load(open('$INVENTORY'));
[print(x) for x in (d.get('removed', {}).get('$1') or [])]"; }

# --- mise ---
while read -r tool; do
  [[ -z "$tool" ]] && continue
  if mise ls "$tool" >/dev/null 2>&1; then already+=1; echo "= mise $tool"; continue; fi
  run "mise install $tool" mise install "$tool" && installed+=1
done < <(yaml_list mise)

while read -r tool; do
  [[ -z "$tool" ]] && continue
  run "mise uninstall $tool" mise uninstall "$tool" && removed+=1
done < <(yaml_removed_list mise)

# --- npm-global ---
while read -r pkg; do
  [[ -z "$pkg" ]] && continue
  if npm ls -g "$pkg" --depth=0 >/dev/null 2>&1; then already+=1; echo "= npm $pkg"; continue; fi
  run "npm i -g $pkg" npm install -g "$pkg" && installed+=1
done < <(yaml_list npm-global)

while read -r pkg; do
  [[ -z "$pkg" ]] && continue
  run "npm rm -g $pkg" npm uninstall -g "$pkg" && removed+=1
done < <(yaml_removed_list npm-global)

# --- pipx ---
while read -r pkg; do
  [[ -z "$pkg" ]] && continue
  if pipx list --short 2>/dev/null | grep -q "^$pkg "; then already+=1; echo "= pipx $pkg"; continue; fi
  run "pipx install $pkg" pipx install "$pkg" && installed+=1
done < <(yaml_list pipx)

while read -r pkg; do
  [[ -z "$pkg" ]] && continue
  run "pipx uninstall $pkg" pipx uninstall "$pkg" && removed+=1
done < <(yaml_removed_list pipx)

# --- cargo ---
while read -r crate; do
  [[ -z "$crate" ]] && continue
  if cargo install --list 2>/dev/null | grep -q "^$crate "; then already+=1; echo "= cargo $crate"; continue; fi
  run "cargo install $crate" cargo install "$crate" && installed+=1
done < <(yaml_list cargo)

while read -r crate; do
  [[ -z "$crate" ]] && continue
  run "cargo uninstall $crate" cargo uninstall "$crate" && removed+=1
done < <(yaml_removed_list cargo)

echo "=== summary: installed=$installed already=$already removed=$removed failed=$failed ==="

if (( failed > 0 )); then
  printf '⚠ paperclip-shell: %d install(s) failed on last reconcile (%s)\n  See: %s\n' \
    "$failed" "$(IFS=,; echo "${failures[*]}")" "$LOG" > "$MOTD_DROPIN"
  "$NOTIFY" "paperclip-shell: $failed install(s) failed on boot" \
    "$(printf '  %s\n' "${failures[@]}")" || true
else
  printf '✓ paperclip-shell: %d installed, %d already present, %d removed @ %s\n' \
    "$installed" "$already" "$removed" "$(date -Iseconds)" > "$MOTD_DROPIN"
fi

exit 0  # always succeed — fail-open
END paperclip-shell/rootfs/usr/local/lib/paperclip-shell/install-inventory.sh
```

- [x] **Step 5: Write `notify-telegram.sh`** — token + chat_id from env (mounted Secret); fail-silent if env missing

```
BEGIN paperclip-shell/rootfs/usr/local/lib/paperclip-shell/notify-telegram.sh
#!/usr/bin/env bash
set -uo pipefail
TITLE="${1:-paperclip-shell alert}"
DETAIL="${2:-}"

: "${FRANK_C2_TELEGRAM_BOT_TOKEN:=}"
: "${FRANK_C2_TELEGRAM_CHAT_ID:=}"
[[ -z "$FRANK_C2_TELEGRAM_BOT_TOKEN" || -z "$FRANK_C2_TELEGRAM_CHAT_ID" ]] && exit 0

POD="${HOSTNAME:-paperclip-shell}"
TEXT="${TITLE}
${DETAIL}
Pod: ${POD}
kubectl logs ${POD} -c paperclip-shell"

curl -fsS --max-time 10 \
  -X POST "https://api.telegram.org/bot${FRANK_C2_TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${FRANK_C2_TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=${TEXT}" >/dev/null || true
END paperclip-shell/rootfs/usr/local/lib/paperclip-shell/notify-telegram.sh
```

- [x] **Step 6: Write `cont-init.d/40-shell-inventory`** — the s6 hook

```
BEGIN paperclip-shell/rootfs/etc/cont-init.d/40-shell-inventory
#!/usr/bin/with-contenv bash
exec /usr/local/lib/paperclip-shell/install-inventory.sh
END paperclip-shell/rootfs/etc/cont-init.d/40-shell-inventory
```

- [x] **Step 7: Add MOTD drop-in plumbing**

  If `agent-shell-base` already wires `pam_motd` with `motd.dynamic`, drop a script that prints `/var/lib/paperclip-shell/last-reconcile.motd`. If not, add `/etc/update-motd.d/50-paperclip-shell` and ensure sshd is configured to print dynamic motd. Verify with the parent image's existing motd plumbing identified in Task 1, Step 1.

- [x] **Step 8: Write `paperclip-shell/README.md`**

  One-page summary: image purpose, build args, where the inventory ConfigMap lands, how to invoke `paperclip-shell-reconcile`, link back to this plan.

### Task 3: Add CI matrix entry + smoke test

- [x] **Step 1: Add `paperclip-shell` to the build matrix** in `.github/workflows/build.yaml` (or whatever the agent-images CI workflow is named) alongside `secure-agent-kali` and `vk-local`. Build pushes to `ghcr.io/derio-net/paperclip-shell:<sha>`.

- [x] **Step 2: Add smoke test** mirroring secure-agent-kali, running `/init` under the same restricted security context Kubernetes will use:

```bash
docker run --rm --user 1000:1000 \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  ghcr.io/derio-net/paperclip-shell:${{ github.sha }} \
  bash -c '
    /init &
    for i in $(seq 1 30); do
      if ss -ltn 2>/dev/null | grep -q ":2222"; then echo "sshd up"; exit 0; fi
      sleep 1
    done
    echo "sshd never bound 2222"; exit 1
  '
```

  Also assert: `mise --version`, `pipx --version`, `rustup --version`, `paperclip-shell-reconcile` (with empty inventory mount) all succeed.

### Task 4: Open PR, review, merge

- [x] **Step 1: Open PR titled `feat: add paperclip-shell image`** with body linking to this plan. Wait for CI green.

- [ ] **Step 2: Capture the merged commit SHA** — record in this plan's *Deployment Notes* as `agent-images SHA: <sha>` and corresponding tag `ghcr.io/derio-net/paperclip-shell:<sha>`. Phase 2 references this SHA.

---

## Phase 2: Frank manifests for sidecar [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/176 -->
**Depends on:** Phase 1

All work in this repo (`derio-net/frank`). Adds new resources without modifying the existing `paperclip` container spec.

### Task 1: Add `paperclip-shell-home` PVC

- [ ] **Step 1: Create `apps/paperclip/manifests/pvc-shell-home.yaml`**

```
BEGIN apps/paperclip/manifests/pvc-shell-home.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: paperclip-shell-home
  namespace: paperclip-system
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 20Gi
END apps/paperclip/manifests/pvc-shell-home.yaml
```

### Task 2: Add the inventory ConfigMap (initially empty)

- [ ] **Step 1: Create `apps/paperclip/manifests/configmap-shell-inventory.yaml`**

  Start with empty arrays — Phase 4 populates them. This proves the installer is wired up and idempotent before any tools are declared:

```
BEGIN apps/paperclip/manifests/configmap-shell-inventory.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: paperclip-shell-inventory
  namespace: paperclip-system
data:
  inventory.yaml: |
    # Layer-2 declarations — installed at boot via cont-init.d.
    # See docs/superpowers/specs/2026-05-02--orch--paperclip-shell-sidecar-design.md
    mise: []
    npm-global: []
    pipx: []
    cargo: []
    removed:
      mise: []
      npm-global: []
      pipx: []
      cargo: []
END apps/paperclip/manifests/configmap-shell-inventory.yaml
```

### Task 3: Add ExternalSecrets

- [ ] **Step 1: Read existing `agent-ssh-keys` ESO definition** to mirror its shape

```bash
ls apps/secure-agent-pod/manifests/ | grep -i 'externalsecret\|ssh-key'
cat apps/secure-agent-pod/manifests/externalsecret-github-token.yaml | head -40  # for ESO scaffold reference
```

  Capture: `secretStoreRef`, Infisical project / path, the exact `dataFrom` or `data:` shape that produces `agent-ssh-keys`.

- [ ] **Step 2: Audit existing Telegram-credentials wiring**

```bash
grep -rE 'FRANK_C2_TELEGRAM_BOT_TOKEN|FRANK_C2_TELEGRAM_CHAT_ID' apps/ secrets/ 2>/dev/null
```

  Decision: if a Secret containing both values already exists in another namespace, replicate the ESO (one ESO per namespace, same Infisical source). If not, create one specifically for `paperclip-system`.

- [ ] **Step 3: Create `apps/paperclip/manifests/externalsecret-shell-ssh-keys.yaml`** mirroring the discovered shape; produces Secret `paperclip-shell-ssh-keys` from the same Infisical entries as `agent-ssh-keys`.

- [ ] **Step 4: Create `apps/paperclip/manifests/externalsecret-shell-alerts.yaml`** producing Secret `paperclip-shell-alerts` with `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID`.

### Task 4: Add the LoadBalancer Service

- [ ] **Step 1: Confirm `192.168.55.221` is free**

```bash
kubectl get svc -A -o jsonpath='{range .items[*]}{.status.loadBalancer.ingress[0].ip}{"\n"}{end}' \
  | sort -u | grep -F 192.168.55.221 \
  || echo "192.168.55.221 is free"
```

- [ ] **Step 2: Create `apps/paperclip/manifests/service-shell.yaml`**

```
BEGIN apps/paperclip/manifests/service-shell.yaml
apiVersion: v1
kind: Service
metadata:
  name: paperclip-shell
  namespace: paperclip-system
  annotations:
    lbipam.cilium.io/ips: 192.168.55.221
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: paperclip
    app.kubernetes.io/component: server
  ports:
    - { name: ssh, port: 22, targetPort: 2222, protocol: TCP }
    - { name: mosh-60000, port: 60000, protocol: UDP }
    - { name: mosh-60001, port: 60001, protocol: UDP }
    - { name: mosh-60002, port: 60002, protocol: UDP }
    - { name: mosh-60003, port: 60003, protocol: UDP }
    - { name: mosh-60004, port: 60004, protocol: UDP }
    - { name: mosh-60005, port: 60005, protocol: UDP }
    - { name: mosh-60006, port: 60006, protocol: UDP }
    - { name: mosh-60007, port: 60007, protocol: UDP }
    - { name: mosh-60008, port: 60008, protocol: UDP }
    - { name: mosh-60009, port: 60009, protocol: UDP }
    - { name: mosh-60010, port: 60010, protocol: UDP }
    - { name: mosh-60011, port: 60011, protocol: UDP }
    - { name: mosh-60012, port: 60012, protocol: UDP }
    - { name: mosh-60013, port: 60013, protocol: UDP }
    - { name: mosh-60014, port: 60014, protocol: UDP }
    - { name: mosh-60015, port: 60015, protocol: UDP }
END apps/paperclip/manifests/service-shell.yaml
```

### Task 5: Update `deployment.yaml` to add the sidecar

- [ ] **Step 1: Investigate the upstream paperclip container's UID**

```bash
docker run --rm --entrypoint id ghcr.io/paperclipai/paperclip:sha-3494e84
# expect uid=1000 or document the actual value
```

  If the value is not `1000`, decide between option (a) `initContainer` chowning `/paperclip` to `fsGroup: 1000`, or (b) overriding `paperclip` container's `securityContext.runAsUser: 1000`. Document the decision inline in this plan's *Deployment Notes* section.

- [ ] **Step 2: Edit `apps/paperclip/manifests/deployment.yaml`** — add `shareProcessNamespace: true` at pod-spec level, add the sidecar container, add the new volumes. Use `Edit` (not `Write`) on the existing file.

  Sidecar container fragment:

```yaml
- name: paperclip-shell
  image: ghcr.io/derio-net/paperclip-shell:<SHA-FROM-PHASE-1>
  imagePullPolicy: IfNotPresent
  ports:
    - { name: ssh, containerPort: 2222, protocol: TCP }
    - { name: mosh-60000, containerPort: 60000, protocol: UDP }
    # ... 60001 through 60015 (15 more lines)
  env:
    - { name: PAPERCLIP_SHELL_USER, value: agent }
    - { name: MOSH_SERVER_NETWORK_TMOUT, value: "3600" }
  envFrom:
    - secretRef: { name: paperclip-shell-alerts, optional: true }
  volumeMounts:
    - { name: shell-home, mountPath: /home/agent }
    - { name: paperclip-data, mountPath: /paperclip }
    - { name: shell-ssh-keys, mountPath: /etc/ssh-keys, readOnly: true }
    - { name: shell-inventory, mountPath: /etc/paperclip-shell, readOnly: true }
  securityContext:
    runAsUser: 1000
    runAsGroup: 1000
    runAsNonRoot: true
    allowPrivilegeEscalation: false
    capabilities: { drop: ["ALL"] }
  resources:
    requests: { cpu: 500m, memory: 1Gi }
    limits:   { cpu: "4", memory: 8Gi }
  readinessProbe:
    tcpSocket: { port: 2222 }
    initialDelaySeconds: 10
    periodSeconds: 30
  livenessProbe:
    tcpSocket: { port: 2222 }
    initialDelaySeconds: 30
    periodSeconds: 60
```

  New volume entries (extend the existing `volumes:` array):

```yaml
- name: shell-home
  persistentVolumeClaim: { claimName: paperclip-shell-home }
- name: shell-ssh-keys
  secret: { secretName: paperclip-shell-ssh-keys, defaultMode: 0400 }
- name: shell-inventory
  configMap: { name: paperclip-shell-inventory }
```

  At pod-spec level: `shareProcessNamespace: true`.

### Task 6: Add operator client-setup files

- [ ] **Step 1: Create `apps/paperclip/client-setup/laptop/`** mirroring `apps/secure-agent-pod/client-setup/laptop/`:

  - `ssh-config.snippet` — `Host paperclip-shell` block with `HostName 192.168.55.221`, `Port 22`, `User agent`, `IdentityFile ~/.ssh/<your_key>`.
  - `mosh-wrapper.sh` — invokes `mosh --server="mosh-server new -p 60000:60015" agent@192.168.55.221`.
  - `README.md` — explains both, points at the secure-agent-pod README where applicable.

### Task 7: Open frank PR

- [ ] **Step 1: Open PR titled `feat(orch): add paperclip-shell sidecar (manifests only)`** with body linking to this plan and the spec. Note the inventory is empty — Phase 4 populates it.

- [ ] **Step 2: Wait for ArgoCD auto-sync after merge**

```bash
kubectl -n argocd get application paperclip -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'
# expect: Synced Healthy
```

---

## Phase 3: First-deploy validation [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/177 -->
**Depends on:** Phase 2

Confirms the sidecar deploys cleanly, paperclip is unaffected, and the alerting path works end-to-end.

### Task 1: Pod-level health

- [ ] **Step 1: Confirm both containers Ready**

```bash
kubectl -n paperclip-system get pod -l app.kubernetes.io/name=paperclip \
  -o jsonpath='{range .items[0].status.containerStatuses[*]}{.name}: ready={.ready} restarts={.restartCount}{"\n"}{end}'
# expect both 'paperclip' and 'paperclip-shell' with ready=true
```

- [ ] **Step 2: Confirm shareProcessNamespace works**

```bash
kubectl -n paperclip-system exec -c paperclip-shell deploy/paperclip -- ps -ef | grep -E 'paperclip|node|sshd'
# expect to see paperclip's process(es) AND sshd in the output
```

- [ ] **Step 3: Confirm `/paperclip` is shared and writable from both containers**

```bash
kubectl -n paperclip-system exec -c paperclip-shell deploy/paperclip -- touch /paperclip/.shell-write-test
kubectl -n paperclip-system exec -c paperclip            deploy/paperclip -- ls -la /paperclip/.shell-write-test
kubectl -n paperclip-system exec -c paperclip-shell deploy/paperclip -- rm /paperclip/.shell-write-test
```

  If the write or read fails with permission denied, escalate to the UID/GID investigation captured in Phase 2 Task 5 Step 1.

### Task 2: SSH connectivity from operator laptop

- [ ] **Step 1: Service has the LB IP**

```bash
kubectl -n paperclip-system get svc paperclip-shell -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
# expect: 192.168.55.221
```

- [ ] **Step 2: SSH connects**

```bash
ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/<your-key> agent@192.168.55.221 \
  'whoami; hostname; cat /etc/os-release | head -3; ls -la ~'
# expect: whoami=agent, /home/agent populated from /etc/skel
```

- [ ] **Step 3: Mosh connects**

```bash
mosh agent@192.168.55.221 -- echo 'mosh ok'
# expect 'mosh ok' over UDP without falling back to SSH
```

- [ ] **Step 4: tmux session persists across reattach**

```bash
ssh agent@192.168.55.221 -- tmux new-session -d -s test 'sleep 600'
ssh agent@192.168.55.221 -- tmux ls
# expect 'test' session listed
ssh agent@192.168.55.221 -- tmux kill-session -t test
```

### Task 3: MOTD shows last-reconcile summary

- [ ] **Step 1: Fresh login should print** one of:

```
✓ paperclip-shell: 0 installed, 0 already present, 0 removed @ 2026-05-…
```

  Verify by SSH-ing in and observing the motd. If the line is missing, the `motd.dynamic` plumbing in `agent-shell-base` may need adjustment — log as a follow-up task in Phase 1 rather than blocking here.

### Task 4: Telegram alert path (induced failure)

- [ ] **Step 1: Add a known-bad entry to the inventory**

  Edit `apps/paperclip/manifests/configmap-shell-inventory.yaml`:

```yaml
data:
  inventory.yaml: |
    npm-global:
      - "@anthropic-ai/this-package-does-not-exist-XXXX"
    # other sections unchanged
```

  Commit, push, ArgoCD syncs.

- [ ] **Step 2: Run reconcile**

```bash
ssh agent@192.168.55.221 -- paperclip-shell-reconcile
```

- [ ] **Step 3: Verify Telegram alert arrived** in the configured chat with format `⚠ paperclip-shell: 1 install(s) failed on boot`.

- [ ] **Step 4: Verify MOTD shows the failure** on next SSH login.

- [ ] **Step 5: Revert the inventory change** — remove the bogus entry, commit, push, run reconcile again. MOTD should flip to the success line. No Telegram message expected (no failures, no notification on success).

### Task 5: Confirm paperclip web UI is unaffected

- [ ] **Step 1:**

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://192.168.55.212:3100/
# expect 200 or 302 — same as before this plan
```

---

## Phase 4: Populate inventory and verify reconcile [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/178 -->
**Depends on:** Phase 3

Move from "the wiring works" to "the operator's day-to-day toolset is installed."

### Task 1: Curate initial inventory

- [ ] **Step 1: Inspect the upstream paperclip image's pre-installed CLIs** (informational — sidecar inventory is independent)

```bash
kubectl -n paperclip-system exec -c paperclip deploy/paperclip -- bash -c \
  'for c in claude codex gh git node python3 npm pipx cargo rustc; do command -v "$c" >/dev/null 2>&1 && echo "$c: $(command -v "$c")"; done'
```

  Anything already present in the paperclip container is *not* relevant to the sidecar's inventory — they live in different filesystems. The inventory is for the *shell sidecar's* environment only.

- [ ] **Step 2: Edit `configmap-shell-inventory.yaml`** to declare the operator's expected toolset. Suggested starting set:

```yaml
data:
  inventory.yaml: |
    mise:
      - python@3.12
      - node@20
      - rust@stable
    npm-global:
      - "@anthropic-ai/claude-code"
      - "@openai/codex"
    pipx:
      - black
      - ruff
    cargo:
      - ripgrep
      - eza
```

  Commit and push.

### Task 2: Run reconcile and verify

- [ ] **Step 1:** ArgoCD syncs the ConfigMap. Then:

```bash
ssh agent@192.168.55.221 -- paperclip-shell-reconcile
```

  Expect log lines for each tool, ending with `summary: installed=N already=0 removed=0 failed=0`.

- [ ] **Step 2: Verify each manager reports the tool present**

```bash
ssh agent@192.168.55.221 -- bash -lc '
  mise ls
  npm ls -g --depth=0
  pipx list --short
  cargo install --list
'
```

### Task 3: Persistence test across pod restart

- [ ] **Step 1: Force a pod bounce**

```bash
kubectl -n paperclip-system rollout restart deploy/paperclip
kubectl -n paperclip-system rollout status deploy/paperclip --timeout=120s
```

- [ ] **Step 2: Reconnect and verify everything still present**

```bash
ssh agent@192.168.55.221 -- bash -lc '
  cargo install --list | grep -E "ripgrep|eza"
  pipx list --short
  ls ~/.cargo/bin
'
# expect: tools listed, binaries present on PV
```

  Also confirm the MOTD on this fresh login reads `installed=0 already=N removed=0 failed=0` — proves the installer ran on boot, found everything already present, and committed no work.

### Task 4: Interactive install drift test

- [ ] **Step 1: Manually install something not in the inventory**

```bash
ssh agent@192.168.55.221 -- cargo install fd-find
```

- [ ] **Step 2: Confirm it persists across pod bounce** (same restart + reconnect flow). Demonstrates Layer-3 escape hatch works.

- [ ] **Step 3: Document the drift policy** in this plan's *Deployment Notes*: interactive installs are intentional; promote to inventory if you want survival across PV migrations.

---

## Phase 5: Documentation [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/179 -->
**Depends on:** Phase 4

### Task 1: Update CLAUDE.md rules

- [ ] **Step 1: Update `.claude/rules/frank-infrastructure.md`**

  Add to the Frank Cluster Services table:

```
| Paperclip Shell (SSH+Mosh) | 192.168.55.221 | Cilium L2 LoadBalancer (port 22/SSH, UDP 60000-60015/Mosh) |
```

- [ ] **Step 2: Add gotchas to `.claude/rules/frank-gotchas.md`** — only patterns that actually surfaced during Phase 3/4. Examples:
  - "MixedProtocolLBService working on Cilium 1.17 + K8s 1.35 — single LB IP serves both TCP/22 and UDP/60000-60015 cleanly."
  - Anything else that surfaced.

### Task 2: Update existing paperclip blog posts (extension, not new posts)

- [ ] **Step 1: Append to `blog/content/docs/building/15-paperclip/index.md`** — section *Adding a side door: SSH-able shell sidecar*. Cover: why (24/7 workflow, install-on-the-fly, kubectl-exec ergonomics); the sidecar topology (use the spec's diagram); three-layer install model (image / inventory / interactive); fail-open with Telegram alerting (the tension and the resolution); why not Ansible / not modifying the upstream image.

- [ ] **Step 2: Append to `blog/content/docs/operating/18-paperclip/index.md`** — new sections: *Connecting via SSH/Mosh* (with the laptop `~/.ssh/config` snippet); *Adding/removing tools* (ConfigMap edit flow vs interactive `mise install`); *Reading the install log / interpreting the alert*; *When to bump `paperclip-shell` image vs add to inventory*.

### Task 3: Run `/update-readme`

- [ ] **Step 1:** Run the skill. Verify the Service Access table now includes `192.168.55.221` and the Repository Structure section reflects any new directories under `apps/paperclip/`.

### Task 4: Sync runbook (only if any manual-operation blocks were introduced)

- [ ] **Step 1:** Audit this plan for `# manual-operation` blocks — there are none currently. If any were added during implementation (e.g., an out-of-band initContainer chown step), run `/sync-runbook`. Otherwise skip.

### Task 5: Update plan status

- [ ] **Step 1:** Set `**Status:** Deployed` at the top of this plan.

---

## Phase 6: Post-Deploy Checklist [manual]
<!-- Tracking: https://github.com/derio-net/frank/issues/180 -->
**Depends on:** Phase 5

This is a fix/extension plan, so most post-deploy steps are absorbed into Phase 5. This phase explicitly confirms the per-step disposition rather than skipping silently.

- [-] **Step 1: Expose externally** — *skipped:* not user-facing; SSH/Mosh are operator-only on the LAN. No Traefik IngressRoute, no homepage tile.
- [-] **Step 2: Write building blog post** — *skipped:* extension to existing layer; appended to `building/15-paperclip` in Phase 5 Task 2 instead.
- [-] **Step 3: Write operating blog post** — *skipped:* extension to existing layer; appended to `operating/18-paperclip` in Phase 5 Task 2 instead.
- [ ] **Step 4: Update README** — done in Phase 5 Task 3. Confirm.
- [-] **Step 5: Sync runbook** — *skipped:* no `# manual-operation` blocks introduced.
- [ ] **Step 6: Update plan status** — done in Phase 5 Task 5. Confirm `**Status:** Deployed`.

---

## Deployment Notes

*(Populated as phases run. Each row records the date, phase, and the concrete value or decision recorded at that step.)*

| Date | Phase | Note |
|------|-------|------|
| 2026-05-02 | Phase 1 | `derio-net/agent-images` PR opened: https://github.com/derio-net/agent-images/pull/46 — adds `paperclip-shell/` directory, CI matrix entry, and smoke test. P1.T4.S2 (capturing the merged SHA + GHCR tag for Phase 2 to consume) deferred until that PR merges. |
| 2026-05-02 | Phase 1 | Investigation findings: agent-shell-base defaults are `AGENT_USER=agent` / `AGENT_HOME=/home/agent` / UID,GID=1000 (inherited unchanged). The `/run` ownership fix and `with-contenv` shebang fix have already landed in `agent-shell-base/Dockerfile` (lines 69–70 and `/command/with-contenv` shebangs respectively), so no upstream blocker. |
| 2026-05-02 | Phase 1 | Deviation from plan: sshd in `agent-shell-base` is configured with `UsePAM no` (sshd_config L7), so PAM `motd.dynamic` is not available. Implemented MOTD via `/etc/profile.d/50-paperclip-shell-motd.sh` instead — fires for both interactive ssh and `kubectl exec -it ... bash -l`. |
| 2026-05-02 | Phase 1 | Deviation from plan: added `/etc/profile.d/40-paperclip-shell-paths.sh` (not in original plan) to wire mise shims, `~/.cargo/bin`, and `~/.local/bin` into the operator's PATH. The installer also prepends these dirs at reconcile-time so `npm`/`cargo` from a mise-installed runtime resolve correctly inside `cont-init.d` boot context. |
| 2026-05-02 | Phase 1 | Deviation from plan: `install-base-runtimes.sh` was extended with the apt build deps (`build-essential`, `pkg-config`, `libssl-dev`, `python3`, `python3-yaml`, `pipx`, `jq`) needed by the runtime managers and by `install-inventory.sh`'s YAML parsing. Original plan implicitly assumed these were already in the parent image; they aren't. The system Python is the load-bearing one for inventory parsing — at `cont-init.d` boot time mise shims are not yet on PATH for the script's own environment, and parsing must keep working before any mise-managed runtimes land on the PV. |
| 2026-05-02 | Phase 1 | Deviation from plan: `install-inventory.sh` uses `mise where "$tool"` rather than the plan's `mise ls "$tool" \| grep`. `mise where` returns 0 when a matching version family is installed (incl. when the operator did `mise install python@3.12.4` interactively and the inventory says `python@3.12`); `mise ls` would require parsing. Cleaner idempotency + closer to mise's intended public API. |
| 2026-05-02 | Phase 1 | Deviation from plan: investigation evidence was that `agent-shell-base` ships **no** `/etc/profile.d/` additions and **no** PAM motd configuration today (`sshd_config` L7 sets `UsePAM no`; `etc/skel/` only contains `.tmux.conf`). `paperclip-shell` is the first image in this lineage to add either, so there is no inherited motd convention to reuse — the `/etc/profile.d/50-paperclip-shell-motd.sh` decision is the new convention for now. |
| 2026-05-02 | Phase 1 | Post-review corrections (commit `64e5a42`, agent-images PR #46): pre-create `/var/log/cont-init.d` and `/var/lib/paperclip-shell` owned by AGENT_UID at image-build time (without this the installer's `tee` + MOTD write fail silently under K8s `cap-drop=ALL` / `runAsUser: 1000`); drop dead `RUSTUP_HOME=/usr/local/lib/rustup` in favour of per-user `~/.rustup` initialisation; harden `run()` rc capture; switch `cargo install --list` parsing to a whitespace-strip pipeline; drop trailing blank line in Telegram body via `printf` instead of HEREDOC. |
