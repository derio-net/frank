# Secure-Agent-Pod — Client Setup

Reference configs and installation steps for the **operator's macOS workstation** and the **pod's interactive shell** (kali container, user `claude`). Mirrors the live configs in the operator's home directory; keep both sides in sync when one changes.

The cluster-side manifests live in `../manifests/`. This directory captures everything *outside* the cluster that the operator runs to actually use the pod day-to-day.

```
client-setup/
├── README.md                           ← this file
├── laptop/
│   ├── wezterm.lua                     → ~/.config/wezterm/wezterm.lua
│   ├── tmux.conf                       → ~/.tmux.conf
│   ├── tmux/color-by-cwd.sh            → ~/.config/tmux/color-by-cwd.sh
│   └── zshrc-snippet.zsh               → append to ~/.zshrc (or modular include)
└── pod/
    ├── tmux.conf                       → /home/claude/.tmux.conf
    ├── tmux/color-by-cwd.sh            → /home/claude/.config/tmux/color-by-cwd.sh
    └── bashrc-snippet.bash             → append to /home/claude/.bashrc
```

The pod paths are inside the kali container; the home directory is backed by `pvc-agent-home` (RWO PersistentVolumeClaim) so anything you install there survives pod restarts. See `../manifests/pvc-agent-home.yaml` for the volume spec.

---

## Laptop installation (macOS)

Prerequisites: WezTerm, tmux 3.6+, mosh 1.4+, netcat (`/usr/bin/nc` ships with macOS). Homebrew installs all of these via `brew install wezterm tmux mosh`.

```bash
# 1. Configs
mkdir -p ~/.config/wezterm ~/.config/tmux
cp laptop/wezterm.lua          ~/.config/wezterm/wezterm.lua
cp laptop/tmux.conf            ~/.tmux.conf
cp laptop/tmux/color-by-cwd.sh ~/.config/tmux/color-by-cwd.sh
chmod +x ~/.config/tmux/color-by-cwd.sh

# 2. Zsh chpwd hook (re-colors tmux pane on cd). Append to your existing
#    ~/.zshrc, or to whichever modular include file you use.
cat laptop/zshrc-snippet.zsh >> ~/.zshrc

# 3. SSH key for the pod. Edit REMOTE_KEY in wezterm.lua to point at the
#    private key that matches the public key mounted on the pod via the
#    agent-ssh-keys Secret (see ../manifests/deployment.yaml; the public
#    half is mounted read-only at /etc/ssh-keys inside the container).

# 4. Reload shells / WezTerm
exec zsh                       # to pick up the chpwd hook in current shell
# WezTerm hot-reloads its config when wezterm.lua changes; for the gui-startup
# hook to fire (which spawns the local + frank workspaces), CMD+Q WezTerm
# fully and relaunch. gui-startup only fires on cold start.
```

After relaunch, WezTerm will spawn two workspaces:

- **`local`** (CMD+1) — local tmux session `claude-local`.
- **`frank`** (CMD+2) — mosh session through the pod, dropping into a tmux session `claude-frank-secure-pod`.

If anything in the mosh handshake fails, the pane stays open at a bare `zsh -f` prompt with the full output tee'd to `/tmp/wezterm-mosh.log`. Read that log for the specific failure mode.

---

## Pod installation (kali container, user `claude`)

The pod's home directory is on a PersistentVolumeClaim, so files you copy here survive `kubectl delete pod` / image bumps. Two install paths:

### Path A — copy from your laptop while connected

Once you have a working SSH or mosh session into the pod (substitute your
own key path for `<your-key>`):

```bash
KEY=~/.ssh/<your-key>

# From laptop: stage the files into the pod
scp -i $KEY pod/tmux.conf            claude@192.168.55.215:/home/claude/.tmux.conf
ssh -i $KEY claude@192.168.55.215 mkdir -p /home/claude/.config/tmux
scp -i $KEY pod/tmux/color-by-cwd.sh claude@192.168.55.215:/home/claude/.config/tmux/color-by-cwd.sh
ssh -i $KEY claude@192.168.55.215 chmod +x /home/claude/.config/tmux/color-by-cwd.sh

# Append the bash hook (from the laptop, into the pod's bashrc)
ssh -i $KEY claude@192.168.55.215 'cat >> /home/claude/.bashrc' < pod/bashrc-snippet.bash
```

