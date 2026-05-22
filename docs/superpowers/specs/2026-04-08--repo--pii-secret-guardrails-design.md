# PII & Secret Guardrails Design

**Date:** 2026-04-08
**Status:** Open design — guardrails not implemented (no PII/secret pre-commit hook present as of 2026-05-22). Spec captures the threat model; implementation deferred.

## Problem

Frank is a public repository. Documentation (including `docs/superpowers/` plans and specs) lives alongside code and is visible to anyone. AI-assisted workflows generate docs that reference real values — emails, IDs, paths, credentials — because they work with real context. The combination of high-throughput AI content generation and a public repo creates a steady leak risk.

### Incident (2026-04-08)

Noticed potentially personally identifying information (PII) in the public repo and git history. Files fixed, history rewritten with `git-filter-repo`, force-pushed to main.

Root cause: no enforcement layer between content generation and `git push`. `.gitignore` catches known filenames but not PII embedded in markdown or YAML values.

## Design Constraints

1. `docs/superpowers/` stays in the public repo — these documents are part of the project's story
2. A blacklist of sensitive strings cannot be committed (it would contain the secrets it protects)
3. Must work for both human commits and Claude Code agent operations
4. Hard block — no warnings, no overrides without explicit `--no-verify`

## Threat Model

| Threat | Vector | Current Protection | Gap |
|--------|--------|--------------------|-----|
| Known secret file committed | `.env`, `.key`, `.pem` filename | `.gitignore` | None — works |
| Secret embedded in YAML/config | Inline value in any file | Nothing | **Open** |
| PII in documentation | AI-generated plans/specs/blog | Nothing | **Open** |
| PII in blog content | Manual or AI-authored posts | Nothing | **Open** |
| Secret in git history | Any past commit | Manual BFG/filter-repo | **Reactive only** |
| Claude Code writes PII | Agent generates doc with real values | Guardrails hook (agent pod only) | **Local sessions unprotected** |

## Architecture

Three layers of defense, from earliest to latest intervention point.

### Layer 1: Agent Awareness (generation time)

**What:** A `.claude/rules/` file in Frank declaring the repo is public and defining what constitutes PII.

**Why:** Catches PII before it's written to disk. The agent self-censors when generating documentation.

**Rules:**

```
This is a PUBLIC repository. Everything committed here is visible to the internet.

Never include in any file:
- Personal email addresses (except the repo owner's public email and the bot's commit email)
- Physical addresses
- Telegram/Discord/Slack IDs (bot IDs, chat IDs, user IDs)
- API keys, tokens, passwords, private keys
- OS usernames or home directory paths
- Any identifier that links to a real person or account

Use Infisical references or placeholders instead. When documenting a configuration
that requires a secret, write: `<value in Infisical: KEY_NAME>` or `(stored in Infisical)`.
```

**Location:** `.claude/rules/public-repo-pii.md`

### Layer 2: Pre-commit Hook (commit time)

**What:** A git pre-commit hook that scans staged content for PII and secret patterns. Hard block.

**Detection approach:** Pattern-matching with a whitelist, not a blacklist.

#### Whitelisted (always allowed)
- The repo owner's public email (`dermitzakisyiannis@gmail.com`)
- The bot's commit email (`clawdia-ai-assistant@gmail.com`)
- All `@derio.net` addresses
- All `noreply@*` addresses
- Standard example domains (`example.com`, `example.org`)

#### Blocked Patterns

| Category | Pattern | Examples |
|----------|---------|----------|
| Email addresses | Standard email regex minus whitelist | Any non-whitelisted email |
| API keys | Known prefixes (`sk-`, `ghp_`, `AKIA`) | AWS, GitHub, OpenAI keys |
| Private keys | PEM header detection | RSA, EC, OPENSSH private keys |
| High-entropy strings | Base64/hex > 40 chars in key/token/secret context | Inline credentials |
| Messaging platform IDs | Numeric IDs in Telegram/Discord/Slack context | Bot IDs, chat IDs |
| Home directory paths | `/Users/<username>/` or `/home/<username>/` (minus CI paths like `/home/runner/`) | OS home dirs |
| EXIF metadata | GPS coordinates, camera serials in image files | Blog images |

#### Implementation

**Recommendation:** Gitleaks with custom `.gitleaks.toml`.

- Gitleaks handles secret patterns well out of the box
- Custom rules added for PII-specific patterns (emails, home paths, messaging IDs)
- Whitelist entries in the config's `[allowlist]` section
- SOPS-encrypted files skipped (detected by SOPS header)
- Wired up via `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks
```

### Layer 3: GitHub Actions (push time — safety net)

**What:** A GitHub Actions workflow that runs gitleaks on every push. Fails the check if secrets or PII are detected.

**Why:** Catches anything that bypasses local hooks (e.g., `--no-verify`, direct GitHub web edits, other contributors).

```yaml
name: Secret & PII Scan
on: [push, pull_request]
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Uses the same `.gitleaks.toml` as the local hook.

## Claude Code Integration

### Frank Repo (`.claude/settings.json`)

Extend the existing `PreToolUse` hook to run gitleaks on staged files before allowing `git commit`. Belt and suspenders alongside the git hook.

### Willikins Guardrails Hook

Extend the existing `guardrails-hook.py` to:
1. Run gitleaks on staged content before allowing `git commit` in public repos
2. Check Write/Edit targets against PII patterns when writing to the Frank repo

Relevant when the persistent agent delegates to a Frank subagent.

## Bootstrap for New Clones

```bash
# After cloning
pip install pre-commit && pre-commit install
```

Add to README and optionally wrap in `scripts/setup-hooks.sh`.

## Implementation Plan

- [ ] Create `.claude/rules/public-repo-pii.md` — agent awareness rule
- [ ] Create `.gitleaks.toml` — custom rules + whitelist, SOPS file exclusion
- [ ] Create `.pre-commit-config.yaml` — hook configuration
- [ ] Add EXIF stripping to pre-commit (e.g., `exiftool` hook for image files)
- [ ] Create `.github/workflows/secret-scan.yml` — CI safety net
- [ ] Update `.claude/settings.json` — add gitleaks pre-commit check
- [ ] Update `README.md` — add hook setup instructions
- [ ] Test — commit with known PII patterns, verify block
- [ ] Update willikins guardrails hook — extend for cross-repo PII checking
- [ ] Rebase all local feature branches onto new main
