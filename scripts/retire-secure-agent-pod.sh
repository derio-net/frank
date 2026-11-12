#!/usr/bin/env bash
# Archive, verify and key-check helper for retiring the secure-agent-pod.
#
# Operator-run, on the Mac. Read-only against the cluster: it never deletes,
# patches, restarts or applies anything. Spec:
# docs/superpowers/specs/2026-11-08--agents--retire-vk-design.md (R9).
#
#   archive          stream the files worth keeping off the pod into $DEST: a home-tree
#                    tarball; git bundles of local-only commits (refs/ minus remote-tracking
#                    refs, plus the detached HEAD of every worktree); annotated tag objects
#                    whose commit a remote already has; and the UNCOMMITTED state of every
#                    clone and linked worktree (index and working-tree patches, untracked
#                    files, skip-worktree files, every stash entry) under worktrees/
#   verify           check what archive wrote (checksums, tarball, bundles, dirty state, mode);
#                    offline. `verify --live` also re-scans the pod, read-only, and diffs it
#   key-fingerprint  compare the GitHub App key across the live Secret and SOPS files
#
# Scope notes. Out of scope on purpose: ignored files (only listed, in ignored/), clones under
# .cache or node_modules (skipped, recorded in SKIPPED.txt), and reflog-only commits (commits
# reachable only through a reflog; deferred). A remote whose URL is a local path on the pod is
# not a remote: its tracking refs do not make a commit "already safe".
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
usage: $(basename "$0") <archive|verify|key-fingerprint> [--dest DIR] [--session-ended-confirmed] [--live] [--old-file-gone-ok]
  archive          copy the files worth keeping off the pod into DEST (default $DEST_DEFAULT):
                   home tarball, bundles of local-only commits (all non-remote refs, detached
                   worktree HEADs), and uncommitted clone state (index and working-tree
                   patches, untracked and skip-worktree files, every stash entry); read-only
                   on the pod. Not archived: ignored files (listed in ignored/), clones under
                   .cache or node_modules (recorded in SKIPPED.txt), reflog-only commits.
  verify           verify the archive in DEST, offline; --live also re-scans the pod
                   (read-only) and fails if its clones or dirty state changed since the archive
  key-fingerprint  compare the GitHub App key fingerprints (never prints key material)
USAGE
  exit 2
}

die() { echo "error: $*" >&2; exit 1; }

