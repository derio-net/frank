#!/usr/bin/env bash
# Rotate Headplane's session-signing key on Hop (manual-op
# edge-hop-headplane-cookie-secret-rotation, ice#5).
#
# Generates a new 32-character key, writes it SOPS-encrypted to
# secrets/hop/headplane-cookie-secret.yaml in the checkout this script lives in,
# and applies the same Secret to Hop. The key is held only in shell variables
# and piped to sops/kubectl; it is never echoed, logged, or written in plaintext.
#
# Idempotent: if both the encrypted file and the live Secret already exist it
# does nothing; pass --force to rotate again. If the Deployment already reads
# the Secret, the pod is restarted so it picks up the new key (env is read at
# boot). Encrypting needs only the public age recipient in .sops.yaml.
#
# Usage: bash scripts/headplane-session-key/rotate.sh [--force]
set -euo pipefail
set +x

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
# .env_hop and the Hop kubeconfig are gitignored and live in the MAIN checkout,
# not in an fr worktree.
MAIN=$(cd "$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir)/.." && pwd)
REL=secrets/hop/headplane-cookie-secret.yaml
OUT="$REPO/$REL"
NS=headscale-system
NAME=headplane-cookie-secret
KEY=cookie-secret

# shellcheck disable=SC1091
KUBECONFIG=$(cd "$MAIN" && source ./.env_hop >/dev/null 2>&1 && realpath "$KUBECONFIG")
export KUBECONFIG
for bin in kubectl sops openssl; do command -v "$bin" >/dev/null || { echo "missing: $bin" >&2; exit 1; }; done
kubectl get ns "$NS" >/dev/null   # fail fast if this is not Hop

live_exists=0
kubectl -n "$NS" get secret "$NAME" >/dev/null 2>&1 && live_exists=1
if [[ $FORCE -eq 0 && $live_exists -eq 1 && -f "$OUT" ]]; then
  echo "already rotated: $REL exists and Secret $NS/$NAME is live (use --force to rotate again)"
else
  new=$(openssl rand -hex 16)               # 32 hex characters, as the schema requires
  [[ ${#new} -eq 32 ]] || { echo "generated key has wrong length" >&2; exit 1; }
  manifest=$(cat <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $NAME
  namespace: $NS
type: Opaque
stringData:
  $KEY: "$new"
EOF
)
  mkdir -p "$(dirname "$OUT")"
  tmp=$(mktemp "$OUT.XXXXXX")
  trap 'rm -f "$tmp"' EXIT
  printf '%s\n' "$manifest" \
    | (cd "$REPO" && sops encrypt --filename-override "$REL" --input-type yaml --output-type yaml /dev/stdin) > "$tmp"
  grep -q 'ENC\[' "$tmp" || { echo "sops output is not encrypted; aborting" >&2; exit 1; }
  mv "$tmp" "$OUT"; trap - EXIT
  printf '%s\n' "$manifest" | kubectl apply -f - >/dev/null
  unset manifest new
  echo "rotated: wrote $REL and applied Secret $NS/$NAME"

  if kubectl -n "$NS" get deploy headplane -o jsonpath='{.spec.template.spec.containers[0].env[*].valueFrom.secretKeyRef.name}' | grep -qw "$NAME"; then
    kubectl -n "$NS" rollout restart deploy/headplane >/dev/null
    kubectl -n "$NS" rollout status deploy/headplane --timeout=120s
  else
    echo "note: the Deployment does not read $NAME yet; it picks the key up when the PR merges and ArgoCD rolls the pod"
  fi
fi

# --- verification (fingerprints only, never values) ----------------------------
fp() { shasum -a 256 | cut -c1-12; }
live_fp=$(kubectl -n "$NS" get secret "$NAME" -o jsonpath="{.data.$KEY}" | base64 -d | fp)
len=$(kubectl -n "$NS" get secret "$NAME" -o jsonpath="{.data.$KEY}" | base64 -d | wc -c | tr -d ' ')
old_fp=$(git -C "$REPO" log --all -p -- clusters/hop/apps/headplane blog/content/docs/building/17-public-edge \
  | grep -E '^[-+][[:space:]]+cookie_secret:' \
  | sed -E 's/.*cookie_secret:[[:space:]]*//' | tr -d "\"' " | sort -u \
  | while read -r v; do printf %s "$v" | fp; done)
echo "live Secret: length=$len fingerprint=$live_fp"
if grep -qx "$live_fp" <<<"$old_fp"; then
  echo "FAIL: live key matches a value from git history" >&2; exit 1
fi
echo "OK: live key differs from every value ever committed (headplane manifests + blog post)"
echo "next: commit $REL on the PR branch; after merge run: bash scripts/headplane-session-key/verify.sh"