### Path B — clone the frank repo inside the pod

```bash
# Inside the pod (after SSH/mosh in)
cd ~/repos                                            # adjust to your clone location
git clone <frank-repo-url>                            # the Git remote for this repo
cd frank/apps/secure-agent-pod/client-setup/pod
mkdir -p ~/.config/tmux
cp tmux.conf            ~/.tmux.conf
cp tmux/color-by-cwd.sh ~/.config/tmux/color-by-cwd.sh
chmod +x ~/.config/tmux/color-by-cwd.sh
cat bashrc-snippet.bash >> ~/.bashrc
```

### Reload

```bash
# Inside any pod shell:
source ~/.bashrc                       # picks up the cd-wrapper for color-by-cwd
tmux source ~/.tmux.conf               # if a tmux server is already running
# Or: detach and reattach (mosh stays connected):
#   tmux detach
#   tmux attach -t claude-frank-secure-pod
```

The pod's tmux config differs from the laptop's in two visible ways:

- The status bar shows a red **`REMOTE:hostname`** banner so you can never confuse a pod-side pane with a laptop-side one at a glance.
- It has the same key-bindings (`Prefix S`, `Prefix |`, `Prefix Space`, `Prefix M-Space`, `Prefix Ctrl+6`, `Prefix Ctrl+Alt+6`, `Prefix r`) but no zsh4humans warnings — the pod runs bash, not z4h.

---

## Verification — both sides

### Laptop

```bash
# WezTerm parses the lua cleanly
wezterm --config-file ~/.config/wezterm/wezterm.lua show-keys >/dev/null && echo OK

# tmux 3.6+ and mosh 1.4+ on PATH
tmux -V; mosh --version | head -1

# Layout bindings registered (after attaching to claude-local)
tmux list-keys -T prefix | grep -E '^bind-key.*-T prefix\s+(C-6|C-M-6|S |\| |Space|M-Space|r )\b'

# nc on PATH (mosh's ProxyCommand needs it)
which nc                       # expect /usr/bin/nc
```

### Pod

```bash
# Inside the pod
tmux -V                        # expect 3.x
mosh-server --version | head -1
echo "$LANG / $LC_ALL"         # expect C.UTF-8 / C.UTF-8 (set in the image)
ls -la ~/.config/tmux/color-by-cwd.sh

# Reload tmux + bash and try splitting two panes in different cwds:
#   Prefix |    (split horizontally)
#   cd /tmp     (in the new pane)
# Each pane should now have its own bg color.
```

If a pane stays uncolored: run `~/.config/tmux/color-by-cwd.sh "$PWD" "$TMUX_PANE"` directly to confirm the script works in isolation. If it does, the trigger (chpwd / cd-wrapper / tmux hook) isn't firing — re-source the relevant rc file.

---

## Architecture context

The pod is fronted by **two separate Cilium L2 LoadBalancer IPs** by design (Deployment Deviation #4 in the parent plan):

- **`192.168.55.215`** — TCP/22, the SSH service.
- **`192.168.55.219`** — UDP/60000-60015, the mosh service.

The `wezterm.lua` knows about both: it tunnels SSH bytes through `nc 192.168.55.215 22` (via `-o ProxyCommand=`), and points mosh's UDP positional at `192.168.55.219`. If the cluster ever consolidates these onto a single shared LB IP via `lbipam.cilium.io/sharing-key`, the simplified invocation lives in the parent plan's "Appendix" section.

For the full debug story behind why each `-o` flag and env-var indirection is necessary, see `../../../docs/superpowers/plans/2026-04-26--agents--secure-pod-tmux-mosh.md` (Appendix: Client-Side Configuration).
