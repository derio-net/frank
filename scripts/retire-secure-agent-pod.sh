#!/usr/bin/env bash
# Archive, verify and key-check helper for retiring the secure-agent-pod.
#
# Operator-run, on the Mac. Read-only against the cluster: it never deletes,
# patches, restarts or applies anything. Spec:
# docs/superpowers/specs/2026-11-08--agents--retire-vk-design.md (R9).
#
#   archive          stream the files worth keeping off the pod into $DEST
#   verify           check what archive wrote (checksums, tarball, bundles, mode)
#   key-fingerprint  compare the GitHub App key across the live Secret and SOPS files
#
# Env: KUBECTL (default kubectl), SOPS (default sops), POD_HOME (default
# /home/claude; tests point it at a fixture directory).
set -euo pipefail

KUBECTL=${KUBECTL:-kubectl}
SOPS=${SOPS:-sops}
POD_HOME=${POD_HOME:-/home/claude}
DEST_DEFAULT="$HOME/Archives/secure-agent-pod-2026-11"
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)

usage() {
  cat >&2 <<USAGE
usage: $(basename "$0") <archive|verify|key-fingerprint> [--dest DIR] [--session-ended-confirmed]
  archive          copy the files worth keeping off the pod into DEST (default $DEST_DEFAULT)
  verify           verify the archive in DEST
  key-fingerprint  compare the GitHub App key fingerprints (never prints key material)
USAGE
  exit 2
}

die() { echo "error: $*" >&2; exit 1; }

# kubectl exec into the pod's kali container, argv passed through as-is.
rexec() {
  "$KUBECTL" -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- "$@"
}

mode_of() {
  stat -c %a "$1" 2>/dev/null || stat -f %Lp "$1"
}

# Nearest existing ancestor of a path (the path itself when it exists).
existing_ancestor() {
  local p=$1
  while [ ! -e "$p" ]; do p=$(dirname "$p"); done
  [ -d "$p" ] || p=$(dirname "$p")
  echo "$p"
}

check_dest() {
  local anchor
  anchor=$(existing_ancestor "$DEST")
  if git -C "$anchor" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "destination $DEST is inside a git work tree; the archive may hold tokens"
  fi
  if [ -e "$DEST" ]; then
    [ -d "$DEST" ] || die "destination $DEST exists and is not a directory"
    [ "$(mode_of "$DEST")" = "700" ] || die "destination $DEST has mode $(mode_of "$DEST"), need 700"
  fi
}

cmd_archive() {
  check_dest

  # Refuse while an interactive session is alive. `claude remote-control` is the
  # always-on bridge and does not count.
  local procs
  procs=$(rexec ps -eo args=) || die "could not list the pod's processes"
  if [ "$CONFIRMED" != 1 ]; then
    if printf '%s\n' "$procs" | grep -E '(^|/)claude( |$)' | grep -vq 'claude remote-control' \
       || printf '%s\n' "$procs" | grep -Eq '(^|/)herdr( |$)'; then
      die "interactive session still running (claude or herdr); end it, or pass --session-ended-confirmed"
    fi
  fi

  # shellcheck disable=SC2174  # only the leaf matters; its mode is asserted next
  mkdir -p -m 700 "$DEST"
  [ "$(mode_of "$DEST")" = "700" ] || die "destination $DEST is not mode 700"
  mkdir -p "$DEST/bundles"

  echo "archiving home tree from $POD_HOME ..."
  rexec tar -C "$POD_HOME" -czf - \
    --exclude=credentials.json \
    --exclude=server_ed25519_signing_key \
    --exclude=.ssh \
    --exclude=.gnupg \
    --exclude=.config/gh \
    --exclude=.claude.json \
    --exclude=node_modules \
    interviews orgs .hermes .willikins-agent/audit-archive \
    .local/share/vibe-kanban/db.v2.sqlite \
    repos/willikins/scripts/chorebot/config.yaml \
    > "$DEST/secure-agent-pod-home.tar.gz.part"
  mv "$DEST/secure-agent-pod-home.tar.gz.part" "$DEST/secure-agent-pod-home.tar.gz"

  # One bundle per clone, covering only commits no remote has.
  : > "$DEST/bundles/NONE.txt"
  local gitdir repo branch local_only name count
  rexec find "$POD_HOME" -maxdepth 6 -name .git -not -path '*/.cache/*' -not -path '*/node_modules/*' \
    | sort > "$DEST/.clones.txt"
  while IFS= read -r gitdir; do
    [ -n "$gitdir" ] || continue
    repo=$(dirname "$gitdir")
    local_only=""
    while IFS= read -r branch; do
      [ -n "$branch" ] || continue
      count=$(rexec git -C "$repo" rev-list --count "$branch" --not --remotes 2>/dev/null || echo 0)
      if [ "${count:-0}" -gt 0 ]; then local_only="$local_only $branch"; fi
    done < <(rexec git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads 2>/dev/null || true)
    if [ -z "$local_only" ]; then
      echo "$repo" >> "$DEST/bundles/NONE.txt"
      continue
    fi
    name=$(printf '%s' "${repo#/}" | sed 's#/#__#g')
    # shellcheck disable=SC2086  # branch names carry no spaces
    rexec git -C "$repo" bundle create - $local_only --not --remotes > "$DEST/bundles/$name.bundle"
    echo "bundle $name: $(echo "$local_only" | wc -w | tr -d ' ') ref(s):$local_only"
  done < "$DEST/.clones.txt"
  rm -f "$DEST/.clones.txt"

  # shellcheck disable=SC2094  # find skips MANIFEST.sha256 itself
  (cd "$DEST" && find . -type f ! -name MANIFEST.sha256 | sort | sed 's#^\./##' \
     | while IFS= read -r f; do shasum -a 256 "$f"; done > MANIFEST.sha256)
  echo "tarball files: $(tar -tzf "$DEST/secure-agent-pod-home.tar.gz" | wc -l | tr -d ' ')"
  echo "archive written to $DEST; run: $(basename "$0") verify --dest $DEST"
}

