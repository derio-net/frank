#!/usr/bin/env bash
# Provision pinned manifest-validation tooling into a gitignored .bin/ at repo root.
# The fr `dev` devcontainer ships python3/uv/curl/node but NOT helm/kubeconform/tkn/yamllint,
# which the staging-gate plan's TDD validation steps need. Idempotent: skips an already-present
# pinned binary. Run via the exec-bridge:
#   fr isolation exec --branch feat/staging-vcluster-gate -- bash scripts/staging-gate/ensure-tools.sh
set -euo pipefail

HELM_VERSION="v3.16.4"
KUBECONFORM_VERSION="v0.6.7"
TKN_VERSION="0.40.0"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bin="$repo_root/.bin"
mkdir -p "$bin"

case "$(uname -s)" in Linux) os=linux ;; Darwin) os=darwin ;; *) echo "unsupported OS" >&2; exit 1 ;; esac
case "$(uname -m)" in x86_64|amd64) arch=amd64 ;; aarch64|arm64) arch=arm64 ;; *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;; esac

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

if [ ! -x "$bin/helm" ]; then
  echo "==> helm ${HELM_VERSION} (${os}/${arch})"
  curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-${os}-${arch}.tar.gz" | tar -xz -C "$tmp"
  install -m 0755 "$tmp/${os}-${arch}/helm" "$bin/helm"
fi

if [ ! -x "$bin/kubeconform" ]; then
  echo "==> kubeconform ${KUBECONFORM_VERSION} (${os}/${arch})"
  curl -fsSL "https://github.com/yannh/kubeconform/releases/download/${KUBECONFORM_VERSION}/kubeconform-${os}-${arch}.tar.gz" | tar -xz -C "$tmp"
  install -m 0755 "$tmp/kubeconform" "$bin/kubeconform"
fi

if [ ! -x "$bin/tkn" ]; then
  echo "==> tkn ${TKN_VERSION} (${os}/${arch})"
  # tkn release asset arch tokens: x86_64 / aarch64
  case "$arch" in amd64) tkn_arch=x86_64 ;; arm64) tkn_arch=aarch64 ;; esac
  tkn_os="$(echo "$os" | sed 's/^./\U&/')"   # Linux / Darwin
  curl -fsSL "https://github.com/tektoncd/cli/releases/download/v${TKN_VERSION}/tkn_${TKN_VERSION}_${tkn_os}_${tkn_arch}.tar.gz" | tar -xz -C "$tmp"
  install -m 0755 "$tmp/tkn" "$bin/tkn"
fi

# yamllint via uv (already in the container); exposed on PATH as a uv tool.
if ! command -v yamllint >/dev/null 2>&1; then
  echo "==> yamllint (uv tool)"
  uv tool install yamllint >/dev/null
fi

echo "--- versions ---"
"$bin/helm" version --short
"$bin/kubeconform" -v
"$bin/tkn" version 2>/dev/null | head -1 || true
yamllint --version
echo "ok: tools in $bin (+ yamllint via uv)"
