local wezterm = require 'wezterm'
local config = wezterm.config_builder()

config.color_scheme = 'Tokyo Night'
config.font = wezterm.font('JetBrains Mono')
config.font_size = 13.0
config.enable_tab_bar = true
config.use_fancy_tab_bar = false
config.window_decorations = "RESIZE"

-- WezTerk spawns processes with a minimal PATH; surface Homebrew (Intel + Apple Silicon)
-- so `tmux`, `mosh`, etc. resolve when launched via `mux.spawn_window`.
config.set_environment_variables = {
  PATH = '/opt/homebrew/bin:/usr/local/bin:' .. os.getenv('PATH'),
}

-- The secure-agent-pod (Talos/K8s, see this repo's apps/secure-agent-pod manifests)
-- exposes SSH and mosh on *separate* Cilium LoadBalancer IPs:
--   service-ssh.yaml   -> 192.168.55.215  TCP/22  -> container 2222
--   service-mosh.yaml  -> 192.168.55.219  UDP/60000-60015 -> container 60000-60015
-- Only 16 UDP ports are published, so mosh-server must be constrained to that
-- range explicitly (default would pick uniformly from 60000-61000, ~1.6% hit rate).
--
-- Why ProxyCommand instead of -o HostName=:
--   mosh.pl runs `ssh -G <host>` to find the canonical hostname and uses it
--   for the UDP socket. `-o HostName=...` poisons that resolution (mosh ends
--   up sending UDP to the SSH IP). ProxyCommand is invisible to `ssh -G`, so
--   ssh still reports the UDP IP as hostname while the actual TCP bytes
--   tunnel through `nc <SSH_IP> 22` to reach sshd.
local REMOTE_SSH_HOST        = "192.168.55.215"
local REMOTE_UDP_HOST        = "192.168.55.219"
local REMOTE_USER            = "claude"
local REMOTE_KEY             = "~/.ssh/your_private_key"  -- ssh expands ~ for -i; substitute your own path
local REMOTE_MOSH_PORT_RANGE = "60000:60015"
local REMOTE_TMUX_SESSION    = "claude-frank-secure-pod"
local LOCAL_TMUX_SESSION     = "claude-local"

-- Two named workspaces, each launched into a tmux attach-or-create command.
-- `new-session -A -s NAME` attaches if NAME exists, otherwise creates it.
config.default_workspace = "local"

-- spawn_local_workspace: open a window in the `local` workspace running tmux.
-- Idempotent — `tmux new-session -A` attaches to the existing claude-local
-- session if one is alive, so re-spawning just gives you another viewport.
local function spawn_local_workspace()
  return wezterm.mux.spawn_window {
    workspace = 'local',
    args = { 'tmux', 'new-session', '-A', '-s', LOCAL_TMUX_SESSION },
  }
end

-- spawn_frank_workspace: open a window in the `frank` workspace running mosh
-- to the secure-agent-pod, attaching/creating the remote tmux session.
--
-- The MOSH_SSH_PROXY env var trick: mosh.pl splits --ssh= on whitespace
-- (naive split), which would shred a literal `ProxyCommand=nc <ip> 22`
-- into separate tokens. Stashing the proxy command in an env var and
-- referring to it as $MOSH_SSH_PROXY inside single quotes keeps it as
-- one token through zsh and through mosh's split; ssh then expands the
-- env var when it execs ProxyCommand via /bin/sh -c.
--
-- --experimental-remote-ip=local: mosh's default 'proxy' mode reads the
-- peer IP from the SSH ProxyCommand (opaque with plain `nc`), and 'remote'
-- mode reads $SSH_CONNECTION on the pod (which reports the pod's internal
-- 10.244.x.x cluster IP, unreachable from outside). 'local' uses the IP
-- the local resolver returned for the positional arg -- i.e. the LB IP.
-- LC_ALL=C.UTF-8 prefix on --server: mosh-server refuses to run without a
-- UTF-8 locale, and the Kali pod ships with no LANG/LC_* set. Putting the
-- assignment in front of the remote command scopes it to mosh-server only,
-- and avoids needing AcceptEnv on the pod's sshd.
-- ControlMaster=no/ControlPath=none/ControlPersist=no triple is required
-- because ~/.ssh/config has `ControlMaster auto` with a 10-min persist
-- window. mosh's built-in `-S none -o ControlPath=none` doesn't fully
-- suppress this on OpenSSH 10.2+; an existing master gets reused and
-- mosh-server's stdout vanishes into the mux channel, so mosh.pl never
-- sees `MOSH CONNECT` and dies with "Did not find mosh server startup
-- message". Adding all three ssh -o overrides forces a fresh connection.
-- SHELL=/bin/sh on the mosh invocation: ssh picks the ProxyCommand shell
-- from $SHELL (falling back to /bin/sh). On macOS $SHELL is /bin/zsh, and
-- zsh by default does NOT word-split unquoted variable expansions -- so
-- `zsh -c '$MOSH_SSH_PROXY'` treats `nc 192.168.55.215 22` as a single
-- command name and dies with "command not found". /bin/sh word-splits on
-- IFS, which is what we want. The override is scoped to this one mosh
-- run; it doesn't leak into the surrounding shell.
local function spawn_frank_workspace()
  local mosh_invocation = string.format(
    "export MOSH_SSH_PROXY='nc %s 22'; "
    .. "SHELL=/bin/sh mosh --experimental-remote-ip=local "
    .. "--ssh='ssh -l %s -i %s "
        .. "-o ControlMaster=no -o ControlPath=none -o ControlPersist=no "
        .. "-o ProxyCommand=$MOSH_SSH_PROXY' "
    .. "--server='LC_ALL=C.UTF-8 mosh-server new -p %s' "
    .. "%s -- tmux new-session -A -s %s",
    REMOTE_SSH_HOST,
    REMOTE_USER, REMOTE_KEY,
    REMOTE_MOSH_PORT_RANGE,
    REMOTE_UDP_HOST, REMOTE_TMUX_SESSION
  )
  -- On failure: tee everything to /tmp/wezterm-mosh.log AND drop to a
  -- bare `zsh -f` (no .zshrc -> no zsh4humans -> no auto-tmux that would
  -- clear the alternate screen and erase the mosh error message).
  local remote_cmd = string.format(
    'log=/tmp/wezterm-mosh.log; : > "$log"; '
    .. 'exec > >(tee -a "$log") 2>&1; '
    .. 'echo "[wezterm] mosh ssh=%s udp=%s tmux=%s ports=%s log=$log"; '
    .. '%s; '
    .. 'rc=$?; echo; echo "[mosh exited rc=$rc -- bare zsh below; full log at $log]"; '
    .. 'exec /bin/zsh -f',
    REMOTE_SSH_HOST, REMOTE_UDP_HOST, REMOTE_TMUX_SESSION, REMOTE_MOSH_PORT_RANGE,
    mosh_invocation
  )
  return wezterm.mux.spawn_window {
    workspace = 'frank',
    args = { '/bin/zsh', '-l', '-c', remote_cmd },
  }
end

wezterm.on('gui-startup', function(_)
  spawn_local_workspace()
  spawn_frank_workspace()
end)

-- Drop WezTerm's entire default keytable so nothing competes with tmux for
-- Ctrl/Shift/Alt combos. macOS-level CMD shortcuts (Q/M/H/,) still work,
-- mouse selection still works (governed by disable_default_mouse_bindings,
-- which we leave on). We add back only what we explicitly want at the
-- WezTerm layer.
config.disable_default_key_bindings = true

config.keys = {
  -- Clipboard (the one default really worth restoring on macOS).
  { key = 'c', mods = 'CMD', action = wezterm.action.CopyTo  'Clipboard' },
  { key = 'v', mods = 'CMD', action = wezterm.action.PasteFrom 'Clipboard' },

  -- Workspace switching.
  --
  -- Why `phys:` prefix on the SHIFT'd bindings: WezTerm's default
  -- key_map_preference is "Mapped", which matches the *post-layout* key.
  -- On macOS US layouts, SHIFT is consumed by the OS to produce the shifted
  -- glyph -- CMD+SHIFT+1 arrives as `!`, CMD+SHIFT+2 as `@`, CMD+SHIFT+s as
  -- capital `S`. So a literal `key='2', mods='CMD|SHIFT'` never matches
  -- (no `2` is ever produced while SHIFT is held). `phys:2` binds to the
  -- physical scancode for the `2` row instead, leaving SHIFT free to be
  -- a real modifier. The unshifted CMD+1/CMD+2 don't have this problem
  -- because there's no shifted glyph in play, but we use phys: there too
  -- for symmetry and for non-US layouts.
  { key = 'phys:1', mods = 'CMD',       action = wezterm.action.SwitchToWorkspace { name = 'local' } },
  { key = 'phys:2', mods = 'CMD',       action = wezterm.action.SwitchToWorkspace { name = 'frank' } },
  { key = 'phys:S', mods = 'CMD|SHIFT', action = wezterm.action.ShowLauncherArgs { flags = 'WORKSPACES' } },

  -- Workspace re-spawn. CMD+SHIFT+<n> opens a fresh window in workspace <n>
  -- and switches to it. Useful when a mosh session blackholes after a pod
  -- restart (image bump, OOM, supercronic SIGHUP) -- the dead window stays
  -- visible until you close it, but the new one connects cleanly.
  { key = 'phys:1', mods = 'CMD|SHIFT', action = wezterm.action_callback(function(window, pane)
      spawn_local_workspace()
      window:perform_action(wezterm.action.SwitchToWorkspace { name = 'local' }, pane)
    end) },
  { key = 'phys:2', mods = 'CMD|SHIFT', action = wezterm.action_callback(function(window, pane)
      spawn_frank_workspace()
      window:perform_action(wezterm.action.SwitchToWorkspace { name = 'frank' }, pane)
    end) },
}

return config