# kubectl exec into the pod's kali container, argv passed through as-is.
rexec() {
  "$KUBECTL" -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- "$@" </dev/null
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
# tar --exclude flags and verify's check of the tarball members. Key files are
# matched by their exact names (and .pub), so id_rsa_notes.md is kept.
CRED_NAMES=".credentials.json credentials.json server_ed25519_signing_key .claude.json .env auth.json *.pem id_rsa id_rsa.pub id_ed25519 id_ed25519.pub id_ecdsa id_ecdsa.pub id_dsa id_dsa.pub .ssh .gnupg .config/gh"

# Paths archived from the pod home. Missing ones are reported in SKIPPED.txt.
ESSENTIAL_PATHS="interviews orgs repos/willikins/scripts/chorebot/config.yaml"
ARCHIVE_PATHS="interviews orgs .hermes .willikins-agent/audit-archive .local/share/vibe-kanban/db.v2.sqlite repos/willikins/scripts/chorebot/config.yaml"
OPTIONAL_PATHS=".local/share/vibe-kanban/db.v2.sqlite-wal .local/share/vibe-kanban/db.v2.sqlite-shm"

EMPTY_TREE=4b825dc642cb6eb9a060e54bf8d69288fbee4904

# Runs on the pod: executes "$@", forwards its stdout, and reports on stderr the
# command's exit status and the SHA-256 of exactly the bytes it sent. The digest
# goes through a FIFO in a throwaway /tmp dir (removed on exit); the PVC home is
# never written. EVERY pod call goes through this, probes included, so a stream
# cut short with exit 0 is detected instead of being read as "nothing there".
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

SCRATCH=""
STREAM_RECORD=1
STREAM_ERR=""
STREAM_RC=0
LIVE_ONLY=0

# stream_to OUTFILE CMD...: run CMD on the pod, store stdout in OUTFILE, and
# require that the pod-side digest equals the digest of what arrived. Sets
# STREAM_RC (the command's exit status) and STREAM_ERR (its stderr). Records the
# digest in $DEST/REMOTE.sha256 when STREAM_RECORD=1.
stream_to() {
  local out=$1; shift
  local errf; errf=$(mktemp)
  mkdir -p "$(dirname "$out")"
  rexec bash -c "$PODSTREAM" _ "$@" > "$out" 2> "$errf" || true
  local rc rsha lsha
  rc=$(sed -n 's/^REMOTE-RC //p' "$errf" | tail -1)
  rsha=$(sed -n 's/^REMOTE-SHA256 //p' "$errf" | tail -1)
  STREAM_ERR=$(grep -v -e '^REMOTE-RC ' -e '^REMOTE-SHA256 ' "$errf" || true)
  rm -f "$errf"
  [ -n "$rc" ] && [ -n "$rsha" ] || die "stream for $(basename "$out") ended without the pod's status line; the transfer was cut"
  lsha=$(shasum -a 256 "$out" | cut -d' ' -f1)
  [ "$rsha" = "$lsha" ] || die "stream for $(basename "$out") is damaged: pod sent $rsha, received $lsha"
  STREAM_RC=$rc
  if [ "$STREAM_RECORD" = 1 ]; then echo "$rsha  ${out#"$DEST"/}" >> "$DEST/REMOTE.sha256"; fi
}

# cap OUTFILE CMD...: a digest-checked pod call whose result is only read here.
cap() { local out=$1; shift; STREAM_RECORD=0 stream_to "$out" "$@"; }

# adopt SCRATCHFILE DESTFILE: keep a digest-verified capture in the archive.
adopt() {
  mkdir -p "$(dirname "$2")"
  cp "$1" "$2"
  echo "$(shasum -a 256 "$2" | cut -d' ' -f1)  ${2#"$DEST"/}" >> "$DEST/REMOTE.sha256"
}

# Every git call on the pod: no index refresh, no hooks, no fsmonitor daemon, and a
# pinned diff dialect so a hostile ~/.gitconfig cannot change the patch format.
GITP=(env GIT_OPTIONAL_LOCKS=0 git -c core.hooksPath=/dev/null -c core.fsmonitor=false
      -c diff.relative=false -c diff.noprefix=false -c diff.mnemonicPrefix=false
      -c color.diff=never -c color.ui=never)
DIFFARGS=(--binary --no-ext-diff --no-textconv --no-color --src-prefix=a/ --dst-prefix=b/)

# gfile OUT REPO ARGS...: a git call, output to OUT; aborts unless it exits 0.
gfile() {
  local out=$1 repo=$2; shift 2
  cap "$out" "${GITP[@]}" -C "$repo" "$@"
  [ "$STREAM_RC" = 0 ] || die "git $1 failed in $repo (exit $STREAM_RC)"
}

# gprobe REPO ARGS...: like gfile but leaves the exit status in STREAM_RC.
gprobe() {
  local repo=$1; shift
  cap "$SCRATCH/probe" "${GITP[@]}" -C "$repo" "$@"
}

# Succeeds when the session listing ($1) shows a live interactive session. awk
# reads a here-string, so a huge listing cannot cause a SIGPIPE false negative the
# way `printf | grep -q` does under pipefail.
session_running() {
  awk '
    /remote-control/ { next }
    /(^|[ \/])claude( |$)/ { found=1; exit }
    /claude-code/ || /claude\/versions/ { found=1; exit }
    /herdr/ { found=1; exit }
    /(^|[ \/])tmux( |:|$)/ { found=1; exit }
    END { exit found ? 0 : 1 }' <<<"$1"
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

# True when the untracked-file capture drops the path (credential name or node_modules).
excluded_hit() {
  case $1 in node_modules|node_modules/*|*/node_modules|*/node_modules/*) return 0 ;; esac
  cred_hit "$1"
}

# Directory name for a worktree/repo path; the checksum suffix keeps a/b__c and a__b/c apart.
wtname() {
  printf '%s.%s' "$(printf '%s' "${1#/}" | sed 's#/#__#g')" "$(printf '%s' "$1" | cksum | cut -d' ' -f1)"
}
dirty_dir() { echo "$DEST/worktrees/$(wtname "$1")"; }

# --- small NUL-safe parsers (run locally; perl ships with macOS) ----------------
pl_status_counts() {   # status -z file -> "modified untracked"
  perl -0777 -e 'my $d=<STDIN>; my @t=split /\0/,$d; my($m,$u)=(0,0);
    while(@t){ my $e=shift @t; next if $e eq ""; my $x=substr($e,0,2);
      if($x eq "??"){$u++} elsif($x eq "!!"){} else {$m++; shift @t if $x=~/[RC]/;} }
    print "$m $u\n";' < "$1"
}
pl_hidden() {          # ls-files -v -z file -> NUL list of skip-worktree/assume-unchanged paths
  perl -0777 -e 'my $d=<STDIN>; for my $e (split /\0/,$d){ next unless $e=~/^([a-zS]) (.*)$/s; print "$2\0"; }' < "$1"
}
pl_lines() {           # NUL list -> one escaped line per path
  perl -0777 -e 'my $d=<STDIN>; for (split /\0/,$d){ next unless length; s/\\/\\\\/g; s/\n/\\n/g; print "$_\n"; }' < "$1"
}
pl_worktrees() {       # worktree list (porcelain, -z or plain) -> NUL tuples path,bare,prunable,detached,head
  perl -0777 -e '
    my $d=<STDIN>; my @recs;
    if ($d =~ /\0/) { my $cur=[]; for my $f (split /\0/, $d, -1) { if ($f eq "") { push @recs,$cur if @$cur; $cur=[]; } else { push @$cur,$f } } push @recs,$cur if @$cur }
    else { for my $blk (split /\n\n/, $d) { my @l = grep {length} split /\n/, $blk; push @recs,\@l if @l } }
    for my $r (@recs){ my ($p,$b,$pr,$dt,$h)=("",0,0,0,"");
      for (@$r){ if(/^worktree (.*)$/s){$p=$1} elsif(/^HEAD (\S+)/){$h=$1} elsif($_ eq "bare"){$b=1} elsif($_ eq "detached"){$dt=1} elsif(/^prunable/){$pr=1} }
      print join("\0",$p,$b,$pr,$dt,$h),"\0"; }' < "$1"
}
pl_remotes() {         # config -z remote urls -> S NUL name NUL (network) | L NUL name NUL url NUL (local path)
  perl -0777 -e 'my $d=<STDIN>; for my $e (split /\0/,$d){ next unless length $e; my($k,$v)=split /\n/,$e,2; next unless $k=~/^remote\.(.*)\.url$/s; my $n=$1;
    my $loc = ($v =~ m{^(?:file:|/|\.)}i); my $net = !$loc && ($v =~ m{^[A-Za-z][A-Za-z0-9+.-]*://} || $v =~ m{^[^/:]{2,}:});
    print $net ? "S\0$n\0" : "L\0$n\0$v\0"; }' < "$1"
}

# --- discovery ---------------------------------------------------------------
# note_skip TEXT: record something the archive does not capture.
note_skip() {
  if [ "$LIVE_ONLY" = 1 ]; then echo "$1" >> "$SCRATCH/live.skipped"; else echo "$1" >> "$DEST/SKIPPED.txt"; fi
}

# discover: fills $SCRATCH/clones.tsv with "repo<TAB>common-dir", one line per distinct
# repository (linked worktrees and submodules resolve to their own common dir).
discover() {
  local f=$SCRATCH/find.out p repo common seen="" line
  : > "$SCRATCH/clones.tsv"
  # Regenerable caches are pruned for speed, but recorded.
  cap "$f" find -H "$POD_HOME" \( -name .git -o -type d -name '*.git' \) -prune -o \
      -type d \( -name .cache -o -name node_modules \) -prune -print0
  case $STREAM_RC in 0|1) ;; *) die "find (caches) failed on the pod (exit $STREAM_RC)" ;; esac
  while IFS= read -r -d '' p; do note_skip "pruned (regenerable cache, not archived): $p"; done < "$f"
  if [ -n "$STREAM_ERR" ]; then while IFS= read -r line; do note_skip "unreadable: $line"; done <<<"$STREAM_ERR"; fi
  cap "$f" find -H "$POD_HOME" \( -type d \( -name .cache -o -name node_modules \) -prune \) -o \
      \( \( -name .git -o -type d -name '*.git' \) -prune -print0 \)
  case $STREAM_RC in 0|1) ;; *) die "find (repositories) failed on the pod (exit $STREAM_RC)" ;; esac
  if [ -n "$STREAM_ERR" ]; then while IFS= read -r line; do note_skip "unreadable: $line"; done <<<"$STREAM_ERR"; fi
  while IFS= read -r -d '' p; do
    case $p in */.git) repo=${p%/.git} ;; *) repo=$p ;; esac
    case $repo in *$'\n'*) die "repository path contains a newline: unsupported" ;; esac
    # shellcheck disable=SC2016  # the script runs on the pod
    cap "$SCRATCH/common" sh -c 'cd "$1" && cd "$(git rev-parse --git-common-dir)" && pwd -P' _ "$repo"
    if [ "$STREAM_RC" != 0 ]; then note_skip "not a usable git repository: $repo"; continue; fi
    common=$(cat "$SCRATCH/common")
    case $seen in *"|$common|"*) continue ;; esac
    seen="$seen|$common|"
    printf '%s\t%s\n' "$repo" "$common" >> "$SCRATCH/clones.tsv"
  done < "$f"
}

