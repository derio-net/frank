#!/usr/bin/env bash
# Cutover helper for manual operation auth-root-agents-cutover (derio-net/frank#912).
# Run by the operator AFTER the PR merges; nothing here runs in CI.
#
#   matrix           print every SubjectAccessReview cell (root-agents, root-admins, system:masters control)
#   verify           matrix, then exit non-zero unless every cell and every control answered as intended
#   move-membership  Authentik ORM: add claude-agent to root-agents, then remove it from root-admins (idempotent)
#   membership       read back; fails unless claude-agent is only in root-agents
#   token-review     mint a fresh k8s-agent token, TokenReview it, print only the groups; fails on root-admins
#
# `can-i` with --as or --as-group is vacuous through the Omni proxy (frank#963), so every access
# answer comes from a server-side SubjectAccessReview, each deny beside a system:masters control that must
# answer allowed. The token is never printed or placed on a command line.
set -euo pipefail

cd "$(dirname "$0")/.."
# .env sets KUBECONFIG to a RELATIVE path, so source it from the repo root.
if [ -z "${KUBECONFIG:-}" ] && [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

GEN="${ROOT_AGENTS_GEN:-apps/authentik-extras/manifests/root-agents-rbac.yaml}"
PROTECTED="upgrade-sessions cluster-update-fr runs-fr"
EXCLUDED_NS="authentik infisical argocd kube-system longhorn-system"
SECRET_NS="argocd infisical authentik kube-system longhorn-system upgrade-sessions cluster-update-fr runs-fr"
AGENT_USER="claude-agent"
ISSUER_TOKEN_URL="${K8S_AGENT_TOKEN_URL:-https://auth.cluster.derio.net/application/o/token/}"

FAILS=0

generated_namespaces() { sed -n 's/^  namespace: //p' "$GEN"; }

# sar <groups,comma> <verb> <resource> <namespace|-> [subresource]  -> prints true|false
sar() {
  python3 - "$@" <<'PY' | kubectl create -f - -o jsonpath='{.status.allowed}'
import json, sys
groups, verb, resource, ns = sys.argv[1:5]
sub = sys.argv[5] if len(sys.argv) > 5 else ""
ra = {"verb": verb, "resource": resource}
if ns != "-":
    ra["namespace"] = ns
if sub:
    ra["subresource"] = sub
print(json.dumps({"apiVersion": "authorization.k8s.io/v1", "kind": "SubjectAccessReview",
                  "spec": {"user": "root-agents-probe", "groups": groups.split(",") + ["system:authenticated"],
                           "resourceAttributes": ra}}))
PY
}

# cell <label> <groups> <expect allow|deny> <verb> <resource> <namespace|-> [subresource]
cell() {
  local label="$1" groups="$2" expect="$3" verb="$4" resource="$5" ns="$6" sub="${7:-}"
  local got ctl want=true
  got=$(sar "$groups" "$verb" "$resource" "$ns" $sub)
  [ "$expect" = deny ] && want=false
  ctl=$(sar system:masters "$verb" "$resource" "$ns" $sub)
  local status=OK
  if [ "$got" != "$want" ]; then status="MISMATCH"; FAILS=$((FAILS + 1)); fi
  if [ "$ctl" != true ]; then status="$status CONTROL-DENIED"; FAILS=$((FAILS + 1)); fi
  printf '%-12s %-5s %-12s %-28s ns=%-18s got=%-5s control(system:masters)=%-5s %s\n' \
    "$label" "$expect" "$verb" "${resource}${sub:+/$sub}" "$ns" "$got" "$ctl" "$status"
}

matrix() {
  local ns
  FAILS=0
  generated_namespaces | grep -qx monitoring || { echo "monitoring missing from $GEN" >&2; FAILS=$((FAILS + 1)); }
  for ns in $PROTECTED $EXCLUDED_NS; do
    if generated_namespaces | grep -qx "$ns"; then echo "protected or credential-store namespace $ns is bound in $GEN" >&2; FAILS=$((FAILS + 1)); fi
  done

  echo "== group root-agents: allow =="
  cell root-agents root-agents allow get pods monitoring
  cell root-agents root-agents allow get pods monitoring log
  cell root-agents root-agents allow get configmaps monitoring
  cell root-agents root-agents allow list nodes -
  echo "== group root-agents: deny =="
  for ns in $SECRET_NS; do
    cell root-agents root-agents deny get secrets "$ns"
  done
  cell root-agents root-agents deny list pods upgrade-sessions
  for ns in $EXCLUDED_NS; do
    cell root-agents root-agents deny get pods "$ns"
    cell root-agents root-agents deny get pods "$ns" log
    cell root-agents root-agents deny get configmaps "$ns"
  done
  cell root-agents root-agents deny create pods argocd
  cell root-agents root-agents deny impersonate users -
  cell root-agents root-agents deny create serviceaccounts argocd token
  cell root-agents root-agents deny bind clusterroles -
  cell root-agents root-agents deny escalate clusterroles -
  echo "== group root-admins (trusted humans): allow =="
  cell root-admins root-admins allow get secrets argocd
  cell root-admins root-admins allow get secrets upgrade-sessions
  cell root-admins root-admins allow list nodes -
}

verify() {
  matrix
  if [ "$FAILS" -ne 0 ]; then
    echo "verify: $FAILS cell(s) wrong" >&2
    return 1
  fi
  echo "verify: every cell and every system:masters control answered as intended"
}

# Authentik ORM, run inside the server pod. Prints GROUPS=<comma list> afterwards.
orm() {
  local action="$1"
  kubectl exec -i -n authentik deploy/authentik-server -- env ACTION="$action" AGENT="$AGENT_USER" python -c '
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "authentik.root.settings")
import django
django.setup()
from authentik.core.models import Group, User
u = User.objects.get(username=os.environ["AGENT"])
if os.environ["ACTION"] == "move":
    Group.objects.get(name="root-agents").users.add(u)
    Group.objects.get(name="root-admins").users.remove(u)
print("GROUPS=" + ",".join(sorted(g.name for g in u.ak_groups.all())))
'
}

