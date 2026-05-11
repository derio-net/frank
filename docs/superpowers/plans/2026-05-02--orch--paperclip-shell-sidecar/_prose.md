# Paperclip Shell Sidecar Implementation Plan

## Phase 1: Build `paperclip-shell` image (agent-images repo)

### Task 1: Investigate base image inheritance

- P1.T1.S1: Read agent-shell-base Dockerfile and rootfs layout

- P1.T1.S2: Confirm the s6-overlay non-root-mode fix has landed

### Task 2: Add `paperclip-shell/` directory

- P1.T2.S1: Create directory layout

- P1.T2.S2: Write the Dockerfile (use BEGIN/END markers because the file embeds shell scripts)

- P1.T2.S3: Write `install-base-runtimes.sh` — installs the *managers* (slow-changing, image-baked)

- P1.T2.S4: Write `install-inventory.sh` — the heart of Layer 2; idempotent, fail-open, fires Telegram on failure

- P1.T2.S5: Write `notify-telegram.sh` — token + chat_id from env (mounted Secret); fail-silent if env missing

- P1.T2.S6: Write `cont-init.d/40-shell-inventory` — the s6 hook

- P1.T2.S7: Add MOTD drop-in plumbing

- P1.T2.S8: Write `paperclip-shell/README.md`

### Task 3: Add CI matrix entry + smoke test

- P1.T3.S1: Add `paperclip-shell` to the build matrix in `.github/workflows/build.yaml` (or whatever the agent-images CI workflow is named) alongside `secure-agent-kali` and `vk-local`. Build pushes to `ghcr.io/derio-net/paperclip-shell:<sha>`.

- P1.T3.S2: Add smoke test mirroring secure-agent-kali, running `/init` under the same restricted security context Kubernetes will use:

### Task 4: Open PR, review, merge

- P1.T4.S1: Open PR titled `feat: add paperclip-shell image` with body linking to this plan. Wait for CI green.

- P1.T4.S2: Capture the merged commit SHA — record in this plan's *Deployment Notes* as `agent-images SHA: <sha>` and corresponding tag `ghcr.io/derio-net/paperclip-shell:<sha>`. Phase 2 references this SHA.

## Phase 2: Frank manifests for sidecar

### Task 1: Add `paperclip-shell-home` PVC

- P2.T1.S1: Create `apps/paperclip/manifests/pvc-shell-home.yaml`

### Task 2: Add the inventory ConfigMap (initially empty)

- P2.T2.S1: Create `apps/paperclip/manifests/configmap-shell-inventory.yaml`

### Task 3: Add ExternalSecrets

- P2.T3.S1: Read existing `agent-ssh-keys` ESO definition to mirror its shape

- P2.T3.S2: Audit existing Telegram-credentials wiring

- P2.T3.S3: Create `apps/paperclip/manifests/externalsecret-shell-ssh-keys.yaml` mirroring the discovered shape; produces Secret `paperclip-shell-ssh-keys` from the same Infisical entries as `agent-ssh-keys`.

- P2.T3.S4: Create `apps/paperclip/manifests/externalsecret-shell-alerts.yaml` producing Secret `paperclip-shell-alerts` with `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID`.

### Task 4: Add the LoadBalancer Service

- P2.T4.S1: Confirm `192.168.55.221` is free

- P2.T4.S2: Create `apps/paperclip/manifests/service-shell.yaml`

### Task 5: Update `deployment.yaml` to add the sidecar

- P2.T5.S1: Investigate the upstream paperclip container's UID

- P2.T5.S2: Edit `apps/paperclip/manifests/deployment.yaml` — add `shareProcessNamespace: true` at pod-spec level, add the sidecar container, add the new volumes. Use `Edit` (not `Write`) on the existing file.

### Task 6: Add operator client-setup files

- P2.T6.S1: Create `apps/paperclip/client-setup/laptop/` mirroring `apps/secure-agent-pod/client-setup/laptop/`:

### Task 7: Open frank PR

- P2.T7.S1: Open PR titled `feat(orch): add paperclip-shell sidecar (manifests only)` with body linking to this plan and the spec. Note the inventory is empty — Phase 4 populates it.

- P2.T7.S2: Wait for ArgoCD auto-sync after merge

## Phase 3: First-deploy validation

### Task 0: Pre-flight (manual, before anything else)

