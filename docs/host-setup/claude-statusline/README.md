# Claude Code status line

A three-row status line for Claude Code. Reads the session JSON from stdin and
prints:

```
Opus 4.7 (1M context) | ctx:42% of 1M | 5h:30% 7d:55%
main | ~/Docs/projects/DERIO_NET/frank
worktrees (3): feature-x:wt-feature, deadbee:hotfix +1 more
```

- **Line 1** — model + context-window size, context-used %, and 5h / 7d rate
  limits. Context and rate values are color-coded (green <50%, yellow 50–75%,
  red >75%).
- **Line 2** — current git branch and the working directory (`$HOME` shown as `~`).
- **Line 3** — *only when the repo has more than one worktree.* Lists the
  worktrees **other than the current one** (the current is already on line 2),
  as `branch:leaf-dir`. Detached HEADs show a 7-char SHA. The label count is the
  **total** worktree count (WIP gauge), and the list is width-capped with a
  `+N more` overflow so it never crops the terminal.

## Install on a new host

1. Copy the script into your Claude Code config dir:

   ```bash
   cp statusline.sh ~/.claude/statusline.sh
   chmod +x ~/.claude/statusline.sh
   ```

2. Wire it up in `~/.claude/settings.json`:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "bash ~/.claude/statusline.sh"
     }
   }
   ```

The status line reloads on the next render — no restart needed.

## Requirements

- `jq` (parses the session JSON)
- `git` (branch + worktree info; the branch/worktree rows are simply omitted
  outside a repo)

## Tuning

- `STATUSLINE_WT_WIDTH` (default `110`) — plain-text character budget for the
  worktree list portion of line 3 (the label is excluded from the count). Lower
  it for narrow panes, raise it for wide monitors. At least one worktree always
  shows even if it alone exceeds the budget.

## Notes

- The worktree list is parsed from `git worktree list --porcelain` by keying off
  the `worktree ` prefix line and flushing on each new entry (and at EOF). This
  is robust to the variable line count of `branch` / `detached` / `bare` entries
  and to the trailing blank line porcelain emits.
- Output is captured by Claude Code (not a TTY), so terminal width can't be read
  with `tput cols` — hence the fixed, env-tunable width budget.
