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
# Env: KUBECTL (default kubectl), SOPS (default sops), GIT (default git), POD_HOME (default
# /home/claude; tests point it at a fixture directory).
set -euo pipefail

KUBECTL=${KUBECTL:-kubectl}
SOPS=${SOPS:-sops}
GIT=${GIT:-git}
POD_HOME=${POD_HOME:-/home/claude}
DEST_DEFAULT="$HOME/Archives/secure-agent-pod-2026-11"
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)

usage() {
  cat >&2 <<USAGE
usage: $(basename "$0") <archive|verify|key-fingerprint> [--dest DIR] [--session-ended-confirmed] [--old-file-gone-ok]
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

# Credential-bearing names that must never be archived. One list feeds both the
# tar --exclude flags and verify's check of the tarball members.
CRED_NAMES=".credentials.json credentials.json server_ed25519_signing_key .claude.json .env auth.json *.pem id_rsa* id_ed25519* .ssh .gnupg .config/gh"

# Paths archived from the pod home. Missing ones are reported in SKIPPED.txt.
ESSENTIAL_PATHS="interviews orgs repos/willikins/scripts/chorebot/config.yaml"
ARCHIVE_PATHS="interviews orgs .hermes .willikins-agent/audit-archive .local/share/vibe-kanban/db.v2.sqlite repos/willikins/scripts/chorebot/config.yaml"
OPTIONAL_PATHS=".local/share/vibe-kanban/db.v2.sqlite-wal .local/share/vibe-kanban/db.v2.sqlite-shm"

# Runs on the pod: executes "$@", forwards its stdout, and reports on stderr the
# command's exit status and the SHA-256 of exactly the bytes it sent. The digest
# goes through a FIFO in a throwaway /tmp dir (removed on exit); the PVC home is
# never written.
read -r -d '' PODSTREAM <<'POD' || true
d=$(mktemp -d) || exit 97
trap 'rm -rf "$d"' EXIT
mkfifo "$d/f"
sha256sum < "$d/f" > "$d/sum" &
sp=$!
{ "$@"; echo "REMOTE-RC $?" >&2; } | tee "$d/f"
wait "$sp"
echo "REMOTE-SHA256 $(cut -d' ' -f1 "$d/sum")" >&2
POD

# stream_to OUTFILE CMD...: run CMD on the pod, store stdout in OUTFILE, and
# require that the pod-side digest equals the digest of what arrived. Sets
# STREAM_RC to the command's exit status and appends to $DEST/REMOTE.sha256.
stream_to() {
  local out=$1; shift
  local errf; errf=$(mktemp)
  rexec bash -c "$PODSTREAM" _ "$@" > "$out" 2> "$errf" || true
  local rc rsha lsha
  rc=$(sed -n 's/^REMOTE-RC //p' "$errf" | tail -1)
  rsha=$(sed -n 's/^REMOTE-SHA256 //p' "$errf" | tail -1)
  grep -v -e '^REMOTE-RC ' -e '^REMOTE-SHA256 ' "$errf" >&2 || true
  rm -f "$errf"
  [ -n "$rc" ] && [ -n "$rsha" ] || die "stream for $(basename "$out") ended without the pod's status line; the transfer was cut"
  lsha=$(shasum -a 256 "$out" | cut -d' ' -f1)
  [ "$rsha" = "$lsha" ] || die "stream for $(basename "$out") is damaged: pod sent $rsha, received $lsha"
  STREAM_RC=$rc
  echo "$rsha  ${out#"$DEST"/}" >> "$DEST/REMOTE.sha256"
}

# Succeeds when the session listing (stdin-free: passed as $1) shows a live
# interactive session. awk reads a here-string, so a huge listing cannot cause a
# SIGPIPE false negative the way `printf | grep -q` does under pipefail.
session_running() {
  awk '
    /remote-control/ { next }
    /(^|[ \/])claude( |$)/ { found=1; exit }
    /claude-code/ || /claude\/versions/ { found=1; exit }
    /(^|[ \/])herdr( |$)/ || /herdr/ { found=1; exit }
    /(^|[ \/])tmux( |:|$)/ { found=1; exit }
    END { exit found ? 0 : 1 }' <<<"$1"
}

rgit() { rexec git -c core.hooksPath=/dev/null "$@"; }

cmd_archive() {
  check_dest

  local procs
  procs=$(rexec ps -eo args=) || die "could not list the pod's processes"
  if [ "$CONFIRMED" != 1 ] && session_running "$procs"; then
    die "interactive session still running (claude, herdr or tmux); end it, or pass --session-ended-confirmed"
  fi

  # shellcheck disable=SC2174  # only the leaf matters; its mode is asserted next
  mkdir -p -m 700 "$DEST"
  [ "$(mode_of "$DEST")" = "700" ] || die "destination $DEST is not mode 700"
  mkdir -p "$DEST/bundles"
  # A re-run starts clean: nothing stale may enter the manifest.
  rm -f "$DEST"/bundles/* "$DEST/REMOTE.sha256" "$DEST/SKIPPED.txt" "$DEST/DETACHED.txt" \
        "$DEST/MANIFEST.sha256" "$DEST/secure-agent-pod-home.tar.gz"
  : > "$DEST/REMOTE.sha256"; : > "$DEST/SKIPPED.txt"; : > "$DEST/DETACHED.txt"

  # Which paths exist on the pod (read-only probe).
  local p have present=""
  for p in $ARCHIVE_PATHS $OPTIONAL_PATHS; do
    # shellcheck disable=SC2016  # the script runs on the pod; $1 is its own argument
    have=$(rexec sh -c 'if [ -e "$1" ]; then echo yes; else echo no; fi' _ "$POD_HOME/$p") \
      || die "could not probe $p on the pod"
    case $have in
      yes) present="$present $p" ;;
      no) case " $OPTIONAL_PATHS " in *" $p "*) ;; *) echo "$p" >> "$DEST/SKIPPED.txt"; echo "WARNING: $p not found on the pod, skipped" >&2 ;; esac ;;
      *) die "unexpected probe answer for $p" ;;
    esac
  done

  local excludes=() n tarflags=()
  set -f
  for n in $CRED_NAMES; do excludes+=("--exclude=$n"); done
  set +f
  excludes+=("--exclude=node_modules")
  # GNU tar exits 1 on "file changed as we read it"; tolerate that (not exit >= 2).
  local tv; tv=$(rexec tar --version 2>/dev/null || true)
  case $tv in *"GNU tar"*) tarflags+=("--warning=no-file-changed") ;; esac

  echo "archiving home tree from $POD_HOME ..."
  # shellcheck disable=SC2086  # $present is a space-separated list of simple paths
  stream_to "$DEST/secure-agent-pod-home.tar.gz" tar -C "$POD_HOME" -czf - ${tarflags[@]+"${tarflags[@]}"} "${excludes[@]}" $present
  case $STREAM_RC in
    0) ;;
    1) echo "WARNING: tar reported files changing while it read them (exit 1); archive kept" >&2 ;;
    *) die "tar failed on the pod with exit $STREAM_RC" ;;
  esac
  gzip -t "$DEST/secure-agent-pod-home.tar.gz" || die "tarball fails gzip -t"
  tar -tzf "$DEST/secure-agent-pod-home.tar.gz" >/dev/null || die "tarball cannot be listed"

  # One bundle per clone: local-only branches, tags and stash. No remote has these.
  : > "$DEST/bundles/NONE.txt"
  local clones gitdir repo ref refs count name wt wsha wdet
  clones=$(rexec find "$POD_HOME" -maxdepth 6 -type d -name .git -not -path '*/.cache/*' -not -path '*/node_modules/*') \
    || die "could not search the pod for git clones"
  while IFS= read -r gitdir; do
    [ -n "$gitdir" ] || continue
    repo=$(dirname "$gitdir")
    refs=""
    local all
    all=$(rgit -C "$repo" for-each-ref --format='%(refname)' refs/heads refs/tags refs/stash) \
      || die "git for-each-ref failed in $repo"
    while IFS= read -r ref; do
      [ -n "$ref" ] || continue
      count=$(rgit -C "$repo" rev-list --count "$ref" --not --remotes) || die "git rev-list failed for $ref in $repo"
      if [ "$count" -gt 0 ]; then refs="$refs $ref"; fi
    done <<<"$all"
    # The clone's own detached HEAD can be named in a bundle.
    if ! rgit -C "$repo" symbolic-ref -q HEAD >/dev/null 2>&1; then
      count=$(rgit -C "$repo" rev-list --count HEAD --not --remotes) || die "git rev-list failed for HEAD in $repo"
      if [ "$count" -gt 0 ]; then refs="$refs HEAD"; fi
    fi
    # Detached worktrees cannot be named read-only: record their unreachable tips.
    local wl
    wl=$(rgit -C "$repo" worktree list --porcelain) || die "git worktree list failed in $repo"
    wt=""; wsha=""; wdet=0
    while IFS= read -r line; do
      case $line in
        "worktree "*) wt=${line#worktree }; wsha=""; wdet=0 ;;
        "HEAD "*) wsha=${line#HEAD } ;;
        detached) wdet=1 ;;
        "")
          if [ "$wdet" = 1 ] && [ -n "$wsha" ] && [ "$wt" != "$repo" ]; then
            # shellcheck disable=SC2086
            count=$(rgit -C "$repo" rev-list --count "$wsha" --not --remotes $refs) || die "git rev-list failed for worktree $wt"
            if [ "$count" -gt 0 ]; then
              echo "$wt $wsha" >> "$DEST/DETACHED.txt"
              echo "WARNING: detached worktree $wt at $wsha holds commits no remote or ref has; a read-only bundle cannot name it (listed in DETACHED.txt)" >&2
            fi
          fi
          wt=""; wsha=""; wdet=0 ;;
      esac
    done <<<"$wl"$'\n'
    if [ -z "$refs" ]; then
      echo "$repo" >> "$DEST/bundles/NONE.txt"
      continue
    fi
    name=$(printf '%s' "${repo#/}" | sed 's#/#__#g')
    # shellcheck disable=SC2086  # refs are full ref names without spaces
    stream_to "$DEST/bundles/$name.bundle" git -c core.hooksPath=/dev/null -C "$repo" bundle create - $refs --not --remotes
    [ "$STREAM_RC" = 0 ] || die "git bundle create failed in $repo (exit $STREAM_RC)"
    echo "bundle $name: $(echo "$refs" | wc -w | tr -d ' ') ref(s):$refs"
  done <<<"$clones"

  # shellcheck disable=SC2094  # find skips MANIFEST.sha256 itself
  (cd "$DEST" && find . -type f ! -name MANIFEST.sha256 | sort | sed 's#^\./##' \
     | while IFS= read -r f; do shasum -a 256 "$f"; done > MANIFEST.sha256)
  echo "tarball files: $(tar -tzf "$DEST/secure-agent-pod-home.tar.gz" | wc -l | tr -d ' ')"
  echo "archive written to $DEST; run: $(basename "$0") verify --dest $DEST"
}

# True when a tar member path carries a credential name.
cred_hit() {
  local path=$1 n
  set -f
  for n in $CRED_NAMES; do
    # shellcheck disable=SC2254  # $n is a glob on purpose
    case $path in $n|*/$n|$n/*|*/$n/*) set +f; return 0 ;; esac
  done
  set +f
  return 1
}

# Pack checksum of a bundle: the 20 bytes after the pack body are the SHA-1 of
# everything before them. A truncated or damaged bundle fails this, even when its
# prerequisites are absent here (which defeats `git bundle verify`).
bundle_pack_ok() {
  perl -MDigest::SHA=sha1 -e '
    local $/; open(my $fh, "<:raw", $ARGV[0]) or exit 1; my $d = <$fh>;
    my $i = index($d, "\n\nPACK"); exit 1 if $i < 0;
    my $pack = substr($d, $i + 2);
    exit 1 if length($pack) < 32;
    exit(sha1(substr($pack, 0, -20)) eq substr($pack, -20) ? 0 : 1);' "$1"
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

  # The pod-side digests were taken before the bytes left the pod; the local
  # manifest cannot see a stream that was cut in transit.
  if [ -s "$DEST/REMOTE.sha256" ] && (cd "$DEST" && shasum -a 256 -c REMOTE.sha256 >/dev/null 2>&1); then
    pass "pod-side digests match (REMOTE.sha256)"
  else
    fail "pod-side digests match (REMOTE.sha256)"
  fi

  if [ -f "$tarball" ]; then
    local listing
    if gzip -t "$tarball" 2>/dev/null && listing=$(tar -tzf "$tarball" 2>/dev/null); then
      pass "tarball passes gzip -t and lists cleanly"
    else
      fail "tarball passes gzip -t and lists cleanly"; listing=""
    fi
    if printf '%s\n' "$listing" | grep -q 'repos/willikins/scripts/chorebot/config.yaml$'; then
      pass "tarball lists chorebot config.yaml"; else fail "tarball lists chorebot config.yaml"; fi
    if printf '%s\n' "$listing" | grep -q '^\(\./\)\{0,1\}interviews/'; then pass "tarball has interviews/"; else fail "tarball has interviews/"; fi
    if printf '%s\n' "$listing" | grep -q '^\(\./\)\{0,1\}orgs/'; then pass "tarball has orgs/"; else fail "tarball has orgs/"; fi
    local m hit=""
    while IFS= read -r m; do
      [ -n "$m" ] || continue
      if cred_hit "${m%/}"; then hit="$hit $m"; fi
    done <<<"$listing"
    if [ -z "$hit" ]; then pass "no credential files in tarball"; else fail "no credential files in tarball:$hit"; fi
  else
    fail "tarball lists chorebot config.yaml"
  fi

  local essential_missing=""
  if [ -f "$DEST/SKIPPED.txt" ]; then
    local e
    for e in $ESSENTIAL_PATHS; do
      if grep -Fxq "$e" "$DEST/SKIPPED.txt"; then essential_missing="$essential_missing $e"; fi
    done
    if [ -z "$essential_missing" ]; then pass "essential paths archived"; else fail "essential paths archived (skipped:$essential_missing)"; fi
  else
    fail "essential paths archived (SKIPPED.txt missing)"
  fi
  if [ -s "$DEST/DETACHED.txt" ]; then
    echo "WARN detached worktree commits are not in the bundles; see DETACHED.txt:"; sed 's/^/     /' "$DEST/DETACHED.txt"
  fi

  local scratch b
  scratch=$(mktemp -d)
  git init -q "$scratch"
  for b in "$DEST"/bundles/*.bundle; do
    [ -e "$b" ] || continue
    if ! bundle_pack_ok "$b"; then
      fail "bundle pack checksum: $(basename "$b")"
    elif git -C "$scratch" bundle verify "$b" >/dev/null 2>&1; then
      pass "bundle verifies: $(basename "$b")"
    elif git -C "$scratch" bundle list-heads "$b" >/dev/null 2>&1; then
      pass "bundle pack intact, prerequisites absent in scratch repo (checked with list-heads): $(basename "$b")"
    else
      fail "bundle readable: $(basename "$b")"
    fi
  done
  rm -rf "$scratch"

  [ "$fail" = 0 ] || exit 1
}

# SHA-256 of a base64 value, from stdin; never prints the value. An empty value
# is an error: two empties would otherwise compare equal.
fp() {
  local v
  v=$(cat)
  [ -n "$v" ] || { echo "error: empty key value" >&2; return 1; }
  local n
  n=$(printf '%s' "$v" | base64 -d | wc -c | tr -d ' ')
  [ "$n" -gt 0 ] || { echo "error: key value decodes to nothing" >&2; return 1; }
  printf '%s' "$v" | base64 -d | shasum -a 256 | cut -d' ' -f1
}

# Extract the base64 value of data key $1 from decrypted YAML on stdin.
data_value() {
  awk -v k="$1" '
    /^data:/ {d=1; next}
    d && $1 == k":" {print $2; exit}
    d && /^[^ ]/ {exit}'
}

sops_key_fp() {
  local file=$1 keyname=$2
  "$SOPS" -d "$file" | data_value "$keyname" | fp
}

# Same, for a file read from origin/main (it is deleted in this work tree) and
# decrypted through a pipe: no plaintext and no copy of the file touches disk.
sops_key_fp_from_git() {
  local keyname=$1 enc
  enc=$("$GIT" -C "$REPO_ROOT" show origin/main:secrets/github-app/github-app-derio-key.yaml 2>/dev/null) || return 2
  [ -n "$enc" ] || return 2
  printf '%s\n' "$enc" | "$SOPS" -d --input-type yaml --output-type yaml /dev/stdin | data_value "$keyname" | fp
}

cmd_key_fingerprint() {
  local tekton="$REPO_ROOT/secrets/github-app/github-app-derio-key-tekton.yaml"
  local old="$REPO_ROOT/secrets/github-app/github-app-derio-key.yaml"
  [ -f "$tekton" ] || die "$tekton not found"
  # The data key name sits unencrypted under `data:` in the SOPS file.
  local keyname
  keyname=$(awk '/^data:/ {d=1; next} d && /^ +[A-Za-z0-9_.-]+:/ {sub(/^ +/, ""); sub(/:.*/, ""); print; exit}' "$tekton")
  [ -n "$keyname" ] || die "could not read the data key name from $tekton"

  local live tek oldfp="" bad=0 rc
  live=$("$KUBECTL" -n tekton-pipelines get secret github-app-derio-key -o "jsonpath={.data.$keyname}" | fp) || die "live Secret value unusable"
  tek=$(sops_key_fp "$tekton" "$keyname") || die "Tekton SOPS copy value unusable"
  echo "live Secret tekton-pipelines/github-app-derio-key : $live"
  echo "$(basename "$tekton")                  : $tek"
  [ "$live" = "$tek" ] || bad=1
  if [ -f "$old" ]; then
    oldfp=$(sops_key_fp "$old" "$keyname") || die "$(basename "$old") value unusable"
    echo "$(basename "$old")                       : $oldfp"
  else
    rc=0
    oldfp=$(sops_key_fp_from_git "$keyname") || rc=$?
    if [ "$rc" = 0 ]; then
      echo "github-app-derio-key.yaml (origin/main)  : $oldfp"
    elif [ "$OLD_GONE_OK" = 1 ]; then
      echo "github-app-derio-key.yaml is in neither the work tree nor origin/main; --old-file-gone-ok given, comparing the Tekton copy only"
      oldfp=""
    else
      die "github-app-derio-key.yaml is in neither the work tree nor origin/main (or could not be read); pass --old-file-gone-ok to compare the Tekton copy only"
    fi
  fi
  if [ -n "$oldfp" ] && [ "$live" != "$oldfp" ]; then bad=1; fi
  if [ "$bad" = 0 ]; then echo "PASS fingerprints equal"; else echo "FAIL fingerprints differ"; exit 1; fi
}

[ $# -ge 1 ] || usage
SUB=$1; shift
DEST=$DEST_DEFAULT
CONFIRMED=0
OLD_GONE_OK=0
while [ $# -gt 0 ]; do
  case $1 in
    --dest) [ $# -ge 2 ] || usage; DEST=$2; shift 2 ;;
    --session-ended-confirmed) CONFIRMED=1; shift ;;
    --old-file-gone-ok) OLD_GONE_OK=1; shift ;;
    *) usage ;;
  esac
done

case $SUB in
  archive) cmd_archive ;;
  verify) cmd_verify ;;
  key-fingerprint) cmd_key_fingerprint ;;
  *) usage ;;
esac
