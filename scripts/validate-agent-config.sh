#!/usr/bin/env bash
# Validate that all agent runtimes share the same repository contract.
set -euo pipefail

errors=()

fail() {
  errors+=("$1")
}

require_file() {
  local path="$1"
  [ -f "$path" ] || fail "missing required file: $path"
}

require_dir() {
  local path="$1"
  [ -d "$path" ] || fail "missing required directory: $path"
}

require_grep() {
  local pattern="$1"
  local path="$2"
  local message="$3"
  if [ ! -e "$path" ] || ! grep -Eq "$pattern" "$path"; then
    fail "$message"
  fi
}

require_dir agents/rules
require_dir agents/skills
require_dir agents/reviewers
require_dir agents/commands

for path in \
  AGENTS.md \
  CLAUDE.md \
  GEMINI.md \
  docs/layers.yaml \
  docs/superpowers/plan-config.yaml \
  docs/runbooks/manual-operations.yaml \
  agents/rules/frank-argocd.md \
  agents/rules/frank-commands.md \
  agents/rules/frank-gotchas.md \
  agents/rules/frank-identity.md \
  agents/rules/frank-infrastructure.md \
  agents/rules/hop-commands.md \
  agents/rules/hop-gotchas.md \
  agents/rules/hop-infrastructure.md \
  agents/rules/plan-checkbox-tracking.md \
  agents/rules/plan-post-deploy-checklist.md \
  agents/rules/repo-architecture.md \
  agents/rules/repo-blog.md \
  agents/rules/repo-manual-ops.md \
  agents/rules/repo-principles.md \
  agents/rules/repo-workflows.md \
  agents/rules/third-party-privacy.md \
  agents/reviewers/code-reviewer.md \
  agents/reviewers/k8s-manifest-reviewer.md; do
  require_file "$path"
done

require_grep 'canonical entry point for all AI agents' AGENTS.md \
  "AGENTS.md must declare itself as the canonical agent entrypoint"
require_grep 'agents/rules/repo-principles.md' AGENTS.md \
  "AGENTS.md must include the shared rule load order"
require_grep 'scripts/validate-agent-config.sh' AGENTS.md \
  "AGENTS.md must document the portable agent validator"
require_grep 'canonical agent instructions live in `AGENTS.md`' CLAUDE.md \
  "CLAUDE.md must be an adapter that points back to AGENTS.md"
require_grep 'see: \[AGENTS.md\]\(AGENTS.md\)' GEMINI.md \
  "GEMINI.md must be an adapter that points back to AGENTS.md"

# Cross-agent skill-registration guard (frank#581 fix #4).
# Every repo-local skill under agents/skills/ must be registered for every
# supported harness:
#   - reachable to Claude Code via the `.claude/skills -> ../agents/skills`
#     symlink (asserted once for all skills in the adapter loop below), AND
#   - declared in AGENTS.md's Shared Skills registry — the single canonical file
#     that codex/opencode/antigravity/gemini/pi read.
# Discovery-driven (globs agents/skills/*), so a NEW skill can't silently be
# claude-only or invisible-to-AGENTS.md — this is what prevents skill drift from
# recurring. It subsumes the old hardcoded alias allowlist. (Blog authoring —
# blog-post/media/papers — lives in the blog-craft plugin, not agents/skills/,
# so it is out of scope here by construction.)
for skill_dir in agents/skills/*/; do
  skill="$(basename "$skill_dir")"
  skill_md="${skill_dir}SKILL.md"
  if [ ! -f "$skill_md" ]; then
    fail "skill directory $skill_dir has no SKILL.md (not a first-class invocable skill)"
    continue
  fi
  # Read the frontmatter `name:` bounded to the leading `---` block (so a body
  # line beginning `name:` can't be picked up), stripping whitespace and any
  # surrounding quotes (unquoted and "double-quoted" YAML scalars both work).
  declared_name="$(awk '
    /^---[[:space:]]*$/ { n++; next }
    n == 1 && /^name:[[:space:]]*/ { sub(/^name:[[:space:]]*/, ""); print; exit }
  ' "$skill_md" | tr -d '[:space:]"')"
  if [ "$declared_name" != "$skill" ]; then
    fail "agents/skills/$skill/SKILL.md frontmatter name '$declared_name' must equal the directory name '$skill' (so the skill surfaces under the expected verb)"
  fi
  # Anchor to a Shared Skills *registry* list line (`- ...agents/skills/<name>...`),
  # NOT any mention — the aliases prose also names some skills, and a registry
  # deletion must still fail even while the prose keeps the path.
  require_grep "^-[[:space:]].*agents/skills/$skill/SKILL\.md" AGENTS.md \
    "AGENTS.md must declare the shared skill agents/skills/$skill in the Shared Skills registry list"
done

# Reverse direction: every skill AGENTS.md declares must actually exist, so a
# renamed/removed skill can't leave a dangling registration pointing at nothing.
while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  [ -f "$ref" ] || fail "AGENTS.md declares $ref but no such skill exists (dangling registration)"
done < <(grep -oE 'agents/skills/[A-Za-z0-9_-]+/SKILL\.md' AGENTS.md | sort -u)

for adapter in \
  ".claude/skills:../agents/skills" \
  ".claude/rules:../agents/rules" \
  ".claude/agents:../agents/reviewers" \
  ".claude/commands:../agents/commands"; do
  path="${adapter%%:*}"
  expected="${adapter#*:}"
  if [ -L "$path" ]; then
    target="$(readlink "$path")"
    [ "$target" = "$expected" ] || fail "$path must point to $expected"
  else
    fail "$path must be a symlink to $expected"
  fi
done

require_grep 'scripts/hooks/plan-validate-check.sh' .claude/settings.json \
  ".claude/settings.json must keep Claude wired to the shared plan validator hook"
require_grep 'scripts/hooks/plan-archive-check.sh' .claude/settings.json \
  ".claude/settings.json must keep Claude wired to the shared archive hook"
require_grep 'scripts/hooks/plan-checklist-check.sh' .claude/settings.json \
  ".claude/settings.json must keep Claude wired to the shared checklist hook"
require_grep 'BLOCK: This is a sensitive file' .claude/settings.json \
  ".claude/settings.json must keep Claude's sensitive-file guard"

stale_refs="$(
  grep -RIn '\.claude/rules\|\.claude/agents\|\.claude/commands\|CLAUDE.md Services table' \
    AGENTS.md CLAUDE.md agents scripts docs/runbooks 2>/dev/null \
    | grep -v '^scripts/validate-agent-config.sh:' \
    | grep -vi 'compatibility symlinks' || true
)"
if [ -n "$stale_refs" ]; then
  fail "active agent docs still reference Claude-only sources:
$stale_refs"
fi

if [ ${#errors[@]} -gt 0 ]; then
  echo "Agent configuration validation failed:" >&2
  for error in "${errors[@]}"; do
    echo "  - $error" >&2
  done
  exit 1
fi

echo "Agent configuration validation passed."
