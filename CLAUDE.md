# Claude Code Adapter

This repository's canonical agent instructions live in `AGENTS.md`.

Claude Code should load `AGENTS.md` first, then follow the shared rule,
skill, reviewer, and command files under `agents/`:

- Rules: `agents/rules/`
- Skills: `agents/skills/`
- Reviewers: `agents/reviewers/`
- Commands: `agents/commands/`

Claude-specific wiring remains in `.claude/settings.json` and
`.claude/launch.json`. Those files adapt the shared contract for Claude Code;
they do not define separate repository policy.