cmd_verify() {
  local fail=0
  pass() { echo "PASS $1"; }
  fail() { echo "FAIL $1"; fail=1; }

  local tarball="$DEST/secure-agent-pod-home.tar.gz"
  if [ -d "$DEST" ] && [ "$(mode_of "$DEST")" = "700" ]; then pass "destination mode 700"; else fail "destination mode 700"; fi

  if [ -f "$tarball" ]; then pass "tarball present"; else fail "tarball present"; fi

  if [ -f "$DEST/MANIFEST.sha256" ] && (cd "$DEST" && shasum -a 256 -c MANIFEST.sha256 >/dev/null 2>&1); then
    pass "MANIFEST.sha256 matches"
  else
    fail "MANIFEST.sha256 matches"
  fi

  if [ -f "$tarball" ]; then
    local listing
    listing=$(tar -tzf "$tarball" 2>/dev/null || true)
    if printf '%s\n' "$listing" | grep -q 'repos/willikins/scripts/chorebot/config.yaml$'; then
      pass "tarball lists chorebot config.yaml"; else fail "tarball lists chorebot config.yaml"; fi
    if printf '%s\n' "$listing" | grep -q '^\(\./\)\{0,1\}interviews/'; then pass "tarball has interviews/"; else fail "tarball has interviews/"; fi
    if printf '%s\n' "$listing" | grep -q '^\(\./\)\{0,1\}orgs/'; then pass "tarball has orgs/"; else fail "tarball has orgs/"; fi
  else
    fail "tarball lists chorebot config.yaml"
  fi

  local scratch b
  scratch=$(mktemp -d)
  git init -q "$scratch"
  for b in "$DEST"/bundles/*.bundle; do
    [ -e "$b" ] || continue
    if git -C "$scratch" bundle verify "$b" >/dev/null 2>&1; then
      pass "bundle verifies: $(basename "$b")"
    elif git -C "$scratch" bundle list-heads "$b" >/dev/null 2>&1; then
      pass "bundle readable (prerequisites absent in scratch repo, checked with list-heads): $(basename "$b")"
    else
      fail "bundle verifies: $(basename "$b")"
    fi
  done
  rm -rf "$scratch"

  [ "$fail" = 0 ] || exit 1
}

# SHA-256 of a base64 value, from stdin; never prints the value.
fp() { base64 -d | shasum -a 256 | cut -d' ' -f1; }

sops_key_fp() {
  local file=$1 keyname=$2
  "$SOPS" -d "$file" | awk -v k="$keyname" '
    /^data:/ {d=1; next}
    d && $1 == k":" {print $2; exit}
    d && /^[^ ]/ {exit}' | fp
}

cmd_key_fingerprint() {
  local tekton="$REPO_ROOT/secrets/github-app/github-app-derio-key-tekton.yaml"
  local old="$REPO_ROOT/secrets/github-app/github-app-derio-key.yaml"
  [ -f "$tekton" ] || die "$tekton not found"
  # The data key name sits unencrypted under `data:` in the SOPS file.
  local keyname
  keyname=$(awk '/^data:/ {d=1; next} d && /^ +[A-Za-z0-9_.-]+:/ {sub(/^ +/, ""); sub(/:.*/, ""); print; exit}' "$tekton")
  [ -n "$keyname" ] || die "could not read the data key name from $tekton"

  local live tek oldfp=""
  live=$("$KUBECTL" -n tekton-pipelines get secret github-app-derio-key -o "jsonpath={.data.$keyname}" | fp)
  tek=$(sops_key_fp "$tekton" "$keyname")
  echo "live Secret tekton-pipelines/github-app-derio-key : $live"
  echo "$(basename "$tekton")                  : $tek"
  local bad=0
  [ "$live" = "$tek" ] || bad=1
  if [ -f "$old" ]; then
    oldfp=$(sops_key_fp "$old" "$keyname")
    echo "$(basename "$old")                       : $oldfp"
    [ "$live" = "$oldfp" ] || bad=1
  else
    echo "github-app-derio-key.yaml is gone; comparing the Tekton copy only"
  fi
  if [ "$bad" = 0 ]; then echo "PASS fingerprints equal"; else echo "FAIL fingerprints differ"; exit 1; fi
}

[ $# -ge 1 ] || usage
SUB=$1; shift
DEST=$DEST_DEFAULT
CONFIRMED=0
while [ $# -gt 0 ]; do
  case $1 in
    --dest) [ $# -ge 2 ] || usage; DEST=$2; shift 2 ;;
    --session-ended-confirmed) CONFIRMED=1; shift ;;
    *) usage ;;
  esac
done

case $SUB in
  archive) cmd_archive ;;
  verify) cmd_verify ;;
  key-fingerprint) cmd_key_fingerprint ;;
  *) usage ;;
esac