# --- per repository ----------------------------------------------------------
WT_PATH=(); WT_BARE=(); WT_PRUN=(); WT_DET=()
NOT=()          # rev-list exclusion: --not --remotes=<network remote> ...

load_worktrees() {   # REPO
  local repo=$1 t=$SCRATCH/wl i=0 a b c d _head
  cap "$t" "${GITP[@]}" -C "$repo" worktree list --porcelain -z
  [ "$STREAM_RC" = 0 ] || gfile "$t" "$repo" worktree list --porcelain
  pl_worktrees "$t" > "$t.tuples"
  WT_PATH=(); WT_BARE=(); WT_PRUN=(); WT_DET=()
  while IFS= read -r -d '' a && IFS= read -r -d '' b && IFS= read -r -d '' c && IFS= read -r -d '' d && IFS= read -r -d '' _head; do
    case $a in *$'\n'*) die "worktree path contains a newline: unsupported" ;; esac
    WT_PATH[i]=$a; WT_BARE[i]=$b; WT_PRUN[i]=$c; WT_DET[i]=$d; i=$((i + 1))
  done < "$t.tuples"
  [ "$i" -gt 0 ] || die "git worktree list returned nothing for $repo"
  # A submodule's first record is its gitdir (under the parent's .git/modules), not a
  # working tree; use the real top level of the repository we were pointed at.
  if [ "${WT_BARE[0]}" = 0 ]; then
    # shellcheck disable=SC2016  # the script runs on the pod
    cap "$SCRATCH/probe" sh -c 'test -e "$1/.git"' _ "${WT_PATH[0]}"
    if [ "$STREAM_RC" != 0 ]; then
      gfile "$SCRATCH/top" "$repo" rev-parse --show-toplevel
      WT_PATH[0]=$(cat "$SCRATCH/top")
    fi
  fi
}

