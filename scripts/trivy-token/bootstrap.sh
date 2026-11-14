#!/usr/bin/env bash
# Generate the shared Trivy client/server token and apply it where it is read
# (manual-op life-trivy-token, frank#914 finding p3-r7).
#
# Not a session credential: it is a random shared secret between the in-cluster Trivy server and
# its two clients, so it does not wait for phase 7 / frank#912. Two Secrets carry the SAME value:
#   trivy-system/trivy-operator-trivy-config  trivy.serverToken (scan jobs) + TRIVY_TOKEN (server)
#   hop-scan/trivy-server-token               TRIVY_TOKEN (the daily Hop scan)
# Until the first exists trivy-server-0 sits in CreateContainerConfigError and the app is Progressing.
#
# State                                   without --force          with --force
# no SOPS files, no live Secrets          generate + write + apply  same
# SOPS files, no live Secret (rebuild)    restore: decrypt + apply  generate new
# live Secret(s), no SOPS files           REFUSE (wrong checkout?)  generate new
# both present                            nothing                   generate new
#
# The token exists only in a shell variable: builtin printf into sops (encrypt) and kubectl
# (server-side apply, so no last-applied annotation carries it). No here-doc, no argv, no xtrace.
# Encrypting needs only the public age recipient in .sops.yaml; restoring needs the age private key.
#
# Usage (from the repo root, KUBECONFIG = Frank):  bash scripts/trivy-token/bootstrap.sh [--force]
set -euo pipefail
set +x

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1
REPO=$(cd "$(dirname "$0")/../.." && pwd)
for bin in kubectl sops openssl shasum; do command -v "$bin" >/dev/null || { echo "missing: $bin" >&2; exit 1; }; done

# name | namespace | file under secrets/trivy/ | keys (comma separated)
SPECS=(
  "trivy-operator-trivy-config|trivy-system|secrets/trivy/trivy-operator-trivy-config.yaml|trivy.serverToken,TRIVY_TOKEN"
  "trivy-server-token|hop-scan|secrets/trivy/trivy-server-token.yaml|TRIVY_TOKEN"
)

apply() { kubectl apply --server-side --field-manager=trivy-token --force-conflicts -f - >/dev/null; }
fp() { shasum -a 256 | cut -c1-12; }

manifest() { # name ns keys token
  local name=$1 ns=$2 keys=$3 token=$4 k
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n  namespace: %s\ntype: Opaque\nstringData:\n' "$name" "$ns"
  IFS=, read -ra ks <<<"$keys"
  for k in "${ks[@]}"; do printf '  %s: "%s"\n' "$k" "$token"; done
}

live=0; files=0
for s in "${SPECS[@]}"; do
  IFS='|' read -r name ns rel keys <<<"$s"
  kubectl -n "$ns" get secret "$name" >/dev/null 2>&1 && live=$((live+1))
  [[ -f "$REPO/$rel" ]] && files=$((files+1))
done
n=${#SPECS[@]}

if [[ $FORCE -eq 0 && $live -eq $n && $files -eq $n ]]; then
  echo "nothing to do: both Secrets are live and both SOPS files exist (use --force to rotate)"
elif [[ $FORCE -eq 0 && $live -gt 0 && $files -lt $n ]]; then
  echo "REFUSING: $live live Secret(s) but only $files/$n SOPS files in $REPO." >&2
  echo "Run from the checkout that holds secrets/trivy/, or pass --force to rotate." >&2
  exit 1
elif [[ $FORCE -eq 0 && $files -eq $n ]]; then
  for s in "${SPECS[@]}"; do
    IFS='|' read -r name ns rel keys <<<"$s"
    sops decrypt "$REPO/$rel" | apply
    echo "restored: applied $ns/$name from $rel"
  done
else
  token=$(openssl rand -hex 32)               # 64 hex characters
  [[ ${#token} -eq 64 ]] || { echo "generated token has wrong length" >&2; exit 1; }
  mkdir -p "$REPO/secrets/trivy"
  for s in "${SPECS[@]}"; do
    IFS='|' read -r name ns rel keys <<<"$s"
    tmp=$(mktemp "$REPO/$rel.XXXXXX")
    trap 'rm -f "$tmp"' EXIT
    manifest "$name" "$ns" "$keys" "$token" \
      | (cd "$REPO" && sops encrypt --filename-override "$rel" --input-type yaml --output-type yaml /dev/stdin) > "$tmp"
    grep -q 'ENC\[' "$tmp" || { echo "sops output is not encrypted; aborting" >&2; exit 1; }
    mv "$tmp" "$REPO/$rel"; trap - EXIT
    manifest "$name" "$ns" "$keys" "$token" | apply
    echo "wrote $rel and applied $ns/$name"
  done
  unset token
fi

# --- verification (fingerprints and lengths only, never values) ------------------------------------
a=$(kubectl -n trivy-system get secret trivy-operator-trivy-config -o jsonpath='{.data.TRIVY_TOKEN}' | base64 -d | fp)
b=$(kubectl -n trivy-system get secret trivy-operator-trivy-config -o jsonpath='{.data.trivy\.serverToken}' | base64 -d | fp)
c=$(kubectl -n hop-scan get secret trivy-server-token -o jsonpath='{.data.TRIVY_TOKEN}' | base64 -d | fp)
echo "fingerprints: server=$a scan-jobs=$b hop-scan=$c"
[[ "$a" == "$b" && "$a" == "$c" ]] || { echo "FAIL: the three token keys differ (server would reject its own clients)" >&2; exit 1; }
echo "OK: one token, three readers"
kubectl -n trivy-system rollout status sts/trivy-server --timeout=300s || \
  echo "note: trivy-server is not Ready yet (first start downloads the vulnerability DB); re-check: kubectl -n trivy-system get pods"
echo "next: commit secrets/trivy/ on the PR branch; the Secrets are SOPS-only, never an ArgoCD resource"
