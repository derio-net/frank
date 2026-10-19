#!/usr/bin/env bash
# Operator script for the GitHub-preferred CI / Gitea fallback manual operations
# (frank#875, spec docs/superpowers/specs/2026-10-18--cicd--github-preferred-gitea-fallback-design.md §8,
# runbook docs/runbooks/ci-forge-tiers.md).
#
#   bash scripts/ci-budget-ops.sh                  # = status: read-only, every op DONE/OPEN/N/A + evidence
#   bash scripts/ci-budget-ops.sh status [op]      # one op only
#   bash scripts/ci-budget-ops.sh apply <op>       # implement an automatable op (idempotent, asks first)
#   bash scripts/ci-budget-ops.sh apply pre-merge  # batch: gitea-semantics (once), gitea-org, gitea-mirrors
#   bash scripts/ci-budget-ops.sh apply post-merge # batch: github-webhooks, readonly-secrets, orphan-template
#   bash scripts/ci-budget-ops.sh repos            # the repo list this script derives from tiers.yaml
#   bash scripts/ci-budget-ops.sh offboard <org/repo>  # retire a mirrored repo (see the runbook)
#
# ops (in order):  app-permissions  gitea-semantics  gitea-org  gitea-mirrors
#                  github-webhooks  readonly-secrets  orphan-template  go-live
#
# The repo list is DERIVED from apps/ci-budget/tiers.yaml (github-preferred repos of
# derio-net and derio-homelab), so onboarding a new repo = add it to tiers.yaml and
# re-run `apply gitea-mirrors` + `apply github-webhooks`. Nothing here hard-codes repos.
#
# Needs: kubectl (Frank), sops + the age key, gh (personal account; GITHUB_TOKEN is
# unset for gh calls), jq, yq, openssl, git, curl. Secrets are read live and never
# printed. bash 3.2 compatible (macOS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAIN_ROOT="$(cd "$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)/.." && pwd)"  # base clone (holds .talos/ and the SOPS keys)
TIERS="$ROOT/apps/ci-budget/tiers.yaml"
export KUBECONFIG="${KUBECONFIG:-$MAIN_ROOT/.talos/Frank_Kubeconfig.yaml}"
GITEA="${GITEA_URL:-http://192.168.55.209:3000}"
HOOK_URL="https://webhooks.hop.derio.net"
LISTENER_GITEA="http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080"
STATE_DIR="$ROOT/scripts/tmp/ci-budget-ops"   # gitignored; holds proofs that cannot be re-read live
mkdir -p "$STATE_DIR"

# App identities (match apps/tekton/manifests + apps/ci-budget/clustergenerators.yaml)
# <appID> <installID> <k8s Secret in tekton-pipelines> <SOPS fallback file>
# shellcheck disable=SC2034  # read indirectly via eval
APP_derio_net="3994132 138773908 github-app-derio-key github-app-derio-key-tekton.yaml"
# shellcheck disable=SC2034
APP_derio_homelab="4403773 149345112 github-app-homelab-key github-app-homelab-key.yaml"
# shellcheck disable=SC2034
APP_agentic_stoa="3994156 138773982 github-app-stoa-key github-app-stoa-key.yaml"

c_ok=$'\033[32m'; c_bad=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
done_()  { printf '  %sDONE%s  %s\n' "$c_ok" "$c_off" "$*"; }
open_()  { printf '  %sOPEN%s  %s\n' "$c_bad" "$c_off" "$*"; OPEN_COUNT=$((OPEN_COUNT+1)); }
na_()    { printf '  %sN/A %s  %s\n' "$c_dim" "$c_off" "$*"; }
hdr()    { printf '\n== %s ==\n' "$*"; }
die()    { echo "error: $*" >&2; exit 2; }
confirm(){ read -r -p "$1 [y/N] " a; [ "$a" = y ] || [ "$a" = Y ] || die "aborted"; }
OPEN_COUNT=0

for t in kubectl sops gh jq yq openssl git curl; do command -v "$t" >/dev/null || die "missing tool: $t"; done
ghx() { env -u GITHUB_TOKEN gh "$@"; }

# ---- repo lists, derived from tiers.yaml -------------------------------------
preferred() { yq -r ".orgs.\"$1\".repos | to_entries[] | select(.value.tier == \"github-preferred\") | .key" "$TIERS"; }
mirrored_orgs="derio-net derio-homelab"
all_mirrors() { for o in $mirrored_orgs; do for r in $(preferred "$o"); do echo "$o/$r"; done; done; }