# load_remotes REPO: NOT[] from the network remotes only; a remote whose URL is a
# local path on the pod is not a safe copy, so its tracking refs are ignored (warned).
load_remotes() {
  local repo=$1 t=$SCRATCH/cfg k n u
  NOT=()
  cap "$t" "${GITP[@]}" -C "$repo" config -z --get-regexp '^remote\..*\.url$'
  case $STREAM_RC in 0|1) ;; *) die "git config failed in $repo (exit $STREAM_RC)" ;; esac
  pl_remotes "$t" > "$t.tuples"
  while IFS= read -r -d '' k; do
    if [ "$k" = S ]; then
      IFS= read -r -d '' n
      if [ ${#NOT[@]} -eq 0 ]; then NOT=(--not); fi
      NOT+=("--remotes=$n")
    else
      IFS= read -r -d '' n; IFS= read -r -d '' u
      echo "WARNING: remote '$n' of $repo is a local path ($u); its tracking refs do not count as a remote copy" >&2
    fi
  done < "$t.tuples"
}

# bundle_refs REPO NAME: bundle every non-remote ref with commits no network remote has;
# keep annotated tag objects whose commit is already safe; list all refs in refs/NAME.txt.
bundle_refs() {
  local repo=$1 name=$2 t=$SCRATCH/refs.txt ref ty sha pty psha count
  local cands=() want=()
  gfile "$t" "$repo" for-each-ref --format='%(refname)	%(objecttype)	%(objectname)	%(*objecttype)	%(*objectname)' refs/
  : > "$SCRATCH/refs.own"
  while IFS=$'\t' read -r ref ty sha pty psha; do
    [ -n "$ref" ] || continue
    case $ref in refs/remotes/*) continue ;; esac
    printf '%s\t%s\t%s\t%s\t%s\n' "$ref" "$ty" "$sha" "$pty" "$psha" >> "$SCRATCH/refs.own"
    if [ "$ty" = commit ] || { [ "$ty" = tag ] && [ "$pty" = commit ]; }; then cands+=("$ref"); fi
  done < "$t"
  if [ -s "$SCRATCH/refs.own" ]; then adopt "$SCRATCH/refs.own" "$DEST/refs/$name.txt"; fi
  [ ${#cands[@]} -gt 0 ] || { echo "$repo" >> "$DEST/bundles/NONE.txt"; return 0; }
  gfile "$SCRATCH/count" "$repo" rev-list --count "${cands[@]}" ${NOT[@]+"${NOT[@]}"}
  count=$(cat "$SCRATCH/count")
  if [ "$count" -gt 0 ]; then
    for ref in "${cands[@]}"; do
      gfile "$SCRATCH/count" "$repo" rev-list --count "$ref" ${NOT[@]+"${NOT[@]}"}
      if [ "$(cat "$SCRATCH/count")" -gt 0 ]; then want+=("$ref"); fi
    done
  fi
  # An annotated tag whose commit a remote already has is not bundled (nothing new in
  # the pack); save the tag object itself so the tag can be recreated (git hash-object).
  while IFS=$'\t' read -r ref ty sha pty psha; do
    [ "$ty" = tag ] || continue
    case " ${want[*]+${want[*]}} " in *" $ref "*) continue ;; esac
    stream_to "$DEST/tags/$name/$sha.tag" "${GITP[@]}" -C "$repo" cat-file tag "$sha"
    [ "$STREAM_RC" = 0 ] || die "git cat-file tag $sha failed in $repo"
  done < "$SCRATCH/refs.own"
  if [ ${#want[@]} -gt 0 ]; then
    stream_to "$DEST/bundles/$name.bundle" "${GITP[@]}" -C "$repo" bundle create - "${want[@]}" ${NOT[@]+"${NOT[@]}"}
    [ "$STREAM_RC" = 0 ] || die "git bundle create failed in $repo (exit $STREAM_RC)"
    echo "bundle $name: ${#want[@]} ref(s): ${want[*]}"
  else
    echo "$repo" >> "$DEST/bundles/NONE.txt"
  fi
}

# bundle_detached WT NAME: a detached HEAD is named by no ref, so bundle it from
# inside its own worktree.
bundle_detached() {
  local wt=$1 name=$2 count
  gfile "$SCRATCH/count" "$wt" rev-list --count HEAD ${NOT[@]+"${NOT[@]}"}
  count=$(cat "$SCRATCH/count")
  [ "$count" -gt 0 ] || return 0
  stream_to "$DEST/bundles/$name.HEAD.bundle" "${GITP[@]}" -C "$wt" bundle create - HEAD ${NOT[@]+"${NOT[@]}"}
  [ "$STREAM_RC" = 0 ] || die "git bundle create HEAD failed in $wt (exit $STREAM_RC)"
  echo "bundle $name.HEAD: detached HEAD of $wt"
}

# note_excluded TEXT: something dropped from the archive on purpose (credential name).
note_excluded() { echo "$1" >> "$DEST/EXCLUDED.txt"; }

# scan_patch_headers WT FILE: warn about credential-named paths inside a patch (the
# patch is kept whole; the names are listed in EXCLUDED.txt).
scan_patch_headers() {
  local wt=$1 f=$2 line p
  while IFS= read -r line; do
    p=${line#diff --git a/}; p=${p%% b/*}
    if excluded_hit "$p"; then note_excluded "in patch ($(basename "$f")): $wt: $p"; fi
  done < <(grep -a '^diff --git ' "$f" || true)
}

# capture_worktree WT IS_MAIN: counts, then (unless LIVE_ONLY) the uncommitted state of
# one worktree, read-only on the pod. A clean worktree with no stash writes nothing.
capture_worktree() {
  local w=$1 is_main=$2 st=$SCRATCH/status.z m u n=0 h=0 dir i sha base rc line p
  gfile "$st" "$w" status --porcelain=v1 -z --untracked-files=all --ignore-submodules=none
  read -r m u < <(pl_status_counts "$st")
  gfile "$SCRATCH/lsv.z" "$w" ls-files -v -z
  pl_hidden "$SCRATCH/lsv.z" > "$SCRATCH/hidden.z"
  h=$(perl -0777 -ne 'my @a=split /\0/; print scalar(@a)' < "$SCRATCH/hidden.z")
  if [ "$is_main" = 1 ]; then
    gprobe "$w" show-ref --verify -q refs/stash
    case $STREAM_RC in
      0) gfile "$SCRATCH/stash.shas" "$w" rev-list -g refs/stash
         n=$(awk 'NF {c++} END {print c+0}' "$SCRATCH/stash.shas") ;;
      1) n=0 ;;
      *) die "git show-ref failed in $w (exit $STREAM_RC)" ;;
    esac
  fi
  if [ "$m" -eq 0 ] && [ "$u" -eq 0 ] && [ "$n" -eq 0 ] && [ "$h" -eq 0 ]; then return 0; fi
  if [ "$LIVE_ONLY" = 1 ]; then
    echo "$w modified=$m untracked=$u stash=$n hidden=$h" >> "$SCRATCH/live.dirty"
    return 0
  fi

  dir=$(dirty_dir "$w")
  mkdir -p "$dir"
  echo "$w modified=$m untracked=$u stash=$n hidden=$h" >> "$DEST/DIRTY.txt"
  adopt "$st" "$dir/status.txt"

  if [ "$m" -gt 0 ]; then
    gprobe "$w" rev-parse --verify -q HEAD
    case $STREAM_RC in
      0) base=HEAD ;;
      1) # Unborn only when HEAD names a branch whose ref does not exist; anything else is damage.
         gprobe "$w" symbolic-ref -q HEAD
         [ "$STREAM_RC" = 0 ] || die "HEAD of $w is unreadable (detached to a missing object?); refusing to treat it as unborn"
         gfile "$SCRATCH/ref.out" "$w" for-each-ref --count=1 "$(cat "$SCRATCH/probe")"
         [ ! -s "$SCRATCH/ref.out" ] || die "HEAD of $w points at an unreadable commit (corrupt repository?); refusing to treat it as unborn"
         base=$EMPTY_TREE
         echo "HEAD is unborn in $w; staged.patch is the index against the empty tree" > "$dir/NOTE.txt"
         echo "$(shasum -a 256 "$dir/NOTE.txt" | cut -d' ' -f1)  ${dir#"$DEST"/}/NOTE.txt" >> "$DEST/REMOTE.sha256" ;;
      *) die "HEAD of $w is unreadable (corrupt repository?); refusing to treat it as unborn" ;;
    esac
    # Two patches, always: index against HEAD, and working tree against the index.
    stream_to "$dir/staged.patch" "${GITP[@]}" -C "$w" diff --cached "${DIFFARGS[@]}" "$base"
    [ "$STREAM_RC" = 0 ] || die "git diff --cached failed in $w (exit $STREAM_RC)"
    stream_to "$dir/tracked.patch" "${GITP[@]}" -C "$w" diff "${DIFFARGS[@]}"
    [ "$STREAM_RC" = 0 ] || die "git diff failed in $w (exit $STREAM_RC)"
    scan_patch_headers "$w" "$dir/staged.patch"
    scan_patch_headers "$w" "$dir/tracked.patch"
  fi

  if [ "$u" -gt 0 ]; then
    gfile "$SCRATCH/untracked.z" "$w" ls-files --others --exclude-standard -z
    while IFS= read -r -d '' p; do
      if excluded_hit "$p"; then note_excluded "untracked: $w: $p"; fi
    done < "$SCRATCH/untracked.z"
    # shellcheck disable=SC2016  # the script runs on the pod
    stream_to "$dir/untracked.tar.gz" bash -c 'set -o pipefail; w=$1; shift; cd "$w" || exit 3
      GIT_OPTIONAL_LOCKS=0 git -c core.hooksPath=/dev/null -c core.fsmonitor=false ls-files --others --exclude-standard -z | tar -czf - "$@" --null -T -' _ "$w" "${EXCLUDES[@]}"
    case $STREAM_RC in 0|1) ;; *) die "tar of untracked files failed in $w (exit $STREAM_RC)" ;; esac
    gzip -t "$dir/untracked.tar.gz" || die "untracked tarball of $w fails gzip -t"
  fi

  if [ "$h" -gt 0 ]; then
    pl_lines "$SCRATCH/hidden.z" > "$SCRATCH/hidden.txt"
    adopt "$SCRATCH/hidden.txt" "$dir/hidden.txt"
    # skip-worktree / assume-unchanged files: invisible to status and diff, so tar them.
    # shellcheck disable=SC2016  # the script runs on the pod
    stream_to "$dir/hidden.tar.gz" bash -c 'set -o pipefail; w=$1; shift; cd "$w" || exit 3
      GIT_OPTIONAL_LOCKS=0 git -c core.hooksPath=/dev/null -c core.fsmonitor=false ls-files -v -z |
      while IFS= read -r -d "" e; do
        case $e in [a-zS]\ *) f=${e#? }; if [ -e "$f" ]; then printf "%s\0" "$f"; fi ;; esac
      done | tar -czf - "$@" --null -T -' _ "$w" "${EXCLUDES[@]}"
    case $STREAM_RC in 0|1) ;; *) die "tar of skip-worktree files failed in $w (exit $STREAM_RC)" ;; esac
    gzip -t "$dir/hidden.tar.gz" || die "hidden-files tarball of $w fails gzip -t"
  fi

  if [ "$n" -gt 0 ]; then
    gfile "$SCRATCH/stash.list" "$w" stash list
    adopt "$SCRATCH/stash.list" "$dir/stash-list.txt"
    adopt "$SCRATCH/stash.shas" "$dir/stash-shas.txt"
    # Every entry is exported from its commits, so no git-version feature is needed:
    # stash-N.patch is the tracked change (base -> stash commit); stash-N.untracked.patch
    # is the untracked part (third parent) as a new-files patch.
    i=0
    while [ "$i" -lt "$n" ]; do
      sha=$(sed -n "$((i + 1))p" "$SCRATCH/stash.shas")
      stream_to "$dir/stash-$i.patch" "${GITP[@]}" -C "$w" diff "${DIFFARGS[@]}" "$sha^1" "$sha"
      [ "$STREAM_RC" = 0 ] || die "git diff failed for stash entry $i in $w"
      gprobe "$w" rev-parse --verify -q "$sha^3"
      case $STREAM_RC in
        0) stream_to "$dir/stash-$i.untracked.patch" "${GITP[@]}" -C "$w" diff "${DIFFARGS[@]}" "$EMPTY_TREE" "$sha^3"
           [ "$STREAM_RC" = 0 ] || die "git diff failed for untracked part of stash entry $i in $w" ;;
        1) ;;
        *) die "git rev-parse failed for stash entry $i in $w" ;;
      esac
      i=$((i + 1))
    done
  fi
}

# process_repo REPO COMMON: bundles and dirty state of one repository and its worktrees.
process_repo() {
  local repo=$1 name i wt
  load_worktrees "$repo"
  load_remotes "$repo"
  name=$(wtname "${WT_PATH[0]}")
  if [ "$LIVE_ONLY" != 1 ]; then
    bundle_refs "$repo" "$name"
  fi
  i=0
  while [ "$i" -lt "${#WT_PATH[@]}" ]; do
    wt=${WT_PATH[$i]}
    if [ "${WT_BARE[$i]}" = 0 ] && [ "${WT_PRUN[$i]}" = 0 ]; then
      if [ "$LIVE_ONLY" != 1 ] && [ "${WT_DET[$i]}" = 1 ]; then bundle_detached "$wt" "$(wtname "$wt")"; fi
      if [ "$i" -eq 0 ]; then capture_worktree "$wt" 1; else capture_worktree "$wt" 0; fi
      if [ "$LIVE_ONLY" != 1 ]; then
        gfile "$SCRATCH/ign.z" "$wt" ls-files --others --ignored --exclude-standard --directory -z
        if [ -s "$SCRATCH/ign.z" ]; then
          pl_lines "$SCRATCH/ign.z" > "$SCRATCH/ign.txt"
          adopt "$SCRATCH/ign.txt" "$DEST/ignored/$(wtname "$wt").txt"
        fi
      fi
    elif [ "${WT_PRUN[$i]}" = 1 ]; then
      note_skip "prunable worktree (directory missing): $wt"
    fi
    i=$((i + 1))
  done
}

# scan_all: discovery plus per-repo processing (archive) or counting only (LIVE_ONLY).
scan_all() {
  local repo common
  discover
  while IFS=$'\t' read -r repo common; do
    [ -n "$repo" ] || continue
    echo "$common" >> "$SCRATCH/clone.list"
    process_repo "$repo"
  done < "$SCRATCH/clones.tsv"
}

cmd_archive() {
  check_dest

  local procs pf
  pf=$SCRATCH/ps.out; cap "$pf" ps -eo args=
  [ "$STREAM_RC" = 0 ] || die "could not list the pod's processes"
  procs=$(cat "$pf")
  if [ "$CONFIRMED" != 1 ] && session_running "$procs"; then
    die "interactive session still running (claude, herdr or tmux); end it, or pass --session-ended-confirmed"
  fi

  # shellcheck disable=SC2174  # only the leaf matters; its mode is asserted next
  mkdir -p -m 700 "$DEST"
  [ "$(mode_of "$DEST")" = "700" ] || die "destination $DEST is not mode 700"
  # A re-run starts clean: nothing stale may enter the manifest.
  rm -rf "$DEST/bundles" "$DEST/worktrees" "$DEST/refs" "$DEST/tags" "$DEST/ignored"
  rm -f "$DEST/REMOTE.sha256" "$DEST/SKIPPED.txt" "$DEST/DETACHED.txt" "$DEST/DIRTY.txt" \
        "$DEST/EXCLUDED.txt" "$DEST/CLONES.txt" "$DEST/MANIFEST.sha256" "$DEST/secure-agent-pod-home.tar.gz"
  mkdir -p "$DEST/bundles"
  : > "$DEST/REMOTE.sha256"; : > "$DEST/SKIPPED.txt"; : > "$DEST/DETACHED.txt"
  : > "$DEST/DIRTY.txt"; : > "$DEST/EXCLUDED.txt"; : > "$DEST/CLONES.txt"; : > "$DEST/bundles/NONE.txt"
  : > "$SCRATCH/clone.list"

  EXCLUDES=()
  local n
  set -f
  for n in $CRED_NAMES; do EXCLUDES+=("--exclude=$n"); done
  set +f
  EXCLUDES+=("--exclude=node_modules")

  # Which home paths exist on the pod (read-only probe).
  local p have present=""
  for p in $ARCHIVE_PATHS $OPTIONAL_PATHS; do
    # shellcheck disable=SC2016  # the script runs on the pod; $1 is its own argument
    cap "$SCRATCH/have" sh -c 'if [ -e "$1" ]; then echo yes; else echo no; fi' _ "$POD_HOME/$p"
    [ "$STREAM_RC" = 0 ] || die "could not probe $p on the pod"
    have=$(cat "$SCRATCH/have")
    case $have in
      yes) present="$present $p" ;;
      no) case " $OPTIONAL_PATHS " in *" $p "*) ;; *) echo "$p" >> "$DEST/SKIPPED.txt"; echo "WARNING: $p not found on the pod, skipped" >&2 ;; esac ;;
      *) die "unexpected probe answer for $p" ;;
    esac
  done

  local tarflags=() tv
  cap "$SCRATCH/tarv" tar --version || true
  tv=$(cat "$SCRATCH/tarv")
  case $tv in *"GNU tar"*) tarflags+=("--warning=no-file-changed") ;; esac

  echo "archiving home tree from $POD_HOME ..."
  # shellcheck disable=SC2086  # $present is a space-separated list of simple paths
  stream_to "$DEST/secure-agent-pod-home.tar.gz" tar -C "$POD_HOME" -czf - ${tarflags[@]+"${tarflags[@]}"} "${EXCLUDES[@]}" $present
  case $STREAM_RC in
    0) ;;
    1) echo "WARNING: tar reported files changing while it read them (exit 1); archive kept" >&2 ;;
    *) die "tar failed on the pod with exit $STREAM_RC" ;;
  esac
  gzip -t "$DEST/secure-agent-pod-home.tar.gz" || die "tarball fails gzip -t"
  tar -tzf "$DEST/secure-agent-pod-home.tar.gz" >/dev/null || die "tarball cannot be listed"

  scan_all
  sort -u "$SCRATCH/clone.list" > "$DEST/CLONES.txt"

  # shellcheck disable=SC2094  # find skips MANIFEST.sha256 itself
  (cd "$DEST" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 shasum -a 256 \
     | sed 's#  \./#  #' > MANIFEST.sha256)
  echo "tarball files: $(tar -tzf "$DEST/secure-agent-pod-home.tar.gz" | wc -l | tr -d ' ')"
  if [ -s "$DEST/EXCLUDED.txt" ]; then echo "NOTE: $(wc -l < "$DEST/EXCLUDED.txt" | tr -d ' ') credential-named path(s) were left out; see EXCLUDED.txt" >&2; fi
  echo "archive written to $DEST; run: $(basename "$0") verify --dest $DEST"
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
  if [ -f "$DEST/SKIPPED.txt" ] && grep -Eq '^(pruned|unreadable|not a usable|prunable)' "$DEST/SKIPPED.txt"; then
    echo "WARN some paths were pruned, unreadable or not repositories; see SKIPPED.txt"
  fi
  if [ -s "$DEST/DETACHED.txt" ]; then
    fail "no uncaptured detached worktree commits (DETACHED.txt):"; sed 's/^/     /' "$DEST/DETACHED.txt"
  else
    pass "no uncaptured detached worktree commits"
  fi
  if [ -s "$DEST/EXCLUDED.txt" ]; then
    echo "WARN credential-named paths were left out of the archive; see EXCLUDED.txt:"; sed 's/^/     /' "$DEST/EXCLUDED.txt"
  fi

  # Uncommitted clone state: DIRTY.txt against what is on disk.
  if [ -s "$DEST/DIRTY.txt" ]; then
    echo "INFO dirty clones (uncommitted state archived under worktrees/):"; sed 's/^/     /' "$DEST/DIRTY.txt"
    local dline dpath ddir dm du dn dh bad="" k
    while IFS= read -r dline; do
      [ -n "$dline" ] || continue
      dpath=${dline%% modified=*}
      dm=$(sed -n 's/.* modified=\([0-9]*\) .*/\1/p' <<<"$dline")
      du=$(sed -n 's/.* untracked=\([0-9]*\) .*/\1/p' <<<"$dline")
      dn=$(sed -n 's/.* stash=\([0-9]*\) .*/\1/p' <<<"$dline")
      dh=$(sed -n 's/.* hidden=\([0-9]*\)$/\1/p' <<<"$dline")
      ddir=$(dirty_dir "$dpath")
      if [ ! -d "$ddir" ] || [ -z "$(ls -A "$ddir" 2>/dev/null)" ]; then bad="$bad $dpath(missing)"; continue; fi
      [ -f "$ddir/status.txt" ] || bad="$bad $dpath(status.txt)"
      if [ "${dm:-0}" -gt 0 ]; then
        [ -f "$ddir/staged.patch" ] && [ -f "$ddir/tracked.patch" ] || bad="$bad $dpath(patches)"
      fi
      if [ "${du:-0}" -gt 0 ]; then [ -f "$ddir/untracked.tar.gz" ] || bad="$bad $dpath(untracked.tar.gz)"; fi
      if [ "${dh:-0}" -gt 0 ]; then [ -f "$ddir/hidden.tar.gz" ] && [ -f "$ddir/hidden.txt" ] || bad="$bad $dpath(hidden)"; fi
      k=0
      while [ "$k" -lt "${dn:-0}" ]; do
        [ -f "$ddir/stash-$k.patch" ] || bad="$bad $dpath(stash-$k)"
        k=$((k + 1))
      done
      if [ -f "$ddir/stash-$k.patch" ]; then bad="$bad $dpath(stash-$k unexpected)"; fi
    done < "$DEST/DIRTY.txt"
    if [ -z "$bad" ]; then pass "dirty clone state present"; else fail "dirty clone state present (problems:$bad)"; fi
  else
    echo "INFO no dirty clones"
  fi
  if [ -d "$DEST/worktrees" ]; then
    local wf unlisted="" credbad="" um
    while IFS= read -r -d '' wf; do
      grep -Fq "  ${wf#"$DEST"/}" "$DEST/REMOTE.sha256" || unlisted="$unlisted ${wf#"$DEST"/}"
      case $wf in
        */untracked.tar.gz|*/hidden.tar.gz)
          if gzip -t "$wf" 2>/dev/null && um=$(tar -tzf "$wf" 2>/dev/null); then
            while IFS= read -r m; do
              [ -n "$m" ] || continue
              if cred_hit "${m%/}"; then credbad="$credbad $m"; fi
            done <<<"$um"
          else
            fail "worktree tarball readable: ${wf#"$DEST"/}"
          fi ;;
      esac
    done < <(find "$DEST/worktrees" -type f -print0 | sort -z)
    case $unlisted in "") pass "every worktrees/ file has a pod-side digest" ;; *) fail "every worktrees/ file has a pod-side digest (unlisted:$unlisted)" ;; esac
    case $credbad in "") pass "no credential files in untracked tarballs" ;; *) fail "no credential files in untracked tarballs:$credbad" ;; esac
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

  if [ "$LIVE" = 1 ]; then
    # Re-scan the pod, read-only, and compare with what the archive recorded.
    LIVE_ONLY=1
    : > "$SCRATCH/live.dirty"; : > "$SCRATCH/live.skipped"; : > "$SCRATCH/clone.list"
    scan_all
    sort -u "$SCRATCH/clone.list" > "$SCRATCH/live.clones"
    LIVE_ONLY=0
    if [ -f "$DEST/CLONES.txt" ] && diff <(sort -u "$DEST/CLONES.txt") "$SCRATCH/live.clones" >/dev/null; then
      pass "live clone list matches the archive"
    else
      fail "live clone list matches the archive (diff: $(diff <(sort -u "$DEST/CLONES.txt" 2>/dev/null) "$SCRATCH/live.clones" | tr '\n' ';'))"
    fi
    if diff <(sort "$DEST/DIRTY.txt") <(sort "$SCRATCH/live.dirty") >/dev/null; then
      pass "live dirty state matches the archive"
    else
      fail "live dirty state matches the archive (diff: $(diff <(sort "$DEST/DIRTY.txt") <(sort "$SCRATCH/live.dirty") | tr '\n' ';'))"
    fi
  fi

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
LIVE=0
while [ $# -gt 0 ]; do
  case $1 in
    --dest) [ $# -ge 2 ] || usage; DEST=$2; shift 2 ;;
    --session-ended-confirmed) CONFIRMED=1; shift ;;
    --live) LIVE=1; shift ;;
    --old-file-gone-ok) OLD_GONE_OK=1; shift ;;
    *) usage ;;
  esac
done

SCRATCH=$(mktemp -d)
trap 'rm -rf "$SCRATCH"' EXIT

case $SUB in
  archive) cmd_archive ;;
  verify) cmd_verify ;;
  key-fingerprint) cmd_key_fingerprint ;;
  *) usage ;;
esac
