# AGENTS.md

Welcome, agent. This repository manages the **Frank** Talos Kubernetes cluster and its workloads.

## Core Directives

- **Declarative-Only:** Every resource on the cluster must be reproducible from code. No ad-hoc `kubectl apply` (except for bootstrap secrets).
- **Plan-Driven:** Implementation must follow the plan lifecycle in `docs/superpowers/plans/`.
- **Validation:** Always verify changes with relevant `kubectl` or `talosctl` commands as defined in the rules.

## Instructions

Project-specific rules and workflows are located in [.agents/instructions/](.agents/instructions/):

- [Frank Principles](.agents/instructions/repo-principles.md) — The fundamental laws of this repo.
- [Frank Architecture](.agents/instructions/repo-architecture.md) — How the two-tier IaC and apps are structured.
- [Frank Workflows](.agents/instructions/repo-workflows.md) — Development lifecycle and project management.
- [Frank Gotchas](.agents/instructions/frank-gotchas.md) — Critical pitfalls and how to avoid them.
- [Infrastructure: Frank](.agents/instructions/frank-infrastructure.md) | [Infrastructure: Hop](.agents/instructions/hop-infrastructure.md)
- [Commands: Frank](.agents/instructions/frank-commands.md) | [Commands: Hop](.agents/instructions/hop-commands.md)

## Skills

Custom workflows are defined in [.agents/skills/](.agents/skills/):

- [blog-post](.agents/skills/blog-post/SKILL.md) — Create Hugo documentation posts.
- [deploy-app](.agents/skills/deploy-app/SKILL.md) — Standardized app deployment workflow.
- [sync-runbook](.agents/skills/sync-runbook/SKILL.md) — Keep manual ops registry in sync.

## Personas

Standard personas for this repository are defined in [.agents/personas/](.agents/personas/). (Currently inheriting standard roles).
