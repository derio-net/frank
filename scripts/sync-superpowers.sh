#!/usr/bin/env bash
#
# sync-superpowers.sh — Vendor superpowers plugin skills/agents into this project
#
# Copies the latest installed superpowers plugin version from the user-level
# Claude Code plugin cache into .claude/skills/ and .claude/agents/ so the
# skills are available in cloud/CI environments without plugin installation.
#
# Run this whenever you update the superpowers plugin:
#   claude plugin update superpowers@claude-plugins-official
#   ./scripts/sync-superpowers.sh
#
# Prerequisites:
#   - superpowers@claude-plugins-official installed at user level
#     (claude plugin install superpowers@claude-plugins-official)

set -euo pipefail

PLUGIN_CACHE="${HOME}/.claude/plugins/cache/claude-plugins-official/superpowers"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLS_DIR="${PROJECT_ROOT}/.claude/skills"
AGENTS_DIR="${PROJECT_ROOT}/.claude/agents"

# Find the latest installed version (highest semver directory)
LATEST_VERSION=$(ls -v "${PLUGIN_CACHE}" 2>/dev/null | tail -1)

if [[ -z "${LATEST_VERSION}" ]]; then
  echo "ERROR: superpowers plugin not found at ${PLUGIN_CACHE}" >&2
  echo "Install it with: claude plugin install superpowers@claude-plugins-official" >&2
  exit 1
fi

PLUGIN_PATH="${PLUGIN_CACHE}/${LATEST_VERSION}"
echo "Syncing from superpowers v${LATEST_VERSION}"

# Sync skills
if [[ -d "${PLUGIN_PATH}/skills" ]]; then
  echo "  Copying skills..."
  cp -r "${PLUGIN_PATH}/skills/"* "${SKILLS_DIR}/"
  echo "  Skills: $(ls "${PLUGIN_PATH}/skills" | wc -l | tr -d ' ') files"
fi

# Sync agents
if [[ -d "${PLUGIN_PATH}/agents" ]]; then
  echo "  Copying agents..."
  cp -r "${PLUGIN_PATH}/agents/"* "${AGENTS_DIR}/"
  echo "  Agents: $(ls "${PLUGIN_PATH}/agents" | wc -l | tr -d ' ') files"
fi

echo "Done. Commit the changes to make them available in cloud environments."
