#!/usr/bin/env bash
# Private-exposure check (speech service Test Plan step 6, #1006):
# speech.cluster.derio.net answers on the LAN/mesh and does NOT resolve or route
# from the public edge. Read-only. Prints a colon-free gate answer.
#
# Why each check is shaped the way it is:
# - *.cluster.derio.net is a homelab wildcard to Traefik (192.168.55.220), so
#   "the name resolves" proves nothing. The positive check asks the route for
#   /v1/models and requires speaches' own model list in the body, and a negative
#   control (an impossible name) shows the resolver is not just echoing.
# - Public DNS is asked directly (1.1.1.1, 8.8.8.8), falling back to
#   DNS-over-HTTPS because plain public DNS is blocked on the homelab LAN.
#   The name must be NXDOMAIN.
# - The public edge (Hop's Caddy, HOP_IP from the repo's .env_hop) is asked with
#   the speech Host forced onto its address: it must not return speaches.
# The mesh resolver (100.100.100.100) is skipped when this host is not on the
# tailnet; run it from a mesh-joined device to cover that half.
# Usage: bash scripts/speech/speech-exposure-check.sh
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
# Gitignored operator files (.env_hop, .talos/) live only in the MAIN checkout,
# not in an fr worktree: look in this checkout first, then the main one.
MAIN=$(dirname "$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$REPO/.git")")
repo_file() { if [ -e "$REPO/$1" ]; then echo "$REPO/$1"; else echo "$MAIN/$1"; fi; }
NAME=speech.cluster.derio.net
ENV_HOP=${ENV_HOP:-$(repo_file .env_hop)}
command -v dig >/dev/null && command -v curl >/dev/null && command -v python3 >/dev/null || { echo "need dig, curl, python3" >&2; exit 2; }
FAIL=0
R=()
note() { echo "  $1"; R+=("$1"); }
bad() { echo "  FAIL $1"; R+=("FAIL $1"); FAIL=1; }

status_of() { dig +time=3 +tries=1 "@$1" "$2" A 2>/dev/null | awk '/status:/{gsub(",","",$6); print $6; exit}'; }
answer_of() { dig +short +time=3 +tries=1 "@$1" "$2" A 2>/dev/null | tr '\n' ' ' | sed 's/ $//'; }

echo "== LAN and mesh resolvers"
for r in 192.168.10.11 192.168.10.12 100.100.100.100; do
  s=$(status_of $r $NAME || true)
  if [ -z "$s" ]; then note "resolver $r unreachable from here (skipped)"; continue; fi
  ctl=$(status_of $r "nope-$RANDOM.cluster.derio.net" || true)
  note "resolver $r - $NAME $s $(answer_of $r $NAME); negative control nope-x.cluster.derio.net $ctl (wildcard if NOERROR)"
done

echo "== Positive - the route serves speaches (body checked, not just the status)"
body=$(curl -sS --max-time 15 -w '\n__HTTP__%{http_code}' "https://$NAME/v1/models" || true)
code=${body##*__HTTP__}
if [ "$code" = 200 ] && printf '%s' "$body" | grep -q 'faster-whisper'; then
  note "https://$NAME/v1/models HTTP 200 with speaches model list (whisper, kokoro, piper) from this host"
else
  bad "https://$NAME/v1/models returned HTTP $code without speaches' model list"
fi

echo "== Negative - public DNS"
doh() {  # doh <url> -> "NXDOMAIN" | "NOERROR <answers>" | ""
  curl -sS --max-time 10 -H 'accept: application/dns-json' "$1?name=$NAME&type=A" 2>/dev/null | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
s={0:'NOERROR',2:'SERVFAIL',3:'NXDOMAIN'}.get(d.get('Status'),str(d.get('Status')))
print(s, ' '.join(a.get('data','') for a in d.get('Answer') or []))"
}
for r in 1.1.1.1 8.8.8.8; do
  s=$(status_of $r $NAME || true)
  if [ -n "$s" ]; then
    a=$(answer_of $r $NAME || true)
    if [ "$s" = NXDOMAIN ]; then note "public resolver $r - $NAME NXDOMAIN"; else bad "public resolver $r - $NAME $s $a (should be NXDOMAIN)"; fi
    continue
  fi
  url=https://cloudflare-dns.com/dns-query; [ $r = 8.8.8.8 ] && url=https://dns.google/resolve
  res=$(doh $url)
  case "$res" in
    NXDOMAIN*) note "public DNS $r over HTTPS (plain DNS is blocked here) - $NAME NXDOMAIN" ;;
    "") bad "public DNS $r unreachable over UDP and HTTPS, cannot prove absence" ;;
    *) bad "public DNS $r over HTTPS - $NAME $res (should be NXDOMAIN)" ;;
  esac
done

echo "== Negative - the public edge does not route it"
HOP_IP=$(grep -E '^(export )?HOP_IP=' "$ENV_HOP" 2>/dev/null | head -1 | sed -E 's/^(export )?HOP_IP=//; s/["'"'"']//g')
if [ -z "$HOP_IP" ]; then
  bad "HOP_IP not found in $ENV_HOP"
else
  for scheme in https http; do
    port=443; [ $scheme = http ] && port=80
    r=$(curl -sS --max-time 10 -k --resolve "$NAME:$port:$HOP_IP" -o "${TMPDIR:-/tmp}/speech-edge.$$" -w '%{http_code}' "$scheme://$NAME/v1/models" 2>&1 || true)
    if grep -q 'faster-whisper' "${TMPDIR:-/tmp}/speech-edge.$$" 2>/dev/null; then
      bad "public edge ($scheme, Host $NAME) RETURNED speaches"
    else
      what=$(printf '%s' "$r" | head -c 200)
      case "$what" in
        *SSL*|*"(35)"*) what="TLS handshake refused, the edge holds no certificate for the name" ;;
        308|301|302) what="HTTP $what redirect to https only" ;;
        *) what="HTTP $what" ;;
      esac
      note "public edge ($scheme, Host $NAME forced onto the Hop IP) - no speaches response ($what)"
    fi
    rm -f "${TMPDIR:-/tmp}/speech-edge.$$"
  done
fi

echo
[ $FAIL = 0 ] && echo "RESULT PASS" || echo "RESULT FAIL"
python3 - "$FAIL" "$(date -u +%F)" "${R[@]}" <<'PY'
import sys
fail, day, rows = sys.argv[1] == "1", sys.argv[2], sys.argv[3:]
verb = "owed" if fail else "ran"
line = f"{verb} speech-exposure-check.sh on {day} - " + "; ".join(rows)
print("\nSuggested gate answer (one line, colon-free) -")
print(line.replace("https://", "").replace("http://", "").replace(":", "-"))
PY
[ $FAIL = 0 ]
