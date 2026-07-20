#!/usr/bin/env bash
# Per-batch gate for the batch/campaign post-rewrite workflow
# (see skills/post-rewrite "Batch / campaign mode"). One command an operator
# runs after each batch, before committing:
#
#   scripts/batch-gate.sh content/docs/<series>/<NN>-<slug>/index.md [more...]
#
# It (1) runs the educational-writing gate over the batch, then (2) a Hugo build
# check. The build step is skipped — with a clear warning — when Hugo/Go is
# unavailable or BATCH_GATE_SKIP_BUILD=1, so the validate path stays reproducible
# (and unit-testable) without a Hugo toolchain. Read-only: never edits posts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYBIN="${PYTHON:-python3}"   # real blogs use python3 (needs pyyaml); tests may pin a venv

if [ "$#" -eq 0 ]; then
  echo "usage: batch-gate.sh <post-index.md> [<post-index.md> ...]" >&2
  exit 2
fi

fail() { echo "BATCH GATE FAILED" >&2; exit 1; }

# Blog root: walk up from the first post's directory for .blog-craft.yaml.
_find_blog_root() {
  local d
  d="$(cd "$(dirname "$1")" && pwd)"
  while [ "$d" != "/" ]; do
    [ -f "$d/.blog-craft.yaml" ] && { echo "$d"; return 0; }
    d="$(dirname "$d")"
  done
  return 1
}

BLOG_ROOT="$(_find_blog_root "$1")" || {
  echo "BATCH GATE FAILED: no .blog-craft.yaml found above $1" >&2
  exit 1
}

# 1. Educational-writing gate over the whole batch (fail-fast).
echo "batch-gate: validating $# post(s) against the educational gate..."
"$PYBIN" "$SCRIPT_DIR/validate_educational.py" \
  --config "$BLOG_ROOT/.blog-craft.yaml" "$@" || fail

# 2. Hugo build check (skippable).
if [ "${BATCH_GATE_SKIP_BUILD:-0}" = "1" ]; then
  echo "batch-gate: build check skipped (BATCH_GATE_SKIP_BUILD=1)"
else
  # Hextra is a Hugo Module and needs a modern Go; prepend the first one found
  # (same dance as hugo-serve.sh).
  GO_LOCATIONS=(/usr/local/bin /opt/homebrew/bin /home/linuxbrew/.linuxbrew/bin "$HOME/.asdf/shims")
  for d in "${GO_LOCATIONS[@]}"; do
    [ -x "$d/go" ] && { export PATH="$d:$PATH"; break; }
  done
  if ! command -v hugo >/dev/null 2>&1 || ! command -v go >/dev/null 2>&1; then
    echo "batch-gate: build check skipped (hugo or go not found on PATH)" >&2
  else
    echo "batch-gate: hugo build check..."
    ( cd "$BLOG_ROOT" && hugo --quiet --gc -d /tmp/batch-gate-build ) || fail
  fi
fi

echo "BATCH GATE PASS: $# post(s)"