# Every namespace the generated RoleBindings name must exist on the live cluster, or that RoleBinding fails the sync.
namespaces() {
  local want have missing
  want=$(generated_namespaces | sort -u)
  have=$(kubectl get ns -o name | sed 's#^namespace/##' | sort -u)
  missing=$(comm -23 <(printf '%s\n' "$want") <(printf '%s\n' "$have"))
  if [ -n "$missing" ]; then
    echo "namespaces: generated but missing on the cluster:" >&2
    printf '  %s\n' $missing >&2
    return 1
  fi
  echo "namespaces: all $(printf '%s\n' "$want" | wc -l | tr -d ' ') generated namespaces exist"
}

move_membership() {
  orm move
}

membership() {
  local out groups
  out=$(orm read)
  echo "$out"
  groups=${out##*GROUPS=}
  if [ "$groups" != "root-agents" ]; then
    echo "membership: $AGENT_USER must be only in root-agents, found: ${groups:-none}" >&2
    return 1
  fi
}

# Mint, review and discard in one pipeline: neither the secrets nor the token reach argv or stdout.
# Which Authentik user the token belongs to depends on how it is requested:
#   - client_id + client_secret only  -> the provider's synthetic user ("ak-<provider>-client_credentials"),
#     which is NOT claude-agent and carries no group membership;
#   - plus K8S_AGENT_USERNAME / K8S_AGENT_PASSWORD (a service account and its app-password token)
#     -> that service account, i.e. the identity this cutover is about.
# The review prints the resolved username so the operator sees which of the two was exercised; use the
# second mode for the cutover proof. Source the values into the environment by hand (do NOT `source
# .env_agent`: it repoints KUBECONFIG at the agent identity and would run this review as that agent).
token_review() {
  : "${K8S_AGENT_CLIENT_SECRET:?set K8S_AGENT_CLIENT_SECRET (the k8s-agent client secret, kubeconfig-agent.yaml --oidc-client-secret) in the environment}"
  local client_id="${K8S_AGENT_CLIENT_ID:-k8s-agent}" out authenticated user groups cfg
  cfg=$(printf 'data = "grant_type=client_credentials&scope=openid+profile+email"\ndata-urlencode = "client_id=%s"\ndata-urlencode = "client_secret=%s"\n' \
        "$client_id" "$K8S_AGENT_CLIENT_SECRET")
  if [ -n "${K8S_AGENT_USERNAME:-}" ]; then
    : "${K8S_AGENT_PASSWORD:?set K8S_AGENT_PASSWORD (the app-password token of the service account) with K8S_AGENT_USERNAME}"
    cfg+=$(printf '\ndata-urlencode = "username=%s"\ndata-urlencode = "password=%s"\n' "$K8S_AGENT_USERNAME" "$K8S_AGENT_PASSWORD")
  fi
  out=$(
    printf '%s\n' "$cfg" \
      | curl -sS --fail -K - "$ISSUER_TOKEN_URL" \
      | python3 -c '
import json, sys
print(json.dumps({"apiVersion": "authentication.k8s.io/v1", "kind": "TokenReview",
                  "spec": {"token": json.load(sys.stdin)["access_token"]}}))' \
      | kubectl create -f - -o jsonpath='{.status.authenticated}{"|"}{.status.user.username}{"|"}{.status.user.groups}'
  )
  authenticated=${out%%|*}; user=${out#*|}; groups=${user#*|}; user=${user%%|*}
  echo "authenticated: $authenticated  user: $user  groups: $groups"
  if [ "$authenticated" != "true" ]; then
    echo "token-review: the token was not authenticated, so this proves nothing" >&2
    return 1
  fi
  case "$groups" in
    *root-admins*) echo "token-review: the fresh token still carries root-admins" >&2; return 1 ;;
  esac
}

case "${1:-}" in
  matrix) matrix ;;
  namespaces) namespaces ;;
  verify) verify ;;
  move-membership) move_membership ;;
  membership) membership ;;
  token-review) token_review ;;
  *) echo "usage: $0 {matrix|namespaces|verify|move-membership|membership|token-review}" >&2; exit 2 ;;
esac