# ---- secrets read live ---------------------------------------------------------
k_secret() { kubectl -n "$1" get secret "$2" -o jsonpath="{.data.$3}" 2>/dev/null | base64 -d 2>/dev/null; }
gitea_admin_auth() {
  GU="$(k_secret gitea gitea-secrets username)"; GP="$(k_secret gitea gitea-secrets password)"
  [ -n "$GU" ] && [ -n "$GP" ] || die "cannot read gitea-secrets (ns gitea) — check KUBECONFIG=$KUBECONFIG"
}
gt() { # gitea API as admin: gt METHOD PATH [JSON]
  local m="$1" p="$2" d="${3:-}"
  if [ -n "$d" ]; then curl -sS -u "$GU:$GP" -X "$m" -H 'Content-Type: application/json' -d "$d" "$GITEA/api/v1$p"
  else curl -sS -u "$GU:$GP" -X "$m" "$GITEA/api/v1$p"; fi
}
gt_code() { curl -sS -o /dev/null -w '%{http_code}' -u "$GU:$GP" "$GITEA/api/v1$1"; }

# ---- GitHub App installation tokens from the SOPS PEMs --------------------------
b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }
app_jwt() { # app_jwt <appid> <pem-file>
  local now; now=$(date +%s)
  local h p
  h=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
  p=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' $((now-60)) $((now+540)) "$1" | b64url)
  printf '%s.%s.%s' "$h" "$p" "$(printf '%s.%s' "$h" "$p" | openssl dgst -sha256 -sign "$2" -binary | b64url)"
}
with_pem() { # with_pem <k8s-secret> <sops-file> -> path to a 0600 temp PEM, or empty
  # Live cluster Secret first (what ESO actually uses); SOPS file as fallback.
  local f v; f=$(mktemp "$STATE_DIR/pem.XXXXXX"); chmod 600 "$f"
  k_secret tekton-pipelines "$1" key > "$f" 2>/dev/null || true
  if ! grep -q 'PRIVATE KEY' "$f" 2>/dev/null; then
    v=$(sops -d "$MAIN_ROOT/secrets/github-app/$2" 2>/dev/null | yq -r '.data.key // ""' 2>/dev/null || true)
    if [ -n "$v" ]; then printf '%s' "$v" | base64 -d > "$f" 2>/dev/null || true; fi
  fi
  if grep -q 'PRIVATE KEY' "$f" 2>/dev/null; then echo "$f"; else rm -f "$f"; echo ""; fi
}

