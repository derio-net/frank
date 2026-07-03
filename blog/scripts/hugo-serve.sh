#!/usr/bin/env bash
# Thin wrapper around `hugo server` that ensures a recent Go is on PATH.
#
# Hextra ships as a Hugo Module. Its go.mod sets `go 1.24.2`, which older
# system Go binaries (e.g. /usr/local/go pinned at 1.19) reject as invalid:
#   invalid go version '1.24.2': must match format 1.23
# Brew Go (≥ 1.22) does not. This wrapper iterates the common modern-Go
# locations and prepends the first one that has `go`, so a recent Go wins
# over any older one already on PATH.
#
# If your modern Go lives somewhere not in GO_LOCATIONS — e.g. a custom
# install dir, mise shims, a per-project asdf override — add it to the
# list below.
set -euo pipefail
GO_LOCATIONS=(
  /usr/local/bin                   # macOS Intel brew
  /opt/homebrew/bin                # macOS Apple Silicon brew
  /home/linuxbrew/.linuxbrew/bin   # linuxbrew
  "$HOME/.asdf/shims"              # asdf
)
for d in "${GO_LOCATIONS[@]}"; do
  if [[ -x "$d/go" ]]; then
    export PATH="$d:$PATH"
    break
  fi
done
if ! command -v go >/dev/null 2>&1; then
  echo "WARN: hugo-serve.sh: no \`go\` found in PATH or any common location." >&2
  echo "      Hextra is a Hugo Module and requires Go ≥ 1.21 — install one (brew, asdf, etc.)" >&2
  echo "      or add your Go's bin dir to GO_LOCATIONS at the top of this script." >&2
  echo "      Continuing — \`hugo server\` will likely fail with a Go-version error." >&2
fi
exec hugo server "$@"
