#!/usr/bin/env bash
# Formalize the AWX smoke test: create a Gitea repo with ping.yml, an AWX
# Project pointing at it, and a smoke-ping Job Template, then launch it.
# Idempotent. Runs on your Mac. No secrets printed.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
ENV_FILE="${1:-$REPO/scripts/tmp/awx-hosts.env}"
# shellcheck disable=SC1090
source "$ENV_FILE"

# ---- creds (read live) ------------------------------------------------------
GITEA_USER="$(kubectl -n gitea get secret gitea-secrets -o jsonpath='{.data.username}' | base64 -d)"
GITEA_PASS="$(kubectl -n gitea get secret gitea-secrets -o jsonpath='{.data.password}' | base64 -d)"
ADMIN_PW="$(kubectl -n awx get secret awx-admin-password -o jsonpath='{.data.password}' | base64 -d)"
GITEA_API="https://gitea.cluster.derio.net/api/v1"
BASE="${AWX_API_URL%/}/api/v2"
REPO="${AWX_PROJECT_NAME:-frank-ansible-playbooks}"
SCM_URL="http://gitea-http.gitea.svc.cluster.local:3000/${GITEA_USER}/${REPO}.git"

# TLS verification ON: awx.cluster.derio.net + gitea.cluster.derio.net carry valid
# Let's Encrypt certs. SCM_URL stays in-cluster http (pod->pod), authenticated by
# the Source Control credential created below — the repo is private.
g()    { curl -s -u "${GITEA_USER}:${GITEA_PASS}" "$@"; }
api()  { curl -s -u "admin:${ADMIN_PW}" "$@"; }
getj() { api "$BASE/$1"; }
postj(){ api -H 'Content-Type: application/json' -X POST "$BASE/$1" --data-binary @-; }

# ---- 1. Gitea repo ----------------------------------------------------------
echo "==> Gitea repo: ${GITEA_USER}/${REPO}"
if g "${GITEA_API}/repos/${GITEA_USER}/${REPO}" | grep -q '"id"'; then
  echo "    exists"
else
  printf '{"name":"%s","private":true,"auto_init":true,"default_branch":"main"}' "$REPO" \
    | g -H 'Content-Type: application/json' -X POST "${GITEA_API}/user/repos" --data-binary @- >/dev/null
  echo "    created"
fi

# ---- 2. ping.yml in the repo ------------------------------------------------
echo "==> ${REPO}/ping.yml"
if g "${GITEA_API}/repos/${GITEA_USER}/${REPO}/contents/ping.yml" | grep -q '"sha"'; then
  echo "    exists"
else
  PING_B64="$(python3 -c 'import base64;print(base64.b64encode(open("/dev/stdin","rb").read()).decode())' <<'YAML'
---
- name: Smoke test — ping all hosts
  hosts: all
  gather_facts: false
  tasks:
    - name: ansible.builtin.ping
      ansible.builtin.ping:
YAML
)"
  CONTENT="$PING_B64" python3 -c 'import os,json;print(json.dumps({"content":os.environ["CONTENT"],"message":"add ping smoke playbook","branch":"main"}))' \
    | g -H 'Content-Type: application/json' -X POST "${GITEA_API}/repos/${GITEA_USER}/${REPO}/contents/ping.yml" --data-binary @- >/dev/null
  echo "    created"
fi

# ---- 3. AWX ids (org/inventory/credential already exist) --------------------
ORG_ID="$(getj "organizations/?name=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$AWX_ORG")" | python3 -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["id"])')"
INV_ID="$(getj "inventories/?name=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$AWX_INVENTORY")" | python3 -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["id"])')"
CRED_ID="$(getj "credentials/?name=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$AWX_CREDENTIAL")" | python3 -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["id"])')"
echo "==> AWX org=${ORG_ID} inventory=${INV_ID} credential=${CRED_ID}"

# ---- 4. AWX Source Control credential (auth for the private repo clone) ------
echo "==> AWX Source Control credential: frank-gitea-scm"
SC_TYPE="$(getj "credential_types/?name=Source%20Control" | python3 -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["id"])')"
SCM_CRED_ID="$(getj "credentials/?name=frank-gitea-scm" | python3 -c 'import sys,json;r=json.load(sys.stdin)["results"];print(r[0]["id"] if r else "")')"
if [ -z "$SCM_CRED_ID" ]; then
  SCM_CRED_ID="$(N=frank-gitea-scm CT="$SC_TYPE" OID="$ORG_ID" U="$GITEA_USER" P="$GITEA_PASS" python3 -c 'import os,json;print(json.dumps({"name":os.environ["N"],"credential_type":int(os.environ["CT"]),"organization":int(os.environ["OID"]),"inputs":{"username":os.environ["U"],"password":os.environ["P"]}}))' \
    | postj "credentials/" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("id") or sys.exit("SCM CRED FAILED: "+json.dumps(d)))')"