# ==================================================================================
st_app_permissions() {
  hdr "app-permissions  [PRE-MERGE, UI + live proof]"
  local org spec appid inst file pem jwt js tok code repos need
  for org in derio-net derio-homelab agentic-stoa; do
    spec=$(eval echo "\$APP_${org//-/_}"); set -- $spec; appid=$1; inst=$2
    pem=$(with_pem "$3" "$4")
    if [ -z "$pem" ]; then open_ "$org: CANNOT VERIFY — App key unreadable (no cluster Secret tekton-pipelines/$3, and SOPS could not decrypt: set SOPS_AGE_KEY_FILE)"; continue; fi
    jwt=$(app_jwt "$appid" "$pem"); rm -f "$pem"
    js=$(curl -sS -H "Authorization: Bearer $jwt" -H 'Accept: application/vnd.github+json' "https://api.github.com/app/installations/$inst")
    if [ "$(echo "$js" | jq -r '.id // empty')" = "" ]; then open_ "$org: CANNOT VERIFY — installation $inst not readable with the App JWT ($(echo "$js" | jq -r '.message // "no response"'))"; continue; fi
    if [ "$(echo "$js" | jq -r '.permissions.organization_administration // "none"')" = read ] || [ "$(echo "$js" | jq -r '.permissions.organization_administration // "none"')" = write ]; then
      done_ "$org: organization Administration permission granted"
    else open_ "$org: organization Administration:read NOT granted (App settings → Permissions, then accept in org settings)"; fi
    if [ "$org" != agentic-stoa ]; then
      for need in actions_variables checks actions pull_requests statuses; do
        if [ "$(echo "$js" | jq -r ".permissions.$need // \"none\"")" = none ]; then open_ "$org: repository permission '$need' missing"; else done_ "$org: '$need' = $(echo "$js" | jq -r ".permissions.$need")"; fi
      done
      [ "$org" = derio-net ] && { [ "$(echo "$js" | jq -r '.permissions.issues // "none"')" = write ] && done_ "derio-net: issues = write (report issue in willikins)" || open_ "derio-net: issues:write missing (report issue in derio-net/willikins)"; }
    fi
    tok=$(curl -sS -X POST -H "Authorization: Bearer $jwt" -H 'Accept: application/vnd.github+json' "https://api.github.com/app/installations/$inst/access_tokens" | jq -r '.token // empty')
    [ -n "$tok" ] || { open_ "$org: could not mint an installation token"; continue; }
    if [ "$org" != agentic-stoa ]; then
      repos=$(curl -sS -H "Authorization: token $tok" "https://api.github.com/installation/repositories?per_page=100" | jq -r '.repositories[].name')
      for r in $(preferred "$org"); do echo "$repos" | grep -qx "$r" && done_ "$org: installation covers $r" || open_ "$org: installation does NOT cover $r (org settings → GitHub Apps → configure → repository access)"; done
      [ "$org" = derio-net ] && { echo "$repos" | grep -qx willikins && done_ "derio-net: installation covers willikins (report target)" || open_ "derio-net: installation does not cover willikins"; }
    fi
    code=$(curl -sS -o "$STATE_DIR/billing-$org.json" -w '%{http_code}' -H "Authorization: token $tok" -H 'Accept: application/vnd.github+json' \
      "https://api.github.com/organizations/$org/settings/billing/usage?year=$(date -u +%Y)&month=$((10#$(date -u +%m)))")
    if [ "$code" = 200 ]; then
      done_ "$org: billing usage readable with the App token (repositoryName e.g. '$(jq -r '[.usageItems[]?|select(.repositoryName)][0].repositoryName // "-"' "$STATE_DIR/billing-$org.json")'; Actions SKUs: $(jq -r '[.usageItems[]?|select(.product=="actions")|.sku]|unique|join(", ")' "$STATE_DIR/billing-$org.json"))"
    else open_ "$org: billing usage HTTP $code with the App token — STOP before merge (spec §8)"; fi
  done
}

# ==================================================================================
st_gitea_semantics() {
  hdr "gitea-semantics  [PRE-MERGE, one-off proof]"
  if [ -s "$STATE_DIR/gitea-semantics.ok" ]; then done_ "$(cat "$STATE_DIR/gitea-semantics.ok")"
  else open_ "not proven yet — run: bash scripts/ci-budget-ops.sh apply gitea-semantics"; fi
}
ap_gitea_semantics() {
  gitea_admin_auth
  local org=derio-homelab repo=ci-var-probe-$$ run
  confirm "Create scratch repo $org/$repo (+ org variable CI_PROBE), run 4 tiny workflows, then delete both?"
  gt POST "/orgs/$org/repos" '{"name":"'"$repo"'","private":true,"auto_init":true,"default_branch":"main"}' >/dev/null
  gt PATCH "/repos/$org/$repo" '{"has_actions":true}' >/dev/null
  gt POST "/orgs/$org/actions/variables/CI_PROBE" '{"value":"org"}' >/dev/null || true
  gt POST "/repos/$org/$repo/actions/variables/CI_PROBE" '{"value":"repo"}' >/dev/null
  wf_plain=$(printf 'on:\n  push:\n    branches: [main, "sync-rerun-**"]\njobs:\n  repo-wins:\n    if: vars.CI_PROBE == '"'"'repo'"'"'\n    runs-on: ubuntu-latest\n    steps: [{run: "true"}]\n  org-wins:\n    if: vars.CI_PROBE != '"'"'repo'"'"'\n    runs-on: ubuntu-latest\n    steps: [{run: "true"}]\n')
  wf_paths=$(printf 'on:\n  push:\n    branches: ["sync-rerun-**"]\n    paths: ["src/**"]\njobs:\n  paths-run:\n    runs-on: ubuntu-latest\n    steps: [{run: "true"}]\n')
  gt POST "/repos/$org/$repo/contents/.github/workflows/plain.yml" "$(jq -n --arg c "$(printf '%s' "$wf_plain" | base64)" '{content:$c,message:"probe",branch:"main"}')" >/dev/null
  gt POST "/repos/$org/$repo/contents/.github/workflows/paths.yml" "$(jq -n --arg c "$(printf '%s' "$wf_paths" | base64)" '{content:$c,message:"probe2",branch:"main"}')" >/dev/null
  # The branch tip must touch src/**, or the paths filter is legitimately unmatched
  # and the probe proves nothing (the first version of this probe had that flaw).
  gt POST "/repos/$org/$repo/contents/src/probe.txt" "$(jq -n --arg c "$(printf 'probe\n' | base64)" '{content:$c,message:"touch src",branch:"main"}')" >/dev/null
  sleep 5
  gt POST "/repos/$org/$repo/branches" '{"new_branch_name":"sync-rerun-probe","old_branch_name":"main"}' >/dev/null
  echo "waiting up to 15 min for the runner (capacity 2, shared)…"
  local i js res_repo res_branch res_paths
  for i in $(seq 1 90); do
    js=$(gt GET "/repos/$org/$repo/actions/tasks?limit=50")
    res_repo=$(echo "$js" | jq -r '[.workflow_runs[]? | select(.name=="repo-wins" and .head_branch=="main")][0].status // empty')
    res_branch=$(echo "$js" | jq -r '[.workflow_runs[]? | select(.head_branch=="sync-rerun-probe" and .name=="repo-wins")][0].status // empty')
    res_paths=$(echo "$js" | jq -r '[.workflow_runs[]? | select(.head_branch=="sync-rerun-probe" and .name=="paths-run")][0].status // empty')
    case "$res_repo$res_branch" in
      *success*success*)
        [ -n "$res_paths" ] && [ "$res_paths" != waiting ] && [ "$res_paths" != running ] && break
        settle=$(( ${settle:-0} + 1 )); [ "$settle" -ge 18 ] && break ;;   # 3 more min for the paths run to appear
    esac
    sleep 10
  done
  local orgwins; orgwins=$(echo "$js" | jq -r '[.workflow_runs[]? | select(.name=="org-wins")][0].status // "absent"')
  echo "repo-wins@main=$res_repo  org-wins=$orgwins  repo-wins@sync-rerun=$res_branch  paths-filtered@sync-rerun=${res_paths:-NOT-STARTED}"
  gt DELETE "/repos/$org/$repo" >/dev/null; gt DELETE "/orgs/$org/actions/variables/CI_PROBE" >/dev/null || true
  if [ "$res_repo" = success ] && [ "$res_branch" = success ]; then
    printf 'proven %s: repo variable overrides org (repo-wins=success, org-wins=%s); API-created branch fires push runs; paths-filtered workflow on new branch: %s\n' \
      "$(date -u +%FT%TZ)" "$orgwins" "${res_paths:-NOT-STARTED within 3 min after the plain runs, with a tip commit touching src/** — re-run of path-filtered workflows needs another mechanism before go-live}" > "$STATE_DIR/gitea-semantics.ok"
    cat "$STATE_DIR/gitea-semantics.ok"
  else die "semantics NOT proven (see statuses above) — return to the design before merging"; fi
}

