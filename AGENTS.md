# Agent Configuration & Mandates

This file serves as the primary entry point for all AI agents operating in this repository. It centralizes the rules, personas, and workflows established for the Frank cluster.

## Redirection
For the current foundational mandates, persona definitions, and infrastructure rules, refer to the Claude-optimized configuration:

- **Primary Instructions:** [CLAUDE.md](CLAUDE.md)
- **Detailed Rules & Gotchas:** [.claude/rules/](.claude/rules/)
- **Layer Registry:** [docs/layers.yaml](docs/layers.yaml)
- **Plan Configuration:** [docs/superpowers/plan-config.yaml](docs/superpowers/plan-config.yaml)

## Shared Skills (Agent-Agnostic)
Repo-local skills are stored in `agents/skills/`. All agents should consult the `SKILL.md` in these directories when performing related tasks:

- **blog-post:** [agents/skills/blog-post/SKILL.md](agents/skills/blog-post/SKILL.md)
- **deploy-app:** [agents/skills/deploy-app/SKILL.md](agents/skills/deploy-app/SKILL.md)
- **media:** [agents/skills/media/SKILL.md](agents/skills/media/SKILL.md)
- **sync-runbook:** [agents/skills/sync-runbook/SKILL.md](agents/skills/sync-runbook/SKILL.md)
- **update-readme:** [agents/skills/update-readme/SKILL.md](agents/skills/update-readme/SKILL.md)

## Future Consolidation
All agent-specific instructions currently residing in `CLAUDE.md` and `.claude/` will eventually be migrated into this file or its sub-modules.