fi
echo "    scm credential id=${SCM_CRED_ID}"

# ---- 5. AWX Project (private repo, authenticated clone) ----------------------
echo "==> AWX Project: ${REPO}"
PROJ_ID="$(getj "projects/?name=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$REPO")" | python3 -c 'import sys,json;r=json.load(sys.stdin)["results"];print(r[0]["id"] if r else "")')"
if [ -z "$PROJ_ID" ]; then
  PROJ_ID="$(O="$ORG_ID" N="$REPO" U="$SCM_URL" C="$SCM_CRED_ID" python3 -c 'import os,json;print(json.dumps({"name":os.environ["N"],"organization":int(os.environ["O"]),"scm_type":"git","scm_url":os.environ["U"],"scm_branch":"main","scm_update_on_launch":True,"scm_clean":True,"credential":int(os.environ["C"])}))' \
    | postj "projects/" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("id") or sys.exit("PROJECT CREATE FAILED: "+json.dumps(d)))')"
  echo "    created id=${PROJ_ID}"
else
  echo "    exists id=${PROJ_ID}; ensuring SCM credential + triggering update…"
  printf '{"credential":%s}' "$SCM_CRED_ID" | api -H 'Content-Type: application/json' -X PATCH "$BASE/projects/${PROJ_ID}/" --data-binary @- >/dev/null || true
  api -X POST "$BASE/projects/${PROJ_ID}/update/" >/dev/null || true
fi

echo "==> waiting for project sync…"
for _ in $(seq 1 40); do
  PS="$(getj "projects/${PROJ_ID}/" | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')"
  case "$PS" in successful|failed|error|canceled) break;; esac
  sleep 3
done
echo "    project status: ${PS}"
[ "$PS" = "successful" ] || { echo "!! project did not sync — aborting before JT"; exit 1; }

# ---- 5. Job Template + attach credential ------------------------------------
echo "==> Job Template: ${AWX_JOB_TEMPLATE}"
JT_ID="$(getj "job_templates/?name=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$AWX_JOB_TEMPLATE")" | python3 -c 'import sys,json;r=json.load(sys.stdin)["results"];print(r[0]["id"] if r else "")')"
if [ -z "$JT_ID" ]; then
  JT_ID="$(N="$AWX_JOB_TEMPLATE" I="$INV_ID" P="$PROJ_ID" PB="$AWX_PLAYBOOK" python3 -c 'import os,json;print(json.dumps({"name":os.environ["N"],"job_type":"run","inventory":int(os.environ["I"]),"project":int(os.environ["P"]),"playbook":os.environ["PB"],"ask_credential_on_launch":False}))' \
    | postj "job_templates/" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("id") or sys.exit("JT CREATE FAILED: "+json.dumps(d)))')"
  echo "    created id=${JT_ID}"
else
  echo "    exists id=${JT_ID}"
fi
# attach the machine credential (idempotent; ignore if already linked)
printf '{"id":%s}' "$CRED_ID" | postj "job_templates/${JT_ID}/credentials/" >/dev/null 2>&1 || true

# ---- 6. Launch + poll -------------------------------------------------------
echo "==> launching Job Template ${JT_ID}…"
JOB_ID="$(printf '{}' | postj "job_templates/${JT_ID}/launch/" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("job") or d.get("id") or sys.exit("LAUNCH FAILED: "+json.dumps(d)))')"
echo "    job id=${JOB_ID}  (UI: ${AWX_API_URL}/#/jobs/playbook/${JOB_ID}/output)"
for _ in $(seq 1 80); do
  JS="$(getj "jobs/${JOB_ID}/" | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')"
  case "$JS" in successful|failed|error|canceled) break;; esac
  sleep 3
done
echo "    job status: ${JS}"
echo "==> output:"
getj "jobs/${JOB_ID}/stdout/?format=txt" | sed 's/^/    /'

echo
if [ "$JS" = "successful" ]; then
  echo "JOB TEMPLATE GREEN ✅  smoke-ping (job ${JOB_ID}) — tell Claude for the screenshot."
else
  echo "Job Template NOT green (${JS}) ⚠️  — paste output for Claude."
fi
