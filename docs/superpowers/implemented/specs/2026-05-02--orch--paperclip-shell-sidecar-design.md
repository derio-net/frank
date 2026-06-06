# Paperclip Shell Sidecar — Design

**Status:** Draft
**Layer:** `orch`
**Spec date:** 2026-05-02

## Goal

Add an SSH-able shell sidecar to the `paperclip` pod so the operator can land in a persistent, customisable Linux environment alongside the Paperclip server, with `cd /paperclip` access to the shared data PVC and a private home directory for tools, dotfiles, and history. Keep the upstream Paperclip container completely unmodified, and keep the shell environment evolvable without rebuilding the Paperclip image.

This is a **layer extension** of the existing `paperclip` deployment, not a new layer.

## Motivation

Paperclip's expected workflow assumes the operator can SSH in, install tools, and treat the pod as a long-lived dev environment for 24/7 agentic work. The current state requires `kubectl exec` for every interaction, which is functional but inconvenient — no mosh, no persistent tmux sessions across reconnects, no first-class SSH config on the laptop side.

Three constraints shape the design:

1. **The Paperclip image is upstream-managed and bumps unpredictably.** The recent transition from a fork to `ghcr.io/paperclipai/paperclip` (commits `b35b781`, `d4060c8`) explicitly stepped off the maintenance treadmill of forking the image. Baking sshd into a derivative of the upstream image — or worse, installing sshd onto the PV at runtime — would put us back on it: every upstream rebase risks ABI drift, entrypoint changes, or UID changes that would break the SSH layer.
2. **24/7 agentic workflows are downtime-sensitive but not zero-downtime.** Pod restarts cost ~30s of SSH disruption plus tmux reattach, which `tmux-resurrect` (already wired up in `agent-shell-base`'s `/etc/skel`) preserves cleanly. The lever is *minimising restart frequency for routine changes*, not eliminating restarts.
3. **The cluster's everything-declarative principle has fast and slow loops.** Image rebuilds + ArgoCD sync is the slow loop. Boot-time `cont-init.d` scripts reading versioned ConfigMaps are also declarative — same git-as-source-of-truth, with PV state as the materialised result.

## Constraints

1. **`paperclip-data` is RWO.** Paperclip's existing PVC cannot mount on two pods simultaneously. The shell must live as a sidecar in the same pod, not a separate Deployment.
2. **`strategy: Recreate`** stays — RWO PVC requires it (per `frank-gotchas.md`).
3. **Non-root, capability-dropped security context.** The shell runs `runAsUser: 1000`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`. This blocks any `apt`-style runtime install — userspace package management only.
4. **Paperclip container untouched.** No image change, no env change, no mount change, no UID override unless plan-time investigation reveals a `fsGroup` conflict.
5. **Shell image evolves on a separate cadence from Paperclip.** The shell's image lives in `derio-net/agent-images` alongside `secure-agent-kali` and `vk-local`, and bumps independently of upstream Paperclip releases.
6. **Declarative-only.** The shell's image is SHA-pinned in git; the userspace inventory is a versioned ConfigMap; SSH keys come from Infisical via ESO. No interactive setup steps that aren't either codified or explicitly flagged as Layer-3 escape-hatch installs.

## Architecture

### Pod topology

```
namespace: paperclip-system
└── Deployment: paperclip
    │   strategy: Recreate
    │   nodeSelector: { zone: core }
    │   securityContext: { fsGroup: 1000 }
    │   shareProcessNamespace: true                  # NEW — lets shell ps/strace paperclip
    │
    ├── container: paperclip                          # UNCHANGED
    │     image: ghcr.io/paperclipai/paperclip:sha-…
    │     volumeMount: paperclip-data → /paperclip
    │     port: 3100/TCP                              # existing LB 192.168.55.212
    │
    └── container: paperclip-shell                    # NEW
          image: ghcr.io/derio-net/paperclip-shell:<sha>
          securityContext:
            runAsUser: 1000
            runAsGroup: 1000
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
          volumeMounts:
            paperclip-shell-home      → /home/agent           # NEW PVC, RWO, 20Gi
            paperclip-data            → /paperclip            # SHARED RW with paperclip
            paperclip-shell-ssh-keys  → /etc/ssh-keys         # NEW Secret (ESO)
            paperclip-shell-inventory → /etc/paperclip-shell  # NEW ConfigMap
          ports:
            2222/TCP                                  # sshd
            60000-60015/UDP                           # mosh range
          resources:
            requests: { cpu: 500m, memory: 1Gi }
            limits:   { cpu: 4000m, memory: 8Gi }
          readinessProbe: { tcpSocket: { port: 2222 } }
          livenessProbe:  { tcpSocket: { port: 2222 } }
```

### Image topology

```
ghcr.io/derio-net/agent-shell-base:<tag>
  + s6-overlay v3 (non-root mode), sshd, tmux, mosh, base CLI tools
  + AGENT_USER=agent (default), AGENT_HOME=/home/agent (default)
      │
      ├──► ghcr.io/derio-net/secure-agent-kali:<sha>     (existing)
      │       overrides AGENT_USER=claude, AGENT_HOME=/home/claude
      │       + Kali pentest toolset, kubectl, talosctl, omnictl, infisical CLI
      │
      ├──► ghcr.io/derio-net/vk-local:<sha>              (existing)
      │
      └──► ghcr.io/derio-net/paperclip-shell:<sha>       (NEW)
              uses default AGENT_USER=agent, AGENT_HOME=/home/agent
              + mise, rustup, pipx (Layer-1 runtime managers)
              + cont-init.d/40-shell-inventory + install-inventory.sh
              + cont-init.d hook to fire Telegram alert on inventory failure
              + /etc/skel: .bashrc, .tmux.conf with resurrect/continuum
```

### Networking

One LoadBalancer Service exposes both SSH (TCP) and Mosh (UDP) on a single IP, using the K8s 1.26+ MixedProtocolLBService capability. Cilium L2 announces the IP at L2; the kube-proxy-replacement handles per-port TCP/UDP routing in-kernel.

```yaml
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
  ports:
    - { name: ssh, port: 22, targetPort: 2222, protocol: TCP }
    - { name: mosh-60000, port: 60000, protocol: UDP }
    - { name: mosh-60001, port: 60001, protocol: UDP }
    # … through 60015
```

`192.168.55.221` is the next free IP after the current allocations end at 220 (per `frank-infrastructure.md`).

### State persistence

| PVC | Size | RWO | Owned by | Purpose |
|---|---|---|---|---|
| `paperclip-data` (existing) | upstream's choice | yes | upstream Paperclip schema | Paperclip app data; mounted RW in both containers |
| `paperclip-shell-home` (NEW) | 20 Gi | yes | operator | Shell home: tools, dotfiles, ssh keypairs, tmux-resurrect snapshots |

**Two persistence boundaries, made explicit:**

1. `/paperclip` is upstream's territory. The shell may read/write it, but assume any upstream Paperclip update could rearrange its contents. No personal config goes here.
2. `/home/agent` is the operator's. Nothing upstream can touch it. Layer-2 declared installs land here. Layer-3 interactive installs land here. This is the durability anchor that makes "tools survive image bumps" true.

### SSH key management

Reuse the existing `agent-ssh-keys` Infisical entries via a new `ExternalSecret` CR pointing at the same source. One identity, two pods, single source of truth for `authorized_keys`. Rotating a key in Infisical reconciles both pods on the next ESO refresh.

## paperclip-shell image design

`FROM ghcr.io/derio-net/agent-shell-base:<tag>`. Inherits sshd, tmux, mosh, base CLI tools, and the `cont-init.d` non-root-mode setup (the same setup currently being hardened in agent-images CI, observation 2466–2472).

**Adds:**
- **Layer-1 runtime managers** baked into the image, slow-changing: `mise` (asdf-replacement), `rustup`, `pipx`. These are the *managers*; tools they install live on the PV.
- **`/etc/cont-init.d/40-shell-inventory`** — runs on every container boot, reads the inventory ConfigMap, runs idempotent installs.
- **`/usr/local/lib/paperclip-shell/install-inventory.sh`** — the actual installer; tees output to file + stdout; on failure, fires a Telegram alert via `/usr/local/lib/paperclip-shell/notify-telegram.sh`.
- **`/etc/skel/`** seed: `.bashrc` (with `mise`, `cargo`, `npm-global` PATH wired up), `.tmux.conf` (sourcing `/etc/agent/tmux-resurrect.conf` per the existing kali pattern), `.ssh/` scaffold.

**Defaults inherited from `agent-shell-base`:**
- `AGENT_USER=agent`, `AGENT_HOME=/home/agent` (no override needed; this is a fresh PV, unlike `secure-agent-kali`'s legacy `claude`/`/home/claude`).
- s6-overlay v3 in non-root mode, including the `/run` ownership fix from observation 2459.
- `cont-init.d` shebang/with-contenv path conventions (whatever fix lands in `agent-shell-base` from observation 2469-2472 — `paperclip-shell` inherits it, doesn't re-solve it).

**Explicitly NOT in the image:**
- `apt`-installed pentest/kubectl/talosctl tooling — none of that is needed for Paperclip workflows. Keep the image slim.
- Any application-layer tools (claude CLI, codex CLI, etc.) — those go in the inventory, where they can be bumped without rebuilding the image.

**CI smoke test:** mirror the `secure-agent-kali` smoke test currently being repaired in agent-images. Run `/init` under `--cap-drop=ALL --security-opt=no-new-privileges --user 1000`. Verify sshd binds 2222, the inventory installer runs (with empty inventory) without blocking, motd renders.

## Declarative software inventory

### Shape

`apps/paperclip/manifests/configmap-shell-inventory.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: paperclip-shell-inventory
  namespace: paperclip-system
data:
  inventory.yaml: |
    # Layer-2 declarations — installed at boot via cont-init.d, written to PV.
    # Each section is idempotent and uses the manager's native install command.
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
    # Opt-in removals — entries here are actively uninstalled on next boot.
    removed:
      mise: []
      npm-global: []
      pipx: []
      cargo: []
```

### Installer behaviour

- Runs at every container boot, after sshd is configured, before sshd accepts connections.
- For each section: query the manager (`mise ls`, `npm ls -g --json`, `pipx list --json`, `cargo install --list`), diff against declared, install missing, remove the `removed:` set.
- Idempotent: re-running with no changes is a ~1s no-op.
- **Fail-open:** failure of any single tool install logs and continues; never blocks sshd startup. A broken `cargo install` does not deny SSH access.
- Logs to both `/var/log/cont-init.d/40-shell-inventory.log` and container stdout.
- Exposes a `paperclip-shell-reconcile` CLI symlink so the operator can re-run on demand without restarting the pod (e.g., after a ConfigMap edit).

### Editing flow

| Operator wants to... | Operator does... | Effect |
|---|---|---|
| Add a tool permanently | Edit ConfigMap, commit, ArgoCD syncs | Installed on next pod restart, or run `paperclip-shell-reconcile` immediately |
| Try a tool quickly | SSH in, `mise install <x>` / `cargo install <x>` | Immediately, persists on PV, drifts from declared state |
| Promote an interactive install | Add to ConfigMap, commit | Already installed; declaration just records intent |
| Remove a tool | Add to `removed:` list, commit | Uninstalled on next boot or `paperclip-shell-reconcile` |

### Why no Ansible

Ansible is built for fleets and idempotent role composition. For one container with a flat list of tools, the playbook + inventory + role ceremony exceeds the problem. A ~50-line bash script reading a YAML inventory does the same job with no new system to learn. The non-root security context is the binding constraint regardless — Ansible cannot make `apt` work in a `cap-drop=ALL` container; that needs root or image rebuild, both of which are explicit decisions, not config-management automation.

### Why no `apt:` key in the inventory

The schema deliberately omits any system-package install path. Adding one would either (a) require granting capabilities the security model rejects, or (b) require a privileged init container that runs at every boot — both of which hide cost behind the appearance of declarative simplicity. System packages that need adding are an image concern: bump `paperclip-shell` in agent-images.

## Visibility & alerting

The fail-open installer requires active visibility, not passive log files. Three layers, ranked passive → active:

| Layer | Mechanism | Cost | Visible when |
|---|---|---|---|
| 1 | Tee installer output to stdout + log file | Free (one `tee`) | `kubectl logs paperclip -c paperclip-shell` |
| 2 | MOTD on SSH login prints last-boot summary (`✓ N installed, ⚠ M failed`) | Free (PAM motd reads log header) | Every SSH session |
| 3 | Telegram alert on any failure via existing `@agent_zero_cc_bot` webhook | ~3 lines `curl` | Within seconds of pod boot |

**Layer 3 is the load-bearing channel.** Reuses `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID` from Infisical (already wired into existing alerting per `frank-gotchas.md`). Alert format mirrors existing ArgoCD notifications style — pod name, failed-package list, `kubectl logs` snippet for triage.

**Success path also signals:** on clean reconcile, MOTD prints a single confirmation line so the operator can immediately tell whether a recent ConfigMap edit applied. No Telegram noise on success.

**Not designed:** no Prometheus exporter, no Grafana panel, no dedicated alert rule. At one-pod scale these are more moving parts than the problem warrants. If/when the pattern is replicated to N>1 shells (or if Layer-3 alerts become noisy), promote to a metric-based alert path.

## Documentation & rollout surface

This change touches four documentation surfaces and one external repo.

### `derio-net/agent-images` (companion repo, separate PR)

```
agent-images/
└── paperclip-shell/                    (NEW)
    ├── Dockerfile                      (FROM agent-shell-base)
    ├── rootfs/
    │   ├── etc/cont-init.d/40-shell-inventory
    │   ├── usr/local/lib/paperclip-shell/install-inventory.sh
    │   ├── usr/local/lib/paperclip-shell/notify-telegram.sh
    │   ├── usr/local/lib/paperclip-shell/install-base-runtimes.sh
    │   └── etc/skel/{.bashrc,.tmux.conf,...}
    └── README.md
```

CI: matrix-build alongside existing children; smoke test under non-root + cap-drop.

### `apps/paperclip/` (this repo)

- `manifests/deployment.yaml` — add second container, `shareProcessNamespace: true`, mount the new PVC + Secret + ConfigMap
- `manifests/pvc-shell-home.yaml` (NEW) — 20 Gi, RWO, longhorn
- `manifests/configmap-shell-inventory.yaml` (NEW) — software inventory
- `manifests/externalsecret-shell-ssh-keys.yaml` (NEW) — ESO referencing same Infisical entries as `agent-ssh-keys`
- `manifests/service-shell.yaml` (NEW) — single mixed TCP+UDP Service on `192.168.55.221`
- `client-setup/laptop/` (NEW) — mirror `apps/secure-agent-pod/client-setup/laptop/`: `~/.ssh/config` snippet, mosh wrapper, README

### CLAUDE.md rules

- `.claude/rules/frank-infrastructure.md` — add row to Frank Cluster Services for `Paperclip Shell (SSH+Mosh) | 192.168.55.221`
- `.claude/rules/frank-gotchas.md` — add any non-obvious patterns discovered during implementation (UID alignment, MixedProtocolLBService quirks, inventory installer edge cases)

### Blog posts (extension, not new posts)

Per `repo-workflows.md` *Layer Fix/Extension Workflow*, this is a retroactive update of the existing `paperclip` layer's posts:

- `blog/content/docs/building/15-paperclip/index.md` — append section: *"Adding a side door: SSH-able shell sidecar."* Cover the why (24/7 workflow, install-on-the-fly), the three-layer install model, the fail-open-with-Telegram visibility design.
- `blog/content/docs/operating/18-paperclip/index.md` — append operational sections: *Connecting via SSH/Mosh*, *Adding/removing tools*, *Reading the install log / interpreting the alert*, *When to bump `paperclip-shell` image vs add to inventory*.

No new building/operating posts. The change is a side door on an existing service, not a new layer.

### README

Run `/update-readme` post-deploy to sync Service Access table (add `192.168.55.221`) and Current Status if applicable.

## Migration plan

Sequence (high level — converted to phased plan in `/vk-plan`):

1. **agent-images PR:** add `paperclip-shell/` directory, Dockerfile, rootfs, smoke test. Merge once CI green.
2. **Frank PR — manifests:** add the new PVC, ConfigMap, Secret (ESO), Service, and the second container in `deployment.yaml`. Empty inventory for first deploy.
3. **First deploy validation:** ArgoCD syncs, Recreate strategy bounces the pod, paperclip container comes up unchanged, paperclip-shell container reaches Ready (sshd listens on 2222), MOTD prints `✓ 0 installed`. SSH from laptop to `192.168.55.221:22` succeeds. `cd /paperclip` shows Paperclip's data.
4. **Inventory population:** add the operator's day-to-day tools to the ConfigMap, commit, run `paperclip-shell-reconcile`, verify all install successfully.
5. **Documentation pass:** update CLAUDE.md rules, blog posts, README. Run `/sync-runbook` if any manual-ops blocks were introduced.
6. **Plan status → Deployed.**

Rollback at any step: revert the frank PR. The standalone Paperclip container is unmodified throughout — reverting only removes the sidecar and its resources. No state loss possible on the Paperclip side.

## Decisions log

- **Sidecar in the existing pod, not a separate Deployment.** RWO PVC + the requirement to share `/paperclip` make the sidecar the only viable shape.
- **New `paperclip-shell` image based on `agent-shell-base`, not modifying upstream Paperclip.** Decouples the shell's upgrade lifecycle from Paperclip's. Eliminates the maintenance treadmill that the recent fork-drop deliberately stepped off.
- **No Ansible.** Wrong tool for one container with a flat tool list; doesn't escape the non-root capability constraint that blocks `apt` regardless. A YAML-driven bash installer in `cont-init.d` does the same job with no new system to learn.
- **Three install layers (image / inventory / interactive).** Image baseline is slow and explicit; ConfigMap inventory is fast and declarative; interactive installs are the acknowledged escape hatch for "try this quickly." Each layer has a clear owner and a clear durability story.
- **Fail-open with Telegram alert.** Fail-closed (CrashLoop on install failure) trades SSH availability for loud failures; for 24/7 operator workflow that trade is wrong. Active alerting via the existing Telegram path provides loud failure without sacrificing availability.
- **One LB IP, mixed TCP+UDP Service.** K8s 1.26+ MixedProtocolLBService GA, supported by Cilium L2 + kube-proxy-replacement. The two-IP pattern in `secure-agent-pod` is historical (mosh added in a separate PR), not principled. Optional follow-up: consolidate `secure-agent-pod` to one IP too.
- **Shared SSH keys with `secure-agent-pod`.** One operator identity; one source of truth in Infisical; ESO reconciles both pods. Rotation is a single edit.
- **`shareProcessNamespace: true`.** Cheap; lets the shell `ps`/`strace`/`lsof` Paperclip's processes when debugging. The minor downside (process list crosses containers) is irrelevant for a single-operator pod.
- **Mosh enabled** (16-port UDP range). Mirrors `secure-agent-pod`'s wiring; no new mechanism. Justified by the same use case (remote SSH over flaky networks).
- **Defer egress restriction.** The existing `cilium-egress.yaml.disabled` indicates the prior author considered it. The shell needs wide egress for mise/cargo/npm/pipx installs; defer until threat model warrants it.

## Out of scope

- **VK decommissioning** (apps/vk-remote, vk-local sidecar in secure-agent-pod). Will remain running through the transition; separate plan when retirement is decided.
- **Authentik forward-auth for Paperclip web UI.** Web UI exposure is unchanged and orthogonal to this plan.
- **Backup policy changes for `paperclip-shell-home`.** Default Longhorn snapshot/backup posture covers it; revisit only if cadence/retention needs differ.
- **Periodic reconciler cron.** The interactive `paperclip-shell-reconcile` covers all real cases at one-pod scale.
- **Drift detection / alerting for inventory deviations.** Only worth adding if the interactive escape hatch becomes a problem in practice.
- **Prometheus/Grafana metrics for shell-side state.** Telegram + MOTD + stdout cover visibility at one-pod scale.
- **Consolidating `secure-agent-pod`'s SSH+Mosh into one IP.** Mentioned as future cleanup; not done here.
- **DNS record for `paperclip-shell.cluster.derio.net`.** Operator can add a `~/.ssh/config` host entry on the laptop side; cluster-side DNS not required.

## Open questions (plan-time investigation)

- **Paperclip container UID:** does upstream's image run as UID 1000? If different, decide between (a) initContainer that chowns `/paperclip` to a shared GID, (b) override Paperclip's `securityContext.runAsUser` to 1000. `fsGroup: 1000` covers most cases but not all.
- **Resource limits for `paperclip-shell`:** initial guess `500m/1Gi` requests, `4000m/8Gi` limits. Refine after first week of operator use.
- **Inventory installer behaviour when a manager binary is missing from the image:** if `mise` somehow isn't present, should the installer fail loudly or skip silently? Pick "fail loudly" — image regression should not silently degrade.
- **MOTD plumbing:** does `agent-shell-base`'s sshd config already enable PAM motd? If not, add to the new image; if yes, just write to the right file.

## Success criteria

- `ssh agent@192.168.55.221` succeeds from the operator's laptop, lands in `/home/agent`, with shell, tmux, mosh, mise, cargo, pipx all on PATH.
- `mosh agent@192.168.55.221` reattaches across network changes; tmux-resurrect restores prior session on pod restart.
- `cd /paperclip` shows the same files Paperclip is reading/writing; concurrent edits work (PVC owned by both via `fsGroup: 1000`).
- Editing `configmap-shell-inventory.yaml` and running `paperclip-shell-reconcile` installs the declared additions without restarting the pod.
- A pod restart preserves: home directory, installed tools, ssh keypairs, dotfiles, tmux sessions (via resurrect).
- A pod restart does NOT preserve anything in the paperclip-shell image's rootfs outside `/home/agent` and `/paperclip` — confirming the boundary.
- An induced inventory failure (e.g., add a non-existent npm package to the inventory) fires a Telegram alert within ~30s of pod boot, sshd remains available, MOTD on next login shows the failure.
- Bumping the upstream Paperclip image SHA does not break the shell or its installed tools.
- Bumping `paperclip-shell` image does not affect the Paperclip container or its data.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Paperclip Shell Sidecar Implementation Plan |  | `docs/superpowers/archived-plans/2026-05-02--orch--paperclip-shell-sidecar/` | — |