- P3.T0.S1: Apply the SOPS-encrypted ssh-keys Secret — without this, sshd is up but rejects every login (the `paperclip-shell-ssh-keys` Secret volume is `optional: true` so the pod *boots*, but `authorized_keys` is empty). See `secrets/paperclip/README.md` for the bootstrap procedure. After applying, verify:

### Task 1: Pod-level health

- P3.T1.S1: Confirm both containers Ready

- P3.T1.S2: ~~Confirm shareProcessNamespace works~~ *(obsolete — Phase 2 dropped `shareProcessNamespace: true` per the agent-shell-base / s6-overlay v3 incompatibility under `runAsNonRoot`; see Deployment Notes 2026-05-03 row. Cross-container `ps` is no longer expected to work; the actual debugging surface is the shared `/paperclip` PVC, validated in Step 3.)*

- P3.T1.S3: Confirm `/paperclip` is shared and writable from both containers

### Task 2: SSH connectivity from operator laptop

- P3.T2.S1: Service has the LB IP

- P3.T2.S2: SSH connects

- P3.T2.S3: Mosh connects

- P3.T2.S4: tmux session persists across reattach

### Task 3: MOTD shows last-reconcile summary

- P3.T3.S1: Fresh login should print one of:

### Task 4: Telegram alert path (induced failure)

- P3.T4.S1: Add a known-bad entry to the inventory

- P3.T4.S2: Run reconcile

- P3.T4.S3: Verify Telegram alert arrived in the configured chat with format `⚠ paperclip-shell: 1 install(s) failed on boot`.

- P3.T4.S4: Verify MOTD shows the failure on next SSH login.

- P3.T4.S5: Revert the inventory change — remove the bogus entry, commit, push, run reconcile again. MOTD should flip to the success line. No Telegram message expected (no failures, no notification on success).

### Task 5: Confirm paperclip web UI is unaffected

## Phase 4: Populate inventory and verify reconcile

### Task 1: Curate initial inventory

- P4.T1.S1: Inspect the upstream paperclip image's pre-installed CLIs (informational — sidecar inventory is independent)

- P4.T1.S2: Edit `configmap-shell-inventory.yaml` to declare the operator's expected toolset. Suggested starting set:

### Task 2: Run reconcile and verify

- P4.T2.S2: Verify each manager reports the tool present

### Task 3: Persistence test across pod restart

- P4.T3.S1: Force a pod bounce

- P4.T3.S2: Reconnect and verify everything still present

### Task 4: Interactive install drift test

- P4.T4.S1: Manually install something not in the inventory

- P4.T4.S2: Confirm it persists across pod bounce (same restart + reconnect flow). Demonstrates Layer-3 escape hatch works.

- P4.T4.S3: Document the drift policy in this plan's *Deployment Notes*: interactive installs are intentional; promote to inventory if you want survival across PV migrations.

## Phase 5: Documentation

### Task 1: Update CLAUDE.md rules

- P5.T1.S1: Update `.claude/rules/frank-infrastructure.md`

- P5.T1.S2: Add gotchas to `.claude/rules/frank-gotchas.md` — only patterns that actually surfaced during Phase 3/4. Examples:

### Task 2: Update existing paperclip blog posts (extension, not new posts)

- P5.T2.S1: Append to `blog/content/docs/building/15-paperclip/index.md` — section *Adding a side door: SSH-able shell sidecar*. Cover: why (24/7 workflow, install-on-the-fly, kubectl-exec ergonomics); the sidecar topology (use the spec's diagram); three-layer install model (image / inventory / interactive); fail-open with Telegram alerting (the tension and the resolution); why not Ansible / not modifying the upstream image.

- P5.T2.S2: Append to `blog/content/docs/operating/18-paperclip/index.md` — new sections: *Connecting via SSH/Mosh* (with the laptop `~/.ssh/config` snippet); *Adding/removing tools* (ConfigMap edit flow vs interactive `mise install`); *Reading the install log / interpreting the alert*; *When to bump `paperclip-shell` image vs add to inventory*.

### Task 3: Run `/update-readme`

### Task 4: Sync runbook (only if any manual-operation blocks were introduced)

### Task 5: Update plan status

- P5.T5.S1: ** Set ` Status:** Deployed` at the top of this plan.

## Phase 6: Post-Deploy Checklist