# ==================================================================================
st_gitea_org() {
  hdr "gitea-org  [PRE-MERGE]"
  gitea_admin_auth
  [ "$(gt_code /orgs/derio-net)" = 200 ] && done_ "Gitea org derio-net exists" || open_ "Gitea org derio-net missing"
  for o in derio-net derio-homelab; do
    if gt GET "/orgs/$o/teams" | jq -e 'type=="array"' >/dev/null 2>&1; then
      local owners; owners=$(gt GET "/orgs/$o/teams" | jq -r '.[]|select(.name=="Owners")|.id')
      gt GET "/teams/$owners/members" | jq -r '.[].login' | grep -qx ci-budget && done_ "$o: ci-budget is an org owner" || open_ "$o: ci-budget not an org owner"
      [ "$o" = derio-net ] && { gt GET "/orgs/$o/teams" | jq -r '.[]|select(.name=="mirror-writers")|.id' | head -1 | while read -r tid; do gt GET "/teams/$tid/members" | jq -r '.[].login'; done | grep -qx stoa-bot && done_ "derio-net: stoa-bot has write (team mirror-writers)" || open_ "derio-net: stoa-bot lacks write"; }
      gt GET "/orgs/$o/hooks" | jq -e --arg u "$LISTENER_GITEA" '[.[]|select(.config.url==$u and (.events|index("status")) and .active)]|length>0' >/dev/null \
        && done_ "$o: org status webhook → gitea-listener" || open_ "$o: org status webhook missing"
    else open_ "$o: org teams not readable (does the org exist?)"; fi
  done
  for s in ci-budget-gitea ci-budget-gitea-probe; do
    kubectl -n tekton-pipelines get secret "$s" >/dev/null 2>&1 && done_ "Secret tekton-pipelines/$s present" || open_ "Secret tekton-pipelines/$s missing"
  done
}
ap_gitea_org() {
  gitea_admin_auth
  confirm "Create/ensure Gitea org derio-net, team mirror-writers(stoa-bot), user ci-budget (owner of derio-net + derio-homelab), its token, a read:admin probe token, and status webhooks?"
  [ "$(gt_code /orgs/derio-net)" = 200 ] || gt POST /orgs '{"username":"derio-net","visibility":"private"}' >/dev/null
  local tid; tid=$(gt GET /orgs/derio-net/teams | jq -r '.[]|select(.name=="mirror-writers")|.id' | head -1)
  [ -n "$tid" ] || tid=$(gt POST /orgs/derio-net/teams '{"name":"mirror-writers","permission":"write","includes_all_repositories":true,"units":["repo.code","repo.actions"]}' | jq -r .id)
  gt PUT "/teams/$tid/members/stoa-bot" >/dev/null
  if [ "$(gt_code /users/ci-budget)" != 200 ]; then
    CB_PW="$(openssl rand -base64 30)"
    gt POST /admin/users "$(jq -n --arg p "$CB_PW" '{username:"ci-budget",email:"ci-budget@noreply.invalid",password:$p,must_change_password:false,visibility:"private"}')" >/dev/null
  fi
  for o in derio-net derio-homelab; do
    local ow; ow=$(gt GET "/orgs/$o/teams" | jq -r '.[]|select(.name=="Owners")|.id'); gt PUT "/teams/$ow/members/ci-budget" >/dev/null
    gt GET "/orgs/$o/hooks" | jq -e --arg u "$LISTENER_GITEA" '[.[]|select(.config.url==$u and (.events|index("status")))]|length>0' >/dev/null || \
      gt POST "/orgs/$o/hooks" "$(jq -n --arg u "$LISTENER_GITEA" '{type:"gitea",active:true,events:["status"],config:{url:$u,content_type:"json"}}')" >/dev/null
  done
  if ! kubectl -n tekton-pipelines get secret ci-budget-gitea >/dev/null 2>&1; then
    [ -n "${CB_PW:-}" ] || { CB_PW="$(openssl rand -base64 30)"; gt PATCH /admin/users/ci-budget "$(jq -n --arg p "$CB_PW" '{login_name:"ci-budget",source_id:0,password:$p,must_change_password:false}')" >/dev/null; }
    curl -sS -u "ci-budget:$CB_PW" -X DELETE "$GITEA/api/v1/users/ci-budget/tokens/ci-budget-watcher" >/dev/null || true
    local tok; tok=$(curl -sS -u "ci-budget:$CB_PW" -X POST -H 'Content-Type: application/json' -d '{"name":"ci-budget-watcher","scopes":["write:repository","write:organization"]}' "$GITEA/api/v1/users/ci-budget/tokens" | jq -r '.sha1 // empty')
    [ -n "$tok" ] || die "could not mint the ci-budget token"
    write_sops_secret ci-budget-gitea token "$tok"; unset tok
  fi
  if ! kubectl -n tekton-pipelines get secret ci-budget-gitea-probe >/dev/null 2>&1; then
    curl -sS -u "$GU:$GP" -X DELETE "$GITEA/api/v1/users/$GU/tokens/ci-budget-probe" >/dev/null || true
    local pt; pt=$(curl -sS -u "$GU:$GP" -X POST -H 'Content-Type: application/json' -d '{"name":"ci-budget-probe","scopes":["read:admin"]}' "$GITEA/api/v1/users/$GU/tokens" | jq -r '.sha1 // empty')
    [ -n "$pt" ] || die "could not mint the probe token"
    write_sops_secret ci-budget-gitea-probe token "$pt"; unset pt
  fi
  unset CB_PW; st_gitea_org
}
write_sops_secret() { # name key value -> SOPS file in the checkout + kubectl apply
  # Plaintext lives ONLY in a 0600 temp file outside the repo, removed on any exit;
  # the tracked path is written only after encryption succeeded.
  local name="$1" key="$2" val="$3" dir="$ROOT/secrets/ci-budget" f tmp enc
  mkdir -p "$dir"; f="$dir/$name.yaml"
  tmp=$(mktemp "${TMPDIR:-/tmp}/ci-budget-secret.XXXXXX"); chmod 600 "$tmp"
  enc="$f.enc.$$"
  trap 'rm -f "$tmp" "$enc"' EXIT INT TERM
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n  namespace: tekton-pipelines\ntype: Opaque\nstringData:\n  %s: %s\n' "$name" "$key" "$val" > "$tmp"
  # --filename-override: sops matches .sops.yaml creation rules against the INPUT
  # path, and the temp file's name matches none ("no matching creation rules").
  (cd "$ROOT" && sops --encrypt --filename-override "secrets/ci-budget/$name.yaml" \
       --input-type yaml --output-type yaml "$tmp") > "$enc" || die "sops encryption failed; nothing written to $f"
  grep -q '^sops:' "$enc" || die "encrypted output looks wrong; nothing written to $f"
  mv "$enc" "$f"
  kubectl apply -f "$tmp" >/dev/null   # apply from the plaintext temp: no age key needed for this step
  rm -f "$tmp"; trap - EXIT INT TERM
  echo "  wrote $f (SOPS-encrypted) and applied Secret tekton-pipelines/$name — commit the file"
}

