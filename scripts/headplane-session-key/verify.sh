#!/usr/bin/env bash
# Post-merge check for Headplane's session-signing key on Hop
# (manual-op edge-hop-headplane-cookie-secret-rotation, ice#5).
#
# Asks the RUNNING Headplane which key it accepts, using a signature oracle:
# GET /admin/login with an hp_sess cookie returns 302 (to /admin/machines) when
# the cookie's signature verifies and 200 (login page) when it does not. The
# probe session carries a dummy Headscale API key, so even an accepted cookie
# cannot reach Headscale. Keys never leave this shell: each is piped into
# forge_cookie.py, and only the resulting HMAC cookie is sent to the pod.
#
# Expect: the live Secret's key -> 302 with a Secure cookie; the file
# placeholder and every value ever committed -> 200.
#
# Usage: bash scripts/headplane-session-key/verify.sh
set -euo pipefail
set +x

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
MAIN=$(cd "$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir)/.." && pwd)
NS=headscale-system
# shellcheck disable=SC1091
KUBECONFIG=$(cd "$MAIN" && source ./.env_hop >/dev/null 2>&1 && realpath "$KUBECONFIG")
export KUBECONFIG

kubectl -n "$NS" rollout status deploy/headplane --timeout=120s >/dev/null
if ! kubectl -n "$NS" get deploy headplane -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' | grep -qw HEADPLANE_SERVER__COOKIE_SECRET; then
  echo "FAIL: the live Deployment does not set HEADPLANE_SERVER__COOKIE_SECRET (has the PR merged and synced?)" >&2; exit 1
fi

# node is the only HTTP client guaranteed in the image; redirect:'manual' keeps the 302 visible.
probe() {  # $1 = cookie; prints "<status> <secure-flag>"
  kubectl -n "$NS" exec deploy/headplane -- node -e '
    fetch("http://127.0.0.1:3000/admin/login", {redirect: "manual", headers: {cookie: process.argv[1]}})
      .then(r => console.log(r.status, /;\s*Secure/i.test(r.headers.get("set-cookie") || "") ? "secure" : "-"))
      .catch(e => { console.log("ERR", e.message); process.exit(1); });' "$1"
}

fail=0
new_cookie=$(kubectl -n "$NS" get secret headplane-cookie-secret -o jsonpath='{.data.cookie-secret}' | base64 -d | python3 "$HERE/forge_cookie.py")
read -r st sec <<<"$(probe "$new_cookie")"
if [[ "$st" == 302 && "$sec" == secure ]]; then echo "OK   live Secret key accepted (302, Secure cookie)"
else echo "FAIL live Secret key: status=$st cookie=$sec (want 302 secure)"; fail=1; fi

old_values=$(git -C "$REPO" log --all -p -- clusters/hop/apps/headplane blog/content/docs/building/17-public-edge \
  | grep -E '^[-+][[:space:]]+cookie_secret:' \
  | sed -E 's/.*cookie_secret:[[:space:]]*//' | tr -d "\"' " | grep -v '^<' | sort -u)
n=0
while read -r v; do
  [[ -z "$v" ]] && continue
  n=$((n+1))
  read -r st _ <<<"$(probe "$(printf %s "$v" | python3 "$HERE/forge_cookie.py")")"
  if [[ "$st" == 200 ]]; then echo "OK   committed value #$n rejected (200)"
  else echo "FAIL committed value #$n: status=$st (want 200)"; fail=1; fi
done <<<"$old_values"
unset old_values new_cookie
[[ $n -ge 2 ]] || { echo "FAIL: expected at least 2 committed values to test, found $n" >&2; fail=1; }

exit $fail
