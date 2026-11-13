# Shared helpers for rotate.sh / verify.sh. Sourced, not executed. bash 3.2-safe.
# Nothing here prints a key: values flow only through pipes into fp/forge_cookie.

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
# .env_hop and the Hop kubeconfig are gitignored and live in the MAIN checkout,
# not in an fr worktree.
MAIN=$(cd "$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir)/.." && pwd)
NS=headscale-system
NAME=headplane-cookie-secret
KEY=cookie-secret
REL=secrets/hop/headplane-cookie-secret.yaml

hop_context() {
  [[ -f "$MAIN/.env_hop" ]] || { echo "missing $MAIN/.env_hop" >&2; return 1; }
  # shellcheck disable=SC1091
  KUBECONFIG=$(cd "$MAIN" && unset KUBECONFIG && source ./.env_hop >/dev/null 2>&1 \
    && [[ -n "${KUBECONFIG:-}" ]] && realpath "$KUBECONFIG") \
    || { echo ".env_hop did not set KUBECONFIG" >&2; return 1; }
  export KUBECONFIG
  # Prove this is Hop, not whatever context happens to be ambient.
  kubectl get node hop-1 >/dev/null 2>&1 || { echo "kubeconfig does not reach Hop (no node hop-1)" >&2; return 1; }
}

fp() { shasum -a 256 | cut -c1-12; }

# Every 32-character cookie_secret value ever committed anywhere in the repo,
# one per line (the schema accepts exactly 32, so shorter/longer strings can
# never have been a live key). Includes the current placeholder.
committed_values() {
  git -C "$REPO" log --all -p -G 'cookie_secret:' -- . \
    | grep -E '^[-+][[:space:]]+cookie_secret:' \
    | sed -E 's/^[-+][[:space:]]+cookie_secret:[[:space:]]*//; s/[[:space:]]+#.*$//' \
    | tr -d "\"' " \
    | awk 'length($0) == 32' | sort -u
}