# ==================================================================================
st_gitea_mirrors() {
  hdr "gitea-mirrors  [PRE-MERGE, Gitea side]"
  gitea_admin_auth
  local full js gh_head gt_head def
  for full in $(all_mirrors); do
    js=$(gt GET "/repos/$full")
    if [ "$(echo "$js" | jq -r '.id // empty')" = "" ]; then open_ "$full: Gitea repo missing"; continue; fi
    [ "$(echo "$js" | jq -r .has_actions)" = true ] && done_ "$full: exists, Actions enabled" || open_ "$full: Actions disabled (has_actions=false)"
    [ "$(gt_code "/repos/$full/actions/variables/CI_AUTHORITY")" = 200 ] && done_ "$full: repo variable CI_AUTHORITY=$(gt GET "/repos/$full/actions/variables/CI_AUTHORITY" | jq -r .data)" || open_ "$full: repo variable CI_AUTHORITY missing"
    def=$(ghx api "repos/$full" --jq .default_branch)
    gh_head=$(ghx api "repos/$full/branches/$def" --jq .commit.sha 2>/dev/null || echo "?")
    gt_head=$(gt GET "/repos/$full/branches/$def" | jq -r '.commit.id // "missing"')
    [ "$gh_head" = "$gt_head" ] && done_ "$full: $def in sync ($gt_head)" || open_ "$full: $def GitHub=$gh_head Gitea=$gt_head (backfill or wait for the reconciler)"
  done
  # drift the other way: a Gitea mirror whose repo left tiers.yaml (offboarding half-done)
  local o name known
  known=" $(all_mirrors | tr '\n' ' ') $(for o in $mirrored_orgs; do yq -r ".orgs.\"$o\".repos | to_entries[] | select(.value.tier == \"gitea-only\") | .key" "$TIERS" | sed "s#^#$o/#"; done | tr '\n' ' ') "
  for o in $mirrored_orgs; do
    for name in $(gt GET "/orgs/$o/repos?limit=50" | jq -r 'if type=="array" then .[].name else empty end'); do
      case "$known" in *" $o/$name "*) ;; *) open_ "$o/$name: Gitea mirror not in tiers.yaml — finish offboarding: bash scripts/ci-budget-ops.sh offboard $o/$name";; esac
    done
  done
}
ap_gitea_mirrors() {
  gitea_admin_auth
  echo "repos: $(all_mirrors | tr '\n' ' ')"
  confirm "Create missing Gitea repos (private, Actions on, CI_AUTHORITY=github) and backfill branches+tags from GitHub?"
  local full org repo def tmp auth
  auth=$(printf '%s:%s' "$GU" "$GP" | base64)
  for full in $(all_mirrors); do
    org=${full%/*}; repo=${full#*/}
    def=$(ghx api "repos/$full" --jq .default_branch)
    [ "$(gt_code "/repos/$full")" = 200 ] || gt POST "/orgs/$org/repos" "$(jq -n --arg n "$repo" --arg d "$def" '{name:$n,private:true,default_branch:$d}')" >/dev/null
    gt PATCH "/repos/$full" '{"has_actions":true}' >/dev/null
    [ "$(gt_code "/repos/$full/actions/variables/CI_AUTHORITY")" = 200 ] || gt POST "/repos/$full/actions/variables/CI_AUTHORITY" '{"value":"github"}' >/dev/null
    tmp=$(mktemp -d "$STATE_DIR/mirror.XXXXXX")
    echo "-> backfilling $full ($def)"
    ghx repo clone "$full" "$tmp/r" -- --mirror -q
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader GIT_CONFIG_VALUE_0="Authorization: Basic $auth" \
      git -C "$tmp/r" push -q "$GITEA/$full.git" '+refs/heads/*:refs/heads/*' '+refs/tags/*:refs/tags/*'
    gt PATCH "/repos/$full" "$(jq -n --arg d "$def" '{default_branch:$d}')" >/dev/null
    rm -rf "$tmp"
  done
  st_gitea_mirrors
}

