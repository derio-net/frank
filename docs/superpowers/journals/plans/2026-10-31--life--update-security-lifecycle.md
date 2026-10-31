<!-- fr:journal-schema=3 -->
# Journal: 2026-10-31--life--update-security-lifecycle

<!-- fr:journal kind=decision scope=plan id=plan-repo-split created=2026-10-31T18:53:33+00:00 -->
### plan-repo-split · decision · One plan per repo (operator chose option A)

frank (this plan), derio-net/cluster-update-fr (console), derio-net/agent-images (session image); sibling plans run by cross-repo agents in their own workspaces.

<!-- fr:journal kind=decision scope=plan id=manual-back-loaded created=2026-10-31T18:53:33+00:00 -->
### manual-back-loaded · decision · Bootstrap/manual work back-loaded to phase 7

No agentic phase needs live secrets; apps tolerate missing Secrets (optional: true) until the trailing manual phase.

<!-- fr:journal kind=discovery scope=plan id=p5-scrub-boundary-lessons created=2026-10-31T19:12:03+00:00 phase=5 -->
### p5-scrub-boundary-lessons · discovery · Scrubber regexes must not consume boundaries or anchor at end of line (phase 5)

Security review of the console's internal/scrub/scrub.go found two bypasses that apply equally to scripts/life_scrub.py: (1) a pattern that consumes its trailing boundary char misses the second of two ADJACENT tokens — check boundaries in code or loop until stable, test adjacent tokens; (2) a `$`-anchored, unquoted-key yaml-secret pattern misses trailing comments and JSON pairs — no end anchor, optional key quotes, value ends at whitespace/quote/comma; test both. Share fixtures with the console repo.

<!-- fr:journal kind=discovery scope=plan id=p5-session-image-interface created=2026-10-31T19:14:34+00:00 phase=5 -->
### p5-session-image-interface · discovery · upgrade-session image interface (agent-images#171) (phase 5)

Image ghcr.io/derio-net/upgrade-session:<sha>, built FROM agent-base (NOT infra-shell: s6/sshd is incompatible with a read-only root FS). User uid 1000 'claude', HOME /home/claude, nothing baked under HOME: mount emptyDir at /home/claude and /tmp, readOnlyRootFilesystem true, drop ALL caps, no SA token unless the type needs it. Entrypoint tini + upgrade-session-entrypoint, CMD bash. Pod env UPGRADE_TALOS_MINOR (1.12|1.13|1.14) and UPGRADE_K8S_MINOR (1.34-1.37) select pinned talosctl/kubectl; a bad minor exits 2 at start. In-session: use-versions --talos X --kubernetes Y, use-versions --list; symlinks in $HOME/.local/bin. AGENTS.md/CLAUDE.md must be mounted by frank (e.g. /home/claude). No sshd: attach via runs-fr. Frank must add upgrade-session to the AGENT_IMAGES bump allowlist (agent-images-bump workflow).
