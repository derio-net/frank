#!/usr/bin/env bash
# Wire up AWX from awx-hosts.env and prove the gate with an ad-hoc ansible ping.
# Creates (idempotently): Organization, Machine Credential (new SSH key),
# Inventory + hosts. Then runs `ansible -m ping` and reports per-host result.
# Runs on your Mac (needs the local private key). No secrets are printed.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
ENV_FILE="${1:-$REPO/scripts/tmp/awx-hosts.env}"
# shellcheck disable=SC1090
source "$ENV_FILE"

ADMIN_PW="$(kubectl -n awx get secret awx-admin-password -o jsonpath='{.data.password}' | base64 -d)"
BASE="${AWX_API_URL%/}/api/v2"

api()  { curl -sk -u "admin:${ADMIN_PW}" "$@"; }                       # generic
getj() { api "$BASE/$1"; }                                            # GET
postj(){ api -H 'Content-Type: application/json' -X POST "$BASE/$1" --data-binary @-; }  # POST stdin
patchj(){ api -H 'Content-Type: application/json' -X PATCH "$BASE/$1" --data-binary @-; } # PATCH stdin

# get_or_create <endpoint> <name> <create-json-on-stdin> -> prints id
get_or_create() {
  local ep="$1" name="$2" id enc
  enc="$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$name")"
  id="$(getj "${ep}/?name=${enc}" | python3 -c 'import sys,json;r=json.load(sys.stdin)["results"];print(r[0]["id"] if r else "")')"
  if [ -n "$id" ]; then echo "$id"; return; fi
  postj "${ep}/" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("id") or sys.exit("CREATE FAILED: "+json.dumps(d)))'
}

echo "==> Organization: ${AWX_ORG}"
ORG_PAYLOAD="$(ORG="$AWX_ORG" python3 -c 'import os,json;print(json.dumps({"name":os.environ["ORG"]}))')"
ORG_ID="$(get_or_create organizations "$AWX_ORG" <<<"$ORG_PAYLOAD")"
echo "    org id=${ORG_ID}"

echo "==> Machine Credential: ${AWX_CREDENTIAL}"
CT_ID="$(getj 'credential_types/?name=Machine' | python3 -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["id"])')"
# Resolve the SSH user from the first host row (col 3) or ssh -G.
FIRST_ALIAS="$(printf '%s\n' "$AWX_HOSTS" | sed '/^[[:space:]]*#/d;/^[[:space:]]*$/d' | head -1 | cut -d'|' -f1 | xargs)"
SSH_USER="$(printf '%s\n' "$AWX_HOSTS" | sed '/^[[:space:]]*#/d;/^[[:space:]]*$/d' | head -1 | cut -d'|' -f3 | xargs)"
[ -z "$SSH_USER" ] && SSH_USER="$(ssh -G "$FIRST_ALIAS" 2>/dev/null | awk '/^user /{print $2;exit}')"
echo "    ssh user=${SSH_USER}; key=${AWX_KEY_PATH}"
CRED_PAYLOAD="$(CN="$AWX_CREDENTIAL" CT="$CT_ID" OID="$ORG_ID" CU="$SSH_USER" KEY="$(cat "$AWX_KEY_PATH")" \
  python3 -c 'import os,json;print(json.dumps({"name":os.environ["CN"],"credential_type":int(os.environ["CT"]),"organization":int(os.environ["OID"]),"inputs":{"username":os.environ["CU"],"ssh_key_data":os.environ["KEY"]}}))')"
CRED_ID="$(get_or_create credentials "$AWX_CREDENTIAL" <<<"$CRED_PAYLOAD")"
echo "    credential id=${CRED_ID}"

echo "==> Inventory: ${AWX_INVENTORY}"
INV_PAYLOAD="$(IN="$AWX_INVENTORY" OID="$ORG_ID" python3 -c 'import os,json;print(json.dumps({"name":os.environ["IN"],"organization":int(os.environ["OID"])}))')"
INV_ID="$(get_or_create inventories "$AWX_INVENTORY" <<<"$INV_PAYLOAD")"
echo "    inventory id=${INV_ID}"

echo "==> setting inventory vars (skip host-key prompt on first contact)…"
INV_VARS_PAYLOAD="$(python3 -c 'import json;print(json.dumps({"variables":"ansible_ssh_common_args: \"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null\""}))')"
printf '%s' "$INV_VARS_PAYLOAD" | patchj "inventories/${INV_ID}/" >/dev/null && echo "    ok"

echo "==> Hosts:"
while IFS='|' read -r alias host user becomev; do
  alias="$(printf '%s' "${alias:-}" | sed 's/#.*//;s/^[[:space:]]*//;s/[[:space:]]*$//')"
  host="$(printf '%s' "${host:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [ -z "$alias" ] && continue
  [ -z "$host" ] && host="$(ssh -G "$alias" 2>/dev/null | awk '/^hostname /{print $2;exit}')"
  exists="$(getj "inventories/${INV_ID}/hosts/?name=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$alias")" | python3 -c 'import sys,json;print(json.load(sys.stdin)["count"])')"
  if [ "$exists" != "0" ]; then echo "    - ${alias} (exists)"; continue; fi
  ALIAS="$alias" HOST="$host" python3 -c 'import os,json;print(json.dumps({"name":os.environ["ALIAS"],"variables":"ansible_host: "+os.environ["HOST"]}))' \
    | postj "inventories/${INV_ID}/hosts/" >/dev/null
  echo "    - ${alias} -> ansible_host=${host} (created)"
done <<< "$(printf '%s\n' "$AWX_HOSTS")"

echo "==> Launching ad-hoc 'ping' against inventory ${INV_ID}…"
ADHOC_PAYLOAD="$(INV="$INV_ID" CRED="$CRED_ID" python3 -c 'import os,json;print(json.dumps({"module_name":"ping","module_args":"","inventory":int(os.environ["INV"]),"credential":int(os.environ["CRED"]),"verbosity":0}))')"
CMD_ID="$(printf '%s' "$ADHOC_PAYLOAD" | postj "ad_hoc_commands/" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("id") or sys.exit("LAUNCH FAILED: "+json.dumps(d)))')"
echo "    ad_hoc_command id=${CMD_ID}  (UI: ${AWX_API_URL}/#/jobs/command/${CMD_ID}/output)"

echo "==> Polling for completion…"
for _ in $(seq 1 60); do
  ST="$(getj "ad_hoc_commands/${CMD_ID}/" | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')"
  case "$ST" in
    successful|failed|error|canceled) break ;;
  esac
  sleep 3
done
echo "    final status: ${ST}"
echo "==> Output:"
getj "ad_hoc_commands/${CMD_ID}/stdout/?format=txt" | sed 's/^/    /'

echo
if [ "$ST" = "successful" ]; then
  echo "GATE GREEN ✅  ansible ping succeeded against all hosts. Tell Claude."
else
  echo "GATE NOT GREEN (${ST}) ⚠️  — paste the output above for Claude."
fi