# ==================================================================================
st_github_webhooks() {
  hdr "github-webhooks  [POST-MERGE — the triggers must be live first]"
  local full
  for full in $(all_mirrors); do
    ghx api "repos/$full/hooks" 2>/dev/null | jq -e --arg u "$HOOK_URL" '[.[]|select((.config.url|rtrimstr("/"))==$u and .active and (.events|index("push")) and (.events|index("pull_request")))]|length>0' >/dev/null \
      && done_ "$full: webhook push+pull_request → $HOOK_URL" || open_ "$full: webhook missing or lacks push/pull_request"
  done
}
ap_github_webhooks() {
  confirm "Create/patch GitHub repo webhooks (push, pull_request) → $HOOK_URL on $(all_mirrors | wc -l | tr -d ' ') repos? (only after the frank PR is merged and synced)"
  local full org sec id
  for full in $(all_mirrors); do
    org=${full%/*}; sec=$(k_secret tekton-pipelines "$org-github-webhook-secret" secret)
    [ -n "$sec" ] || die "cannot read Secret tekton-pipelines/$org-github-webhook-secret"
    id=$(ghx api "repos/$full/hooks" | jq -r --arg u "$HOOK_URL" '[.[]|select((.config.url|rtrimstr("/"))==$u)][0].id // empty')
    if [ -n "$id" ]; then
      jq -n --arg s "$sec" --arg u "$HOOK_URL" '{active:true,events:["push","pull_request"],config:{url:$u,content_type:"json",secret:$s,insecure_ssl:"0"}}' | ghx api -X PATCH "repos/$full/hooks/$id" --input - >/dev/null
    else
      jq -n --arg s "$sec" --arg u "$HOOK_URL" '{name:"web",active:true,events:["push","pull_request"],config:{url:$u,content_type:"json",secret:$s,insecure_ssl:"0"}}' | ghx api -X POST "repos/$full/hooks" --input - >/dev/null
    fi
  done
  unset sec; st_github_webhooks
}

# ==================================================================================
st_readonly_secrets() {
  hdr "readonly-secrets  [POST-MERGE]"
  gitea_admin_auth
  local org repo name any=0
  for org in $mirrored_orgs; do
    for repo in $(yq -r ".orgs.\"$org\".repos | to_entries[] | select(.value.gitea_secrets) | .key" "$TIERS"); do
      for name in $(yq -r ".orgs.\"$org\".repos.\"$repo\".gitea_secrets[]" "$TIERS"); do
        any=1
        gt GET "/repos/$org/$repo/actions/secrets" | jq -r 'if type=="array" then .[].name else empty end' | grep -qx "$name" \
          && done_ "$org/$repo: repo secret $name present" || open_ "$org/$repo: repo secret $name missing (apply readonly-secrets)"
      done
    done
  done
  [ $any = 1 ] || na_ "no gitea_secrets declared in tiers.yaml"
}
ap_readonly_secrets() {
  gitea_admin_auth
  local org repo name val
  for org in $mirrored_orgs; do
    for repo in $(yq -r ".orgs.\"$org\".repos | to_entries[] | select(.value.gitea_secrets) | .key" "$TIERS"); do
      for name in $(yq -r ".orgs.\"$org\".repos.\"$repo\".gitea_secrets[]" "$TIERS"); do
        echo "$org/$repo needs repo secret $name (READ-ONLY credential; GitHub secrets cannot be read back, paste it from its source)."
        read -r -s -p "  value for $name (empty = skip): " val; echo
        [ -n "$val" ] || { echo "  skipped"; continue; }
        gt PUT "/repos/$org/$repo/actions/secrets/$name" "$(jq -n --arg v "$val" '{data:$v}')" >/dev/null; unset val
        echo "  set (repository secret on $org/$repo only)"
      done
    done
  done
  st_readonly_secrets
}

# ==================================================================================
st_orphan_template() {
  hdr "orphan-template  [POST-MERGE]"
  if ! kubectl -n tekton-pipelines get triggertemplate derio-homelab-main-sync-template >/dev/null 2>&1; then na_ "renamed trigger not synced yet (frank PR not merged/synced)"; return; fi
  kubectl -n tekton-pipelines get triggertemplate derio-homelab-kid-laptops-main-sync-template >/dev/null 2>&1 \
    && open_ "orphan TriggerTemplate derio-homelab-kid-laptops-main-sync-template still live (apply orphan-template)" \
    || done_ "orphan TriggerTemplate gone"
}
ap_orphan_template() {
  kubectl -n tekton-pipelines get triggertemplate derio-homelab-main-sync-template >/dev/null || die "new template not synced yet — merge + sync first"
  confirm "Delete TriggerTemplate derio-homelab-kid-laptops-main-sync-template?"
  kubectl -n tekton-pipelines delete triggertemplate derio-homelab-kid-laptops-main-sync-template --ignore-not-found
  st_orphan_template
}

# ==================================================================================
st_go_live() {
  hdr "go-live  [POST-MERGE, per org, a git change]"
  local org mode
  if kubectl -n tekton-pipelines get cronjob ci-budget-watcher >/dev/null 2>&1; then
    done_ "CronJob ci-budget-watcher deployed (last schedule: $(kubectl -n tekton-pipelines get cronjob ci-budget-watcher -o jsonpath='{.status.lastScheduleTime}'))"
  else na_ "ci-budget-watcher not deployed yet"; fi
  for org in $mirrored_orgs; do
    mode=$(yq -r ".orgs.\"$org\".mode" "$TIERS")
    [ "$mode" = live ] && done_ "$org: mode=live (in this checkout's tiers.yaml)" || open_ "$org: mode=$mode — set to live in apps/ci-budget/tiers.yaml via a PR once the org's repo PRs merged and Test Plan rows 1–8 pass"
  done
}

# ==================================================================================
offboard() { # offboard <org/repo>: retire a mirrored repo (deleted, made public, or moved to github-only)
  local full="$1" org repo id gh_exists
  [ -n "$full" ] || die "offboard <org/repo>"
  org=${full%/*}; repo=${full#*/}
  gitea_admin_auth
  if yq -e ".orgs.\"$org\".repos.\"$repo\"" "$TIERS" >/dev/null 2>&1; then
    echo "note: $full is still in this checkout's tiers.yaml — remove it in the frank PR too (CI guards then list every other place to drop it)."
  fi
  gh_exists=0; ghx api "repos/$full" >/dev/null 2>&1 && gh_exists=1
  confirm "Offboard $full: GitHub CI_AUTHORITY -> github FIRST (so GitHub never stays skipped), delete its GitHub webhook to $HOOK_URL, then DELETE the Gitea mirror?"
  if [ $gh_exists = 1 ]; then
    ghx api -X PATCH "repos/$full/actions/variables/CI_AUTHORITY" -f name=CI_AUTHORITY -f value=github >/dev/null 2>&1 \
      || ghx api -X POST "repos/$full/actions/variables" -f name=CI_AUTHORITY -f value=github >/dev/null
    echo "  GitHub CI_AUTHORITY=github (gated jobs run on GitHub again)"
    id=$(ghx api "repos/$full/hooks" | jq -r --arg u "$HOOK_URL" '[.[]|select((.config.url|rtrimstr("/"))==$u)][0].id // empty')
    [ -z "$id" ] || { ghx api -X DELETE "repos/$full/hooks/$id" >/dev/null; echo "  GitHub webhook deleted"; }
  else echo "  GitHub repo gone: variable and webhook went with it"; fi
  if [ "$(gt_code "/repos/$full")" = 200 ]; then gt DELETE "/repos/$full" >/dev/null; echo "  Gitea mirror deleted (sync-pr/sync-rerun refs with it)"; fi
  echo "done. Remaining: the tiers.yaml PR (and, if the repo still exists, the App installation's repository access)."
}

