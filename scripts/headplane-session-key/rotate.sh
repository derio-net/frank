#!/usr/bin/env bash
# Rotate (or restore) Headplane's session-signing key on Hop
# (manual-op edge-hop-headplane-cookie-secret-rotation, ice#5).
#
# State                                  without --force          with --force
# no SOPS file, no live Secret           generate + write + apply  same
# SOPS file, no live Secret (rebuild)    restore: decrypt + apply  generate new
# live Secret, no SOPS file              REFUSE (wrong checkout?)  generate new
# both present                           nothing                   generate new
#
# A generated key exists only in a shell variable: it is passed to the builtin
# printf and piped into sops (encrypt) and kubectl (server-side apply). No
# here-doc (bash 3.2 backs here-docs with a temp file), no argv, no xtrace, and
# server-side apply so no last-applied-configuration annotation carries it.
# Encrypting needs only the public age recipient in .sops.yaml; restoring needs
# the age private key. A rotation restarts the pod if it already reads the
# Secret (env is read at boot) and signs out every Headplane session.
#
# Usage: bash scripts/headplane-session-key/rotate.sh [--force]
set -euo pipefail
set +x

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
OUT="$REPO/$REL"
for bin in kubectl sops openssl shasum; do command -v "$bin" >/dev/null || { echo "missing: $bin" >&2; exit 1; }; done
hop_context

apply() { kubectl apply --server-side --field-manager=headplane-session-key --force-conflicts -f - >/dev/null; }
restart_if_wired() {
  if kubectl -n "$NS" get deploy headplane -o jsonpath='{.spec.template.spec.containers[0].env[*].valueFrom.secretKeyRef.name}' | grep -qw "$NAME"; then
    kubectl -n "$NS" rollout restart deploy/headplane >/dev/null
    kubectl -n "$NS" rollout status deploy/headplane --timeout=120s
  else
    echo "note: the Deployment does not read $NAME yet; it picks the key up when the PR merges and ArgoCD rolls the pod"
  fi
}

live=0; kubectl -n "$NS" get secret "$NAME" >/dev/null 2>&1 && live=1
file=0; [[ -f "$OUT" ]] && file=1

if [[ $FORCE -eq 0 && $live -eq 1 && $file -eq 1 ]]; then
  echo "nothing to do: $REL exists and Secret $NS/$NAME is live (use --force to rotate)"
elif [[ $FORCE -eq 0 && $live -eq 1 && $file -eq 0 ]]; then
  echo "REFUSING: Secret $NS/$NAME is live but $REL is missing in $REPO." >&2
  echo "Run from the checkout that holds the committed file, or pass --force to rotate (signs everyone out)." >&2
  exit 1
elif [[ $FORCE -eq 0 && $live -eq 0 && $file -eq 1 ]]; then
  sops decrypt "$OUT" | apply
  echo "restored: applied Secret $NS/$NAME from $REL"
  restart_if_wired
else
  new=$(openssl rand -hex 16)               # 32 hex characters, as the schema requires
  [[ ${#new} -eq 32 ]] || { echo "generated key has wrong length" >&2; exit 1; }
  manifest() {
    printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n  namespace: %s\ntype: Opaque\nstringData:\n  %s: "%s"\n' \
      "$NAME" "$NS" "$KEY" "$new"
  }
  mkdir -p "$(dirname "$OUT")"
  tmp=$(mktemp "$OUT.XXXXXX")
  trap 'rm -f "$tmp"' EXIT
  manifest | (cd "$REPO" && sops encrypt --filename-override "$REL" --input-type yaml --output-type yaml /dev/stdin) > "$tmp"
  grep -q 'ENC\[' "$tmp" || { echo "sops output is not encrypted; aborting" >&2; exit 1; }
  mv "$tmp" "$OUT"; trap - EXIT
  manifest | apply
  unset -f manifest; unset new
  echo "rotated: wrote $REL and applied Secret $NS/$NAME"
  restart_if_wired
fi

# --- verification (fingerprints only, never values) ----------------------------
live_fp=$(kubectl -n "$NS" get secret "$NAME" -o jsonpath="{.data.$KEY}" | base64 -d | fp)
len=$(kubectl -n "$NS" get secret "$NAME" -o jsonpath="{.data.$KEY}" | base64 -d | wc -c | tr -d ' ')
old_fps=$(committed_values | while read -r v; do printf %s "$v" | fp; done)
echo "live Secret: length=$len fingerprint=$live_fp"
[[ "$len" == 32 ]] || { echo "FAIL: live key is not 32 characters" >&2; exit 1; }
if grep -qx "$live_fp" <<<"$old_fps"; then
  echo "FAIL: live key matches a value committed to git" >&2; exit 1
fi
echo "OK: live key differs from every 32-character cookie_secret ever committed ($(grep -c . <<<"$old_fps") checked)"
echo "next: commit $REL on the PR branch; after merge run: bash scripts/headplane-session-key/verify.sh"
