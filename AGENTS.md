# Agent Configuration & Mandates

This file is the canonical entry point for all AI agents operating in this
repository. Agent-specific files may adapt these instructions for a particular
runtime, but they must not define a competing source of truth.

## Load Order

Before making non-trivial changes, agents should read these files in order:

1. `AGENTS.md` — this canonical contract.
2. `agents/rules/repo-principles.md` — declarative-only policy and maintenance rules.
3. `agents/rules/repo-architecture.md` — repository layout and naming conventions.
4. `agents/rules/repo-workflows.md` — standard layer and fix/extension workflows.
5. `agents/rules/frank-identity.md` — project voice and persona.
6. Cluster-specific rules on demand:
   - Frank: `agents/rules/frank-infrastructure.md`, `agents/rules/frank-commands.md`,
     `agents/rules/frank-argocd.md`, `agents/rules/frank-gotchas.md`
   - Hop: `agents/rules/hop-infrastructure.md`, `agents/rules/hop-commands.md`,
     `agents/rules/hop-gotchas.md`
7. Task-specific skills or reviewer profiles from `agents/skills/`,
   `agents/reviewers/`, and `agents/commands/`.

## Shared Rule Registry

Agent-neutral rules live in `agents/rules/`:

- `frank-argocd.md`
- `frank-commands.md`
- `frank-gotchas.md`
- `frank-identity.md`
- `frank-infrastructure.md`
- `hop-commands.md`
- `hop-gotchas.md`
- `hop-infrastructure.md`
- `plan-checkbox-tracking.md`
- `plan-post-deploy-checklist.md`
- `repo-architecture.md`
- `repo-blog.md`
- `repo-manual-ops.md`
- `repo-papers.md`
- `repo-principles.md`
- `repo-workflows.md`
- `third-party-privacy.md`

## Shared Skills

Repo-local skills are stored in `agents/skills/`. When a task matches a skill,
read that skill's `SKILL.md` before acting.

- `blog-post`: `agents/skills/blog-post/SKILL.md`
- `deploy-app`: `agents/skills/deploy-app/SKILL.md`
- `media`: `agents/skills/media/SKILL.md`
- `papers`: `agents/skills/papers/SKILL.md`
- `sync-runbook`: `agents/skills/sync-runbook/SKILL.md`
- `update-readme`: `agents/skills/update-readme/SKILL.md`

Slash-command references are aliases for these shared skills. For example,
`/blog-post` means `agents/skills/blog-post/SKILL.md`, and `/sync-runbook`
means `agents/skills/sync-runbook/SKILL.md`.

## Shared Reviewers And Commands

Reusable reviewer profiles live in `agents/reviewers/`:

- `code-reviewer.md`
- `k8s-manifest-reviewer.md`

Reusable command runbooks live in `agents/commands/`:

- `update-openrouter-models.md`

## Machine-Readable Configuration

- Layer registry: `docs/layers.yaml`
- Plan profile: `docs/superpowers/plan-config.yaml`
- Manual operations runbook: `docs/runbooks/manual-operations.yaml`

## Safety And Enforcement

- Do not edit sensitive files such as `.env_devops`, `.sops.yaml`, or files
  under `.talos/` without explicit user confirmation.
- Cluster state should be reproducible from this repo. See
  `agents/rules/repo-principles.md` for the narrow manual-operation exception.
- Validate agent configuration with `scripts/validate-agent-config.sh`.
- Validate plans with `scripts/validate-plans.sh`.
- The shared Git pre-commit hook runs both validators for relevant changes.
- Claude Code hooks in `.claude/settings.json` are adapters only. Other agents
  are not protected by those hooks, so portable checks must live in scripts.

## Agent-Specific Adapters

- `CLAUDE.md` is the Claude Code adapter and should point back here.
- `GEMINI.md` is the Gemini adapter and should point back here.
- `.claude/settings.json` may wire Claude-specific hooks, permissions, and
  plugins, but canonical behavior belongs in `AGENTS.md`, `agents/`, `docs/`,
  and `scripts/`.
- Compatibility symlinks: `.claude/skills`, `.claude/rules`, `.claude/agents`, and `.claude/commands` point into `agents/`.
- `.claude/settings.local.json` is local operator state and must not be treated
  as shared policy.