# ==================================================================================
OPS="app-permissions gitea-semantics gitea-org gitea-mirrors github-webhooks readonly-secrets orphan-template go-live"
fn() { echo "$1" | tr '-' '_'; }
cmd="${1:-status}"
case "$cmd" in
  status)
    set +e   # report every check; one failing probe must not hide the rest
    if [ -n "${2:-}" ]; then "st_$(fn "$2")"; else for o in $OPS; do "st_$(fn "$o")"; done; fi
    printf '\n%d open item(s).\n' "$OPEN_COUNT" ;;
  apply)
    [ -n "${2:-}" ] || die "apply <op>"
    case "$2" in
      pre-merge)
        st_app_permissions
        [ -s "$STATE_DIR/gitea-semantics.ok" ] || ap_gitea_semantics
        ap_gitea_org; ap_gitea_mirrors
        echo; echo "pre-merge batch done. Commit secrets/ci-budget/*.yaml if new, fix any OPEN app-permissions items in the UI, then: $0 status";;
      post-merge)
        kubectl -n tekton-pipelines get triggertemplate derio-homelab-main-sync-template >/dev/null 2>&1 || die "frank PR not merged/synced yet (renamed trigger absent)"
        ap_github_webhooks; ap_readonly_secrets; ap_orphan_template
        echo; echo "post-merge batch done. Remaining: Test Plan rows, then go-live per org (a PR). $0 status";;
      app-permissions) echo "UI-only: GitHub → Settings → Developer settings → GitHub Apps → <App> → Permissions; then each org → Settings → GitHub Apps → review request. Verify with: bash $0 status app-permissions";;
      go-live) echo "A git change: set orgs.<org>.mode: live in apps/ci-budget/tiers.yaml (PR). Verify with: bash $0 status go-live";;
      *) "ap_$(fn "$2")";;
    esac ;;
  repos) all_mirrors ;;
  offboard) offboard "${2:-}" ;;
  *) die "usage: $0 [status [op] | apply <op> | repos | offboard <org/repo>]" ;;
esac
