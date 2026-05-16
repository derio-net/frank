# Agent Configuration Tests

The portable validator is `scripts/validate-agent-config.sh`.

It is intentionally static: no local test can prove that every possible agent
runtime will obey instructions identically. Instead, the test verifies the
contract that makes identical behavior possible:

- `AGENTS.md` is the canonical entrypoint.
- Claude-specific files point back to the shared contract.
- Shared rules, skills, reviewers, and commands live under `agents/`.
- No tracked policy remains under `.claude/rules`, `.claude/agents`, or
  `.claude/commands`.
- Claude hooks call shared scripts rather than owning separate policy.
- Active agent docs do not point at Claude-only paths.

Run:

```bash
scripts/validate-agent-config.sh
```
