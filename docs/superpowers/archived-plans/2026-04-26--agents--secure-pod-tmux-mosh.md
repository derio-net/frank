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

- [x] **Step 1: Open a PR for the manifest changes**  *(PR #125)*

Branch: `feat/agents-mosh-service`. Title: `feat(agents): mosh UDP service + tmux availability`. Body summarises the deviation from the standard layer workflow (fix/extension of layer 12, retroactive plan). The bump PR #124 is independent — they can merge in either order without breakage:
- Bump-only first: image has mosh installed but no UDP service yet → mosh would fail to reach pod, SSH unaffected.
- Service-only first: UDP routes to a pod that does not yet have mosh-server → harmless, no listeners on those ports.

- [x] **Step 2: Operator merges both PRs**  *(#124 → a1a21b1, #125 → 88a4de7)*

Once both #124 (image bump) and the manifest PR are merged, ArgoCD `secure-agent-pod` Application syncs. Pod is recreated (`strategy: Recreate` due to RWO PVC).

---

## Phase 3: Verify [manual]
**Depends on:** Phase 2

<!-- manual: requires shelling into the pod after rollout -->

### Task 1: Confirm tools are present

- [x] **Step 1: `kubectl exec` checks**  *(tmux 3.6, mosh 1.4.0, LANG/LC_ALL=C.UTF-8)*

```bash
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- tmux -V
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- mosh-server --version | head -1
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- printenv LANG LC_ALL
```

Expected: `tmux 3.x`, `mosh-server (mosh) 1.4.x`, `C.UTF-8` for both env vars.

### Task 2: Confirm Cilium L2 LB advertises mosh IP

- [x] **Step 1: Service status**  *(EXTERNAL-IP=192.168.55.219, 4×UDP ports allocated)*

```bash
kubectl get svc -n secure-agent-pod secure-agent-mosh -o wide
# EXTERNAL-IP should be 192.168.55.219
kubectl get ciliuml2announcementpolicy -A 2>/dev/null
```

Expected: `EXTERNAL-IP = 192.168.55.219`, four UDP ports listed.

### Task 3: End-to-end mosh from a client

- [x] **Step 1: Connect from a host on the lab LAN**

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

- [x] **Step 1: Add a "Persistent shells with mosh + tmux" section to `blog/content/docs/operating/14-secure-agent-pod/index.md`**

Cover: client invocation (the `mosh --ssh="…" --server="…" <udp-ip>` form), why SSH and UDP are on different IPs (separate Service objects, no IP sharing), the 4-port cap, and a starter tmux config snippet.

### Task 2: Update building blog post (passing mention)

- [x] **Step 1: One-line correction in `blog/content/docs/building/21-secure-agent-pod/index.md`**

Mention that the apt block now includes `tmux mosh locales-all` and that the deployment has a sibling mosh Service. No deep dive — this is a small extension, not a new layer.

### Task 3: Update README service table

- [x] **Step 1: Run `/update-readme`**

Adds `192.168.55.219 — Secure Agent Pod (Mosh)` to the Service Access table. Confirm the diff before committing.

### Task 4: Sync runbook (only if needed)

- [x] **Step 1: Run `/sync-runbook`**

This plan has no `# manual-operation` blocks, so the runbook should be unchanged. Run anyway to confirm zero diff and avoid drift.

### Task 5: Update gotchas (if Cilium L2 UDP turned out to be quirky)

- [-] **Step 1: Append to `.claude/rules/frank-gotchas.md` if applicable** <!-- skipped — Cilium L2 UDP worked first try; all 10 documented failure modes were client-side (ssh/mosh/zsh/wezterm/tmux), none cluster-side -->

Only if Phase 3 surfaced something non-obvious (e.g., Cilium L2 UDP needing an explicit announcement-policy update, or mosh-server failing under non-root + capability drop).

### Task 6: Set plan status

- [x] **Step 1: Edit `**Status:**` to `Deployed`**

Once Phases 1-4 are all checked off and verification passed.

---

## Phase 5: Post-deploy tuning — 16 ports + 1h mosh timeout [agentic]
**Depends on:** Phase 3

<!-- Tracking: filed during Phase 3 review when the operator asked about the 4-port cap. -->

After verification, the operator surfaced the 4-port-cap edge case: mosh's default `MOSH_SERVER_NETWORK_TMOUT` is 168 hours (7 days), so an ungraceful disconnect leaves a `mosh-server` process squatting its UDP port for a week. With only 4 ports, four bad disconnects in a week could lock new sessions out until the oldest aged out (or someone `kubectl exec ... pkill mosh-server`).

Fix has two independent levers; we apply both:

1. **Lower the timeout** (`MOSH_SERVER_NETWORK_TMOUT=3600` — 1h) so stuck servers reap fast.
2. **Bump port count** from 4 to 16 to give comfortable headroom even before the timeout reaps.

### Task 1: Expand the Service to 16 ports

- [x] **Step 1: Edit `apps/secure-agent-pod/manifests/service-mosh.yaml`**

Add ports 60004–60015 in the same flow-style format. Update the comment block to reference `60000:60015` and the timeout-env mitigation.

### Task 2: Add timeout env + matching containerPorts

- [x] **Step 1: Edit `apps/secure-agent-pod/manifests/deployment.yaml`**

In the kali container: add `MOSH_SERVER_NETWORK_TMOUT=3600` to `env:`, and add containerPort entries 60004–60015 (UDP) to the `ports:` block. Convert all mosh containerPort entries to flow-style for readability.

### Task 3: Land + roll

- [x] **Step 1: Open PR `feat(agents): mosh tuning — 16 ports + 1h timeout`**
- [x] **Step 2: Operator merges; ArgoCD syncs; pod recreates** (env-var change forces a Recreate; expected ~30-60s of unavailability)

### Task 4: Re-verify

- [x] **Step 1: Confirm new pod has the env var**

```bash
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- printenv MOSH_SERVER_NETWORK_TMOUT
# expect: 3600
```

- [x] **Step 2: Confirm Service has 16 UDP ports**

```bash
kubectl get svc -n secure-agent-pod secure-agent-mosh -o jsonpath='{.spec.ports[*].port}' | tr ' ' '\n' | wc -l
# expect: 16
```

---

## Deployment Deviations

The standard layer workflow (`docs/superpowers/rules/repo-workflows.md`) calls for brainstorm → plan → execute → deploy → blog → README → runbook. This plan deviates as follows:

1. **Retroactive authorship.** The Dockerfile change and Frank manifests were authored before the plan, on the operator's call ("we'll do this change and then retroactively create a superpowers plan"). The plan captures intent and post-deploy obligations rather than driving execution from scratch.
2. **Direct push to `agent-images:main` without PR review.** Commit `eb6ae08` was pushed directly; the safety guard flagged this and the operator chose "let it stand". Future tmux/mosh-style image-only changes should go through a PR for traceability.
3. **No new blog post.** Per the fix/extension rule, the existing operating post (14-secure-agent-pod) is extended in place; the building post (21-secure-agent-pod) gets a passing mention. No standalone post.
4. **Mosh client UX trade-off.** SSH and mosh-UDP are on separate LB IPs (215 vs 219), so the client invocation needs explicit `--ssh="…"` and `<udp-ip>` arguments. A future iteration could use `lbipam.cilium.io/sharing-key` to put both Services on a single IP, restoring `mosh user@host` ergonomics — but that requires touching `service-ssh.yaml`, which the operator deferred.
5. **Initial 4-port cap revised post-deploy.** The original plan exposed UDP 60000-60003 (4 ports). During Phase 3 review the operator flagged the 7-day stuck-server window; Phase 5 bumps the range to 60000-60015 (16 ports) and sets `MOSH_SERVER_NETWORK_TMOUT=3600`. Both changes ride a follow-up PR.

---

## Appendix: Client-Side Configuration & Debug Journey

<!-- Reference material captured live during the first end-to-end connect from
     the operator's MacBook on 2026-04-26 / 2026-04-27. The connection failed
     in nine consecutive ways before working; each failure exposed a specific
     boundary between OpenSSH, mosh.pl (a Perl wrapper), tmux, the macOS
     terminal, and zsh. The Debug Journey section captures each one in turn
     so the next person on this stack can recognize the symptoms.
     Phase 4 Task 1 should pull from this when extending the operating blog
     post. -->

This appendix has two parts. **Part 1** is reference material: the resolved configuration, where it lives, how to install it. **Part 2** is the debug journey — what each error along the way taught us about the boundary between OpenSSH, mosh, tmux, the terminal, and zsh. Read part 2 if you want to understand *why* the configs look the way they do; nearly every flag is anchored to a real upstream behavior.

The cluster manifests in this plan are only half the story. The SSH/UDP-on-separate-LB-IPs design (Deployment Deviation #4) pushes real complexity onto the client invocation, and the operator's daily-use shell stack (zsh4humans + tmux + WezTerm) introduces another layer of "convenient defaults that fight us in this scripted-spawn context."

---

## Part 1: Resolved configuration

### File map

The live configs live in `apps/secure-agent-pod/client-setup/` and are kept in sync with the operator's `~`. See that directory's README for installation instructions covering both the laptop and the pod.

| File in repo | Installs at | Purpose |
|---|---|---|
| `laptop/wezterm.lua` | `~/.config/wezterm/wezterm.lua` | Spawns local + remote workspaces; mosh wrapper with diagnostic-on-failure shell. |
| `laptop/tmux.conf` | `~/.tmux.conf` | Splits, layout bindings, prefix indicator, per-pane bg coloring, z4h disclaimer. |
| `laptop/tmux/color-by-cwd.sh` | `~/.config/tmux/color-by-cwd.sh` | Maps cwd → bg color via `select-pane -P`. |
| `laptop/zshrc-snippet.zsh` | append to `~/.zshrc` | Re-color on `cd` via the chpwd hook. |
| `pod/tmux.conf` | `/home/claude/.tmux.conf` | REMOTE-banner status bar; same bindings as laptop. |
| `pod/tmux/color-by-cwd.sh` | `/home/claude/.config/tmux/color-by-cwd.sh` | Identical to laptop's; matches both `~/Docs/projects/DERIO_NET/*` and `~/repos/*`. |
| `pod/bashrc-snippet.bash` | append to `/home/claude/.bashrc` | Bash equivalent of the chpwd hook (cd/pushd/popd wrappers). |

### Canonical mosh invocation

Minimum end-to-end working command. Everything in the wezterm.lua wrapper is plumbing around this:

```sh
export MOSH_SSH_PROXY='nc 192.168.55.215 22'
SHELL=/bin/sh mosh --experimental-remote-ip=local \
  --ssh='ssh -l claude -i ~/.ssh/your_private_key \
         -o ControlMaster=no -o ControlPath=none -o ControlPersist=no \
         -o ProxyCommand=$MOSH_SSH_PROXY' \
  --server='LC_ALL=C.UTF-8 mosh-server new -p 60000:60015' \
  192.168.55.219 -- \
  tmux new-session -A -s claude-frank-secure-pod
```

### Why each non-obvious flag

Each item below is a default we deliberately override, anchored to the upstream behavior that motivates the override. None of these are "tries until it works"; each is structurally load-bearing.

1. **`MOSH_SSH_PROXY` env-var indirection.** `mosh.pl` splits the `--ssh=` value on whitespace with naive `split(' ', …)`, which would shred a literal `ProxyCommand=nc 192.168.55.215 22` into separate broken tokens. The env-var indirection keeps it a single token through both zsh and mosh; ssh expands it when it later forks the ProxyCommand shell.

2. **`-o ProxyCommand=` instead of `-o HostName=` to redirect TCP to `.215`.** `HostName=` poisons `ssh -G`, which `mosh.pl` reads to determine the canonical hostname for the UDP socket — the seemingly-correct "redirect TCP, leave positional UDP" trick ends up making mosh send UDP to `.215` too. ProxyCommand is invisible to `ssh -G`; the positional `.219` survives as the UDP target.

3. **`-o ControlMaster=no -o ControlPath=none -o ControlPersist=no` (the triple).** The operator's `~/.ssh/config` has `ControlMaster auto` with a 10-min `ControlPersist`. mosh's built-in `-S none -o ControlPath=none` doesn't fully suppress this on OpenSSH 10.2+; an existing master gets reused via the auto-mux discovery path, mosh-server's stdout vanishes into the mux channel, and `mosh.pl` dies with "Did not find mosh server startup message". All three overrides together force a fresh, unmultiplexed connection.

4. **`--experimental-remote-ip=local`.** Default `proxy` mode reads peer info from the ProxyCommand connection state — plain `nc` doesn't expose any. `remote` mode reads `$SSH_CONNECTION` on the pod, which reports the pod's internal `10.244.x.x` cluster IP (the pod has no way to know it's behind an LB). `local` uses the locally-resolved positional arg, i.e. the LB IP we actually want.

5. **`SHELL=/bin/sh` prefix on the mosh invocation.** OpenSSH picks the ProxyCommand shell from `$SHELL`, falling back to `/bin/sh`. On macOS `$SHELL` is `/bin/zsh`, and zsh **does not word-split unquoted variable expansions by default** — so `zsh -c '$MOSH_SSH_PROXY'` treats `nc 192.168.55.215 22` as a single command name and dies with "command not found". `/bin/sh` word-splits on `IFS`, so the same expansion runs `nc` with two args. The override is scoped to this one mosh run; it doesn't leak.

6. **`LC_ALL=C.UTF-8` prefixed onto `--server=`.** Phase 1 sets `ENV LANG/LC_ALL=C.UTF-8` in the image, but sshd's non-interactive command channel doesn't always forward those (depends on PAM config and `AcceptEnv`). Scoping the assignment to the `mosh-server` invocation is universal and needs no sshd-side cooperation. Without it, mosh-server refuses to start ("mosh-server needs a UTF-8 native locale to run").

7. **`mosh-server new -p 60000:60015` (explicit port range).** Default `mosh-server new` picks uniformly from 60000-61000, giving a ~1.6% hit rate against the 16 ports the Service publishes. Constraining the server matches the published range exactly.

8. **`exec /bin/zsh -f` (no rc files) on the failure-path shell.** zsh4humans auto-starts tmux on every login-shell startup and clears the alt-screen on attach, erasing mosh's failure message the moment a debug shell launches via `exec $SHELL -l`. Skipping `.zshrc` keeps the diagnostic visible. The companion `tee -a /tmp/wezterm-mosh.log` is belt-and-suspenders for cases where the screen still ends up wiped.

9. **WezTerm `disable_default_key_bindings = true` + add-back of just clipboard and workspace switching.** WezTerm's default keytable grabs `Ctrl+Shift+<digit>` for tab activation, which collides with tmux's `C-6` binding (`Ctrl+Shift+6` is the only way to produce the byte 0x1E that tmux maps to `C-6`). Disabling all defaults means tmux owns every Ctrl/Shift/Alt combo; we explicitly add back Cmd+C/Cmd+V (clipboard) and CMD+1/2/Shift+S (workspace switching).

### tmux configuration (laptop and pod)

The tmux configs add three pieces beyond the base styling:

**(a) Pane splits with normalized layouts.** `Prefix S` and `Prefix |` split + even-out the resulting row/column. Defaults `Prefix "` and `Prefix %` are kept alongside.

**(b) Two 6-pane grid bindings**: `Prefix Ctrl+6` builds a 2-column × 3-row grid; `Prefix Ctrl+Alt+6` builds a 3-column × 2-row grid. Two non-obvious traps live here:

- **Quote trap.** `tmux bind-key X cmd1 \; cmd2 \; cmd3` chains commands. Wrapping the chain in single quotes (`bind-key X 'cmd1 \; cmd2'`) makes tmux treat the whole blob as one literal command name; the binding silently no-ops, *and* `tmux list-keys` still shows it as if it parsed (because list-keys re-emits the bound value with `\;` regardless of how it was actually parsed). The bug is invisible until you actually trigger the binding.
- **Pane renumbering trap.** tmux renumbers panes spatially after every split, in left-to-right / top-to-bottom order. So `select-pane -t .1` doesn't keep pointing at "the second pane created" — after splitting pane 0, the new bottom pane becomes index 1 and the *original* pane 1 shifts to index 2. The bindings use directional selection (`-L`, `-R`, `-U`, `-D`) instead, which is stable across renumbering because it picks the spatial neighbour of the active pane.

**(c) Per-pane background coloring by cwd.** `~/.config/tmux/color-by-cwd.sh` maps cwd → color via `select-pane -t <pane> -P 'bg=…,fg=default'`. Each pane carries its own color independently. Triggers:

- `chpwd` (zsh) / `cd`-wrapper (bash) — pane's cwd changed.
- `after-split-window`, `after-new-window`, `after-new-session` — pane was just created.

`after-select-pane` is **deliberately not** in the hook list: the script's own `select-pane -P` call would re-fire that hook and loop infinitely, manifesting as the active pane's cursor bouncing between panes. Pane styles persist once set, so re-coloring on focus change adds nothing but the loop.

Two API/options-tree subtleties:

- **`pane-style` doesn't exist as a tmux option** in 3.6 — only `window-style` and `window-active-style`, both window-scoped. Per-pane styling lives in pane runtime state, not the options tree, and is set via `select-pane -P style`. `set-option -p pane-style` returns "invalid option".
- **`pane_style` format variable doesn't reflect `select-pane -P` settings** — visual inspection is the verification, not format introspection.

**(d) Status-bar prefix indicator.** `set -g status-right "#{?client_prefix,#[bg=red,bold] PREFIX ,}#H:#M"`. tmux's `client_prefix` format variable evaluates true only while the prefix-key table is active, so a red badge appears the moment you press `C-b` and disappears as soon as the next key fires (or the prefix times out). Critical debugging aid for "is tmux even seeing my keypress?" — without it, you have no way to tell whether the prefix was registered before pressing the next key.

**(e) z4h pitfall.** zsh4humans ships its own tmux config at `~/.cache/zsh4humans/v5/zsh4humans/.tmux.conf`. That config calls `unbind -a` and sets `prefix None`, so every binding in `~/.tmux.conf` is invisible inside z4h's auto-tmux. The file's header documents this and points the reader at the system tmux session (`claude-local`) that WezTerm spawns directly via `tmux new-session -A -s claude-local`.

---

## Part 2: Debug journey — what each error taught us

This section walks through the failures in the order they happened, with the error messages and the structural cause behind each. It's the most useful part for anyone hitting a similar setup; almost every error has a "but it worked when I did X manually" twin elsewhere in the stack, and naming the boundaries explicitly is what lets you stop guessing.

### Round 1 — WezTerm spawn produces a vanishing pane

> **Symptom.** WezTerm launches but the pane that should hold the mosh session closes instantly. No error, no log.
>
> **Cause.** WezTerm runs `mosh` directly via `mux.spawn_window { args = {...} }`. When mosh exits (success or failure), there's nothing left in the pane and tmux closes it. A failure mode silently shut the pane before any output could be read.
>
> **Fix.** Wrap the mosh invocation in `/bin/zsh -l -c '…'` and on failure `exec /bin/zsh -f` so the pane stays alive at a debug shell. Tee everything to `/tmp/wezterm-mosh.log` for post-mortem.

The lesson here is to **never let a `spawn_window` exec a single child that's allowed to die quickly** — wrap in a shell that has a definite "fall through to interactive prompt" path so failures surface.

### Round 2 — The other mosh window is "missing"

> **Symptom.** The local-tmux pane shows up; the frank-mosh pane is "not there".
>
> **Cause.** The frank pane was being spawned into `workspace = 'frank'`, while `default_workspace = 'local'` is what WezTerm displays on cold start. The pane existed; it was just in a hidden workspace.
>
> **Fix.** None at the config level — `CMD+2` reveals it. But it is genuinely worth knowing: WezTerm shows only one workspace at a time, and "the other window doesn't open" can mean "you haven't switched to that workspace yet."

### Round 3 — `mosh-server` not found / locale errors / stripped PATH

> **Symptom.** `mosh: command not found` when WezTerm spawns from Finder/Dock, but `mosh` works fine in a regular terminal.
>
> **Cause.** macOS launchd starts WezTerm with a stripped PATH (`/usr/bin:/bin:/usr/sbin:/sbin`). Homebrew binaries (`/opt/homebrew/bin`, `/usr/local/bin`) aren't on it.
>
> **Fix.** `config.set_environment_variables = { PATH = '/opt/homebrew/bin:/usr/local/bin:' .. os.getenv('PATH') }` in `wezterm.lua`. The lua's `os.getenv('PATH')` runs in the wezterm process so it sees launchd's PATH; we prepend the Homebrew dirs explicitly.

The wider lesson: **GUI-launched apps on macOS inherit launchd's environment, not your shell's**. Anything you thought was "on PATH" because you can run it from Terminal.app may not be there. Always check `os.getenv('PATH')` early when wiring up GUI-side automation.

### Round 4 — `Nothing received from server on UDP port 60001`

> **Symptom.** SSH bootstrap works; mosh client prints `Nothing received from server on UDP port 60001` and exits.
>
> **Cause.** Two parts: the cluster exposes UDP on a different LB IP (`192.168.55.219`) than SSH (`192.168.55.215`), AND `mosh-server new` defaults to picking a random port from `60000-61000` while only `60000-60015` are published.
>
> **Fix.** Two-part:
> - Pass `192.168.55.219` (UDP IP) as the positional to `mosh`, route SSH bytes through `nc 192.168.55.215 22` via ProxyCommand.
> - Constrain the server: `--server='mosh-server new -p 60000:60015'`.

This is the first place the SSH/UDP separation bites the client. The matching cluster-side commit is `88a4de7` (PR #125) plus tuning in `a521b5f` (PR #126).

### Round 5 — `mosh-server` ran but UDP went to the wrong IP

> **Symptom.** With the SSH/UDP IPs split, mosh dies with `Nothing received from server on UDP port 60000` again. Tracing shows mosh tried UDP to `192.168.55.215` (the SSH IP), not `.219` (the UDP IP).
>
> **Cause.** The first attempt at "redirect TCP to .215, leave positional .219" used `-o HostName=192.168.55.215`. But `mosh.pl` calls `ssh -G <host>` to find the canonical hostname for the UDP socket, and `HostName=` overrides what `ssh -G` reports. So mosh ended up using `.215` for both TCP and UDP.
>
> **Fix.** `-o ProxyCommand="nc 192.168.55.215 22"` instead. ProxyCommand is invisible to `ssh -G` — ssh still reports the positional `.219` as `hostname`, while the actual TCP bytes tunnel through `nc` to `.215`.

The lesson: **`ssh -G` is treated by mosh.pl as a hostname-resolution oracle**. Any `-o` that influences `ssh -G`'s hostname output also influences mosh's UDP target. Tools that override SSH connection routing without touching `HostName` (i.e., ProxyCommand) bypass this.

### Round 6 — `--ssh=` wouldn't accept `ProxyCommand=nc 192.168.55.215 22`

> **Symptom.** `mosh: ssh: invalid argument`-style errors, or the ProxyCommand value getting split across multiple ssh args.
>
> **Cause.** `mosh.pl` splits the `--ssh=` value on whitespace with naive `split(' ', …)`. A literal `ProxyCommand=nc 192.168.55.215 22` becomes three separate tokens. ssh sees `-o ProxyCommand=nc` (one option), then `192.168.55.215` and `22` as stray positional args.
>
> **Fix.** Stash the proxy command in an env var: `MOSH_SSH_PROXY='nc 192.168.55.215 22'`, then refer to it as literal `$MOSH_SSH_PROXY` (single-quoted in the lua so it doesn't get expanded prematurely). mosh splits the --ssh value on whitespace, but `$MOSH_SSH_PROXY` is one token. ssh receives `-o ProxyCommand=$MOSH_SSH_PROXY` and expands the variable when it later execs the ProxyCommand shell.

There are many tools in this category — they accept a "command string" that they re-tokenize themselves with rules different from a real shell. Any time you have to put a multi-word value into a single token, **env-var indirection followed by deferred shell expansion** is the universal trick.

### Round 7 — `Did not find remote IP address (is SSH ProxyCommand disabled?)`

> **Symptom.** SSH bootstrap works; mosh dies with `Did not find remote IP address (is SSH ProxyCommand disabled?)` before the UDP phase.
>
> **Cause.** mosh's default `--experimental-remote-ip=proxy` mode tries to extract the peer IP from the SSH ProxyCommand connection state. Plain `nc` doesn't expose any (it's a dumb TCP relay), so mosh has no IP to use.
>
> **Fix.** `--experimental-remote-ip=local`. mosh uses the locally-resolved positional arg (`192.168.55.219`) as the UDP target. The other option, `=remote`, asks the server-side `mosh-server` for *its* IP — but that returns the pod's internal `10.244.x.x` cluster IP, unreachable from outside the LB.

The pattern: **the three modes pick different IPs in different places**. `proxy` reads the SSH ProxyCommand's connection info, `remote` reads `$SSH_CONNECTION` on the server, `local` uses the locally-resolved positional. For LoadBalancer-fronted services, only `local` lands on a routable address.

### Round 8 — `mosh-server needs a UTF-8 native locale to run`

> **Symptom.** SSH connects; the bootstrap command runs; the SSH connection closes with `Connection closed by UNKNOWN port 65535` and mosh dies with "Did not find mosh server startup message". When run by hand via `kubectl exec`, mosh-server prints `mosh-server needs a UTF-8 native locale to run` and exits.
>
> **Cause.** sshd's non-interactive command channel doesn't propagate the operator's local `LANG`/`LC_ALL`. Even though the image bakes in `ENV LANG=C.UTF-8 LC_ALL=C.UTF-8` (Phase 1), those don't always reach the sshd-spawned command — depends on PAM config and `AcceptEnv` whitelisting on the server side.
>
> **Fix.** Prepend the assignment directly to the remote command: `--server='LC_ALL=C.UTF-8 mosh-server new -p 60000:60015'`. sshd runs that string via the user's login shell, which interprets `LC_ALL=…` as a one-shot env scoped to the next command. Universal; no sshd-side change needed.

### Round 9 — SSH multiplex master eating mosh's bootstrap output

> **Symptom.** First connect after WezTerm restart works; subsequent connects fail with `Did not find mosh server startup message`. Sometimes works, sometimes doesn't — irreproducibly.
>
> **Cause.** The operator's `~/.ssh/config` has `ControlMaster auto` with a 10-min `ControlPersist`. The first SSH connect creates a master socket; subsequent connects within 10 minutes ride that master. mosh's built-in `-S none -o ControlPath=none` was supposed to disable this, but on OpenSSH 10.2+ the **auto-mux discovery path** ignores `ControlPath=none` for *existing* masters — it only honors it for *creating* a new one. mosh-server's stdout gets routed through the master's mux channel, mosh.pl never sees the `MOSH CONNECT` line, and dies.
>
> **Fix.** All three: `-o ControlMaster=no -o ControlPath=none -o ControlPersist=no`. Each disables a different layer of the mux machinery; together they force a fresh, unmultiplexed connection every time.

The wider lesson: **OpenSSH 10's auto-mux discovery is more aggressive than 9.x's**. Anything that worked with `-o ControlPath=none` on 9.x may need the full triple on 10.2+. This is also why intermittent "it worked an hour ago" failures emerge for tooling that runs ssh under different shells: an interactively-created master gets reused by the script later.

### Round 10 — `zsh:1: command not found: nc 192.168.55.215 22`

> **Symptom.** With everything else fixed, the final wezterm-spawned mosh fails with this exact zsh-prefixed error. The whole `nc 192.168.55.215 22` is treated as a single command name.
>
> **Cause.** ssh runs ProxyCommand by execing `$SHELL -c "$proxy_value"`, falling back to `/bin/sh`. On macOS `$SHELL` is `/bin/zsh`. **zsh does not word-split unquoted variable expansions by default** (it considers the implicit-split-on-IFS behavior of POSIX sh to be a footgun). So `zsh -c '$MOSH_SSH_PROXY'` treats the whole expanded string as one literal word — the command name `nc 192.168.55.215 22`. /bin/sh, by contrast, *does* word-split.
>
> **Fix.** `SHELL=/bin/sh mosh …` — scoped to the mosh invocation. mosh inherits it, ssh inherits it from mosh, ssh execs `/bin/sh -c "$MOSH_SSH_PROXY"`, /bin/sh word-splits, nc runs.

This is the most fundamental fix in the chain because it's the boundary where two different shells with two different rules meet. The fact that this only surfaced *after* Round 9 disabled multiplexing is itself instructive: until then, an interactively-created master (from a manual `ssh` probe, where the calling shell expanded the env var *before* ssh saw it) was hiding the broken ProxyCommand path.

### What surfaced "in passing" during all this

A handful of tmux/wezterm issues showed up alongside the mosh debugging:

- **WezTerm's `Ctrl+Shift+6` default → ActivateTab(5)** intercepted the exact keystroke needed to send `C-6` to tmux. Fixed by `disable_default_key_bindings = true`.
- **tmux's quote-trap and pane-renumbering** broke our 6-pane layout bindings until we stopped wrapping chains in single quotes and switched from `select-pane -t .N` to directional `-L/-U`.
- **z4h auto-tmux clears the alt-screen on attach**, erasing mosh's failure output. Solved by `exec /bin/zsh -f` (no rc files, no z4h) on the failure path.
- **`pane-style` is not a real option in tmux 3.6**, even though `set-option -p pane-style` *looks* like it should work. Per-pane styling is set via `select-pane -P style` and lives in pane runtime state, not the options tree.
- **`after-select-pane` hook + `select-pane -P` form a feedback loop**, manifesting as the active pane's cursor bouncing between panes. Removing that hook (per-pane styles persist anyway, no need to re-color on focus change) breaks the loop.

---

## When the architecture changes

If Deployment Deviation #4 is ever implemented (SSH and mosh on a single LB IP via `lbipam.cilium.io/sharing-key`), most of the client-side complexity collapses:

```sh
mosh --ssh='ssh -l claude -i ~/.ssh/your_private_key \
            -o ControlMaster=no -o ControlPath=none -o ControlPersist=no' \
     --server='LC_ALL=C.UTF-8 mosh-server new -p 60000:60015' \
     <single-ip> -- tmux new-session -A -s claude-frank-secure-pod
```

The `MOSH_SSH_PROXY`/ProxyCommand machinery, `--experimental-remote-ip=local`, and `SHELL=/bin/sh` all go away — the env-var indirection and zsh word-split workaround were only there to support the ProxyCommand. The locale prefix (#6), the port-range constraint (#7), the multiplexer overrides (#3), and `tmux new-session -A` all stay regardless of how SSH/UDP are fronted, because they address concerns orthogonal to the LB topology.
