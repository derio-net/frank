#!/usr/bin/env bash
# Archive, verify and key-check helper for retiring the secure-agent-pod.
#
# Operator-run, on the Mac. Read-only against the cluster: it never deletes,
# patches, restarts or applies anything. Spec:
# docs/superpowers/specs/2026-11-08--agents--retire-vk-design.md (R9).
#
#   archive          stream the files worth keeping off the pod into $DEST: a home-tree
#                    tarball; ONE self-contained git bundle per repository (every ref,
#                    including remote-tracking refs, plus in-progress and detached heads as
#                    extra revs; no prerequisites); and the UNCOMMITTED state of every clone
#                    and linked worktree (index and working-tree patches, untracked and
#                    skip-worktree files, conflicts with their stages, in-progress merge or
#                    rebase state, every stash entry) under worktrees/
#   verify           check what archive wrote (checksums, tarball, bundles, dirty state, mode);
#                    offline. `verify --live` also re-scans the pod, read-only, and diffs it
#   restore-worktree rebuild one saved worktree in a fresh checkout, locally (never contacts
#                    the pod): restore-worktree --dest ARCHIVE --worktree ORIGINAL_PATH --target DIR
#   key-fingerprint  compare the GitHub App key across the live Secret and SOPS files
#
# ~/.claude goes into the home tarball whole, minus credentials (CRED_NAMES, CLAUDE_CREDS) and
# caches (CLAUDE_CACHES, node_modules); both lists are anchored to .claude/. todos/, debug/,
# logs and ide/ state are kept; only ide/*.lock goes. Transcripts are complete only after
# the session ended.
# Known limits: reflog-only commits (reachable only through a reflog) are not captured;
# ignored files are listed in ignored/, not saved; clones under .cache or node_modules
# are pruned and recorded in SKIPPED.txt. LOCAL-ONLY.txt is information: refs whose commits
# no network remote tracking ref has (a remote whose URL is a local path does not count).
#
# Env: KUBECTL (default kubectl), SOPS (default sops), GIT (default git), POD_HOME (default
# /home/claude; tests point it at a fixture directory).
set -euo pipefail

KUBECTL=${KUBECTL:-kubectl}
SOPS=${SOPS:-sops}
DF=${DF:-df}
GIT=${GIT:-git}
POD_HOME=${POD_HOME:-/home/claude}
DEST_DEFAULT="$HOME/Archives/secure-agent-pod-2026-11"
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)

usage() {
  cat >&2 <<USAGE
usage: $(basename "$0") <archive|verify|key-fingerprint|restore-worktree> [--dest DIR] [--session-ended-confirmed] [--accept-unreadable] [--skip-space-check] [--live] [--old-file-gone-ok]
  archive          copy the files worth keeping off the pod into DEST (default $DEST_DEFAULT):
                   home tarball (interviews, orgs, .hermes, ~/.claude, the audit archive, the
                   vibe-kanban sqlite, chorebot's config; see below); one self-contained bundle per repository (all refs incl.
                   remote-tracking, no prerequisites); uncommitted clone state (index and
                   working-tree patches, untracked and skip-worktree files, conflicts with
                   their stages, merge/rebase-in-progress state, every stash entry); read-only
                   on the pod. Known limits: reflog-only commits; ignored files are listed in
                   ignored/, not saved; clones under .cache or node_modules are pruned
                   (recorded in SKIPPED.txt). Unreadable paths and unusable repositories fail
                   verify unless archive ran with --accept-unreadable (ACCEPTED.txt). A
                   preflight compares the pod's data with the free space at DEST (x1.2) and
                   aborts unless --skip-space-check is given.
                   ~/.claude is archived whole (projects/ transcripts, CLAUDE.md, settings*.json,
                   memory, agents, commands, skills, hooks, history.jsonl, plans, todos, ide
                   state) EXCEPT credentials (every credential name below, plus .claude/*.token,
                   .claude/*oauth*.json, .claude/*mcp-auth*) and caches (.claude/statsig,
                   shell-snapshots, cache, .cache, plugins/cache, plugins/marketplaces,
                   node_modules, *.lock); EXCLUDED.txt lists what was left out. Git clones under
                   .claude are still bundled. Transcripts are complete only once the session has ended.
  verify           verify the archive in DEST, offline; --live also re-scans the pod
                   (read-only) and fails if its clones or dirty state changed since the archive
  restore-worktree rebuild a saved worktree locally: --dest ARCHIVE --worktree ORIGINAL_PATH
                   --target DIR (an empty dir or fresh clone); never contacts the pod
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
ARCHIVE_PATHS="interviews orgs .hermes .claude .willikins-agent/audit-archive .local/share/vibe-kanban/db.v2.sqlite repos/willikins/scripts/chorebot/config.yaml"
# ~/.claude is archived whole (session transcripts in projects/, CLAUDE.md, settings, memory,
# agents, commands, skills, hooks, history, plans, todos, ...) except credentials and pure
# caches. Both lists are anchored to .claude/ so same-named dirs elsewhere (orgs/x/cache,
# interviews/logs) are untouched. Credential names also include every CRED_NAMES entry.
# todos/, debug/, logs and ide/ state are KEPT (not clearly regenerable); only ide/*.lock goes.
# Git clones under .claude (e.g. plugin checkouts outside plugins/cache) are still found by
# discovery and bundled like any other clone.
CLAUDE_CREDS=".claude/*.token .claude/*oauth*.json .claude/*mcp-auth*"
CLAUDE_CACHES=".claude/statsig .claude/shell-snapshots .claude/cache .claude/.cache .claude/plugins/cache .claude/plugins/marketplaces .claude/*.lock"
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
export STREAM_TMP="$d"
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
      -c safe.directory=* -c diff.relative=false -c diff.noprefix=false -c diff.mnemonicPrefix=false
      -c color.diff=never -c color.ui=never)
# The same dialect for inline pod-side scripts (bash -c "$PODGITFN"'...'): plain `git`
# inside them resolves to this function, so none can run without safe.directory (a repo
# owned by another uid) or with hooks/fsmonitor enabled. A test forbids `bash -c '...git`.
# shellcheck disable=SC2016  # evaluated on the pod
PODGITFN='git() { GIT_OPTIONAL_LOCKS=0 command git -c safe.directory="*" -c core.hooksPath=/dev/null -c core.fsmonitor=false "$@"; }
tarlist() { local l="$STREAM_TMP/list"; cat > "$l"; if [ -s "$l" ]; then tar -czf - "$@" --null -T "$l"; else head -c 10240 /dev/zero | gzip -c; fi; }'
DIFFARGS=(--binary --no-ext-diff --no-textconv --no-color --src-prefix=a/ --dst-prefix=b/)

# sel REPO: how to point git at REPO. A normal repository is entered with -C; an
# "orphan" git dir (a deinitialised submodule: git dir without a working tree) is
# selected with --git-dir and treated as bare.
ORPHAN=0
SEL=()
sel() {
  if [ "$ORPHAN" = 1 ]; then SEL=(--git-dir="$1" -c core.bare=true); else SEL=(-C "$1"); fi
}

# gfile OUT REPO ARGS...: a git call, output to OUT; aborts unless it exits 0.
gfile() {
  local out=$1 repo=$2; shift 2
  sel "$repo"
  cap "$out" "${GITP[@]}" "${SEL[@]}" "$@"
  [ "$STREAM_RC" = 0 ] || die "git $1 failed in $repo (exit $STREAM_RC)"
}

# gprobe REPO ARGS...: like gfile but leaves the exit status in STREAM_RC.
gprobe() {
  local repo=$1; shift
  sel "$repo"
  cap "$SCRATCH/probe" "${GITP[@]}" "${SEL[@]}" "$@"
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
  for n in $CLAUDE_CREDS; do
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
  perl -0777 -e 'my $d=<STDIN>; for my $e (split /\0/,$d){ next unless $e=~/^([abcdefghijklmnopqrstuvwxyzS]) (.*)$/s; print "$1 $2\0"; }' < "$1"
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

# discover: fills $SCRATCH/clones.tsv with "repo<TAB>common-dir<TAB>kind", one line per
# distinct repository (linked worktrees and submodules resolve to their own common dir;
# kind is "repo", or "orphan" for a deinitialised submodule's git dir).
discover() {
  local f=$SCRATCH/find.out p repo common seen="" line gd c
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
    # A junk HEAD or a repository the pod user may not read must be recorded, not abort
    # the run: the failing rev-parse is handled explicitly (a bare `cd "$(...)"` would
    # succeed with an empty argument).
    # shellcheck disable=SC2016  # the script runs on the pod
    cap "$SCRATCH/common" bash -c "$PODGITFN"'; cd "$1" || exit 3; c=$(git rev-parse --git-common-dir) || exit 3; cd "$c" && pwd -P' _ "$repo"
    if [ "$STREAM_RC" != 0 ]; then note_skip "not a usable git repository: $repo"; continue; fi
    common=$(cat "$SCRATCH/common")
    case $seen in *"|$common|"*) continue ;; esac
    seen="$seen|$common|"
    printf '%s\trepo\t%s\n' "$repo" "$common" >> "$SCRATCH/clones.tsv"
  done < "$f"
  # Deinitialised submodules keep their git dir under <common>/modules/<name> with no
  # working tree, so nothing above points at them; their local commits still count.
  local seen_now=$seen cm
  while IFS= read -r cm; do
    [ -n "$cm" ] || continue
    # shellcheck disable=SC2016  # the script runs on the pod
    cap "$f" sh -c 'if [ -d "$1/modules" ]; then find -H "$1/modules" -name HEAD -type f -not -path "*/objects/*" -not -path "*/logs/*" -not -path "*/refs/*" -not -path "*/worktrees/*" -print0; fi' _ "$cm"
    [ "$STREAM_RC" = 0 ] || { note_skip "unreadable: modules of $cm"; continue; }
    while IFS= read -r -d '' p; do
      gd=${p%/HEAD}
      # shellcheck disable=SC2016  # the script runs on the pod
      cap "$SCRATCH/common" sh -c 'cd "$1" && [ -d objects ] && pwd -P' _ "$gd"
      [ "$STREAM_RC" = 0 ] || continue
      c=$(cat "$SCRATCH/common")
      case $seen in *"|$c|"*) continue ;; esac
      seen="$seen|$c|"
      printf '%s\torphan\t%s\n' "$gd" "$c" >> "$SCRATCH/clones.tsv"
    done < "$f"
  done < <(printf '%s\n' "$seen_now" | tr '|' '\n' | grep -v '^$' || true)
}

# --- per repository ----------------------------------------------------------
WT_PATH=(); WT_BARE=(); WT_PRUN=(); WT_DET=(); WT_HEAD=()
NOT=()          # rev-list exclusion: --not --remotes=<network remote> ...

load_worktrees() {   # REPO
  local repo=$1 t=$SCRATCH/wl i=0 a b c d e
  cap "$t" "${GITP[@]}" -C "$repo" worktree list --porcelain -z
  [ "$STREAM_RC" = 0 ] || gfile "$t" "$repo" worktree list --porcelain
  pl_worktrees "$t" > "$t.tuples"
  WT_PATH=(); WT_BARE=(); WT_PRUN=(); WT_DET=(); WT_HEAD=()
  while IFS= read -r -d '' a && IFS= read -r -d '' b && IFS= read -r -d '' c && IFS= read -r -d '' d && IFS= read -r -d '' e; do
    case $a in *$'\n'*) die "worktree path contains a newline: unsupported" ;; esac
    WT_PATH[i]=$a; WT_BARE[i]=$b; WT_PRUN[i]=$c; WT_DET[i]=$d; WT_HEAD[i]=$e; i=$((i + 1))
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
LOCAL_REMOTES=" "
load_remotes() {
  local repo=$1 t=$SCRATCH/cfg k n u
  NOT=(); LOCAL_REMOTES=" "
  sel "$repo"
  cap "$t" "${GITP[@]}" "${SEL[@]}" config -z --get-regexp '^remote\..*\.url$'
  case $STREAM_RC in 0|1) ;; *) die "git config failed in $repo (exit $STREAM_RC)" ;; esac
  pl_remotes "$t" > "$t.tuples"
  while IFS= read -r -d '' k; do
    if [ "$k" = S ]; then
      IFS= read -r -d '' n
      if [ ${#NOT[@]} -eq 0 ]; then NOT=(--not); fi
      NOT+=("--remotes=$n")
    else
      IFS= read -r -d '' n; IFS= read -r -d '' u
      LOCAL_REMOTES="$LOCAL_REMOTES$n "
      echo "WARNING: remote '$n' of $repo is a local path ($u); its tracking refs do not count as a remote copy (they are bundled instead)" >&2
    fi
  done < "$t.tuples"
}

CANDS=()
EXTRA_FILE=""      # $SCRATCH/extra.revs: "sha<TAB>label" lines for in-progress and detached heads
# collect_refs REPO NAME: every ref goes into $SCRATCH/refs.own (the bundle holds them
# all); CANDS[] gets the ones a network remote might not have, for LOCAL-ONLY.txt.
# Tracking refs of local-path remotes count as local. Live mode keeps the listing for
# the comparison with the archive.
collect_refs() {
  local repo=$1 name=$2 t=$SCRATCH/refs.txt ref ty sha pty keep l
  CANDS=()
  gfile "$t" "$repo" for-each-ref --format='%(refname)	%(objecttype)	%(objectname)	%(*objecttype)	%(*objectname)' refs/
  cp "$t" "$SCRATCH/refs.own"
  while IFS=$'\t' read -r ref ty sha pty _; do
    [ -n "$ref" ] || continue
    keep=1
    case $ref in
      refs/remotes/*)
        keep=0
        for l in $LOCAL_REMOTES; do
          case $ref in "refs/remotes/$l/HEAD") ;; "refs/remotes/$l/"*) keep=1 ;; esac
        done ;;
    esac
    [ "$keep" = 1 ] || continue
    if [ "$ty" = commit ]; then
      CANDS+=("$ref")
    elif [ "$ty" = tag ]; then
      if [ "$pty" = commit ]; then CANDS+=("$ref")
      elif [ "$pty" = tag ]; then   # a tag of a tag: follow the chain to its final target
        gfile "$SCRATCH/final" "$repo" cat-file -t "$ref^{}"
        if [ "$(cat "$SCRATCH/final")" = commit ]; then CANDS+=("$ref"); fi
      fi
    fi
  done < "$t"
  if [ "$LIVE_ONLY" = 1 ] && [ -s "$SCRATCH/refs.own" ]; then
    mkdir -p "$SCRATCH/live.refs"; cp "$SCRATCH/refs.own" "$SCRATCH/live.refs/$name.txt"
  fi
}

TOTAL_POD_KB=0
TOTAL_BUNDLE_B=0

# bundle_refs REPO NAME COMMON: ONE self-contained bundle per repository: every ref
# (heads, tags, notes, stash, custom namespaces and remote-tracking refs) with no
# exclusion, so it has no prerequisites and restores with nothing but the archive.
# In-progress heads and detached HEADs ride along as extra revs (their objects are in
# the pack; their shas are listed in EXTRA-REVS.txt). The comparison with the network
# remotes is information only: LOCAL-ONLY.txt.
bundle_refs() {
  local repo=$1 name=$2 common=$3 ref kb size sha label extras=() seen=" "
  collect_refs "$repo" "$name"
  if [ -s "$SCRATCH/refs.own" ]; then adopt "$SCRATCH/refs.own" "$DEST/refs/$name.txt"; fi
  sel "$repo"
  if [ ${#CANDS[@]} -gt 0 ]; then
    gfile "$SCRATCH/count" "$repo" rev-list --count "${CANDS[@]}" ${NOT[@]+"${NOT[@]}"}
    if [ "$(cat "$SCRATCH/count")" -gt 0 ]; then
      for ref in "${CANDS[@]}"; do
        gfile "$SCRATCH/count" "$repo" rev-list --count "$ref" ${NOT[@]+"${NOT[@]}"}
        if [ "$(cat "$SCRATCH/count")" -gt 0 ]; then printf '%s\t%s\n' "$repo" "$ref" >> "$DEST/LOCAL-ONLY.txt"; fi
      done
    fi
  fi
  # Extra revs: heads named by files or detached worktrees, no ref points at them. One
  # batch check keeps the commits that exist; the rest are recorded, not bundled.
  if [ -s "$EXTRA_FILE" ]; then
    local cands=() types
    while IFS=$'\t' read -r sha label; do
      [ -n "$sha" ] || continue
      case $seen in *" $sha "*) continue ;; esac
      seen="$seen$sha "
      cands+=("$sha")
    done < "$EXTRA_FILE"
    if [ ${#cands[@]} -gt 0 ]; then
      # shellcheck disable=SC2016  # the script runs on the pod
      cap "$SCRATCH/extra.types" bash -c "$PODGITFN"'; r=$1; shift; printf "%s\n" "$@" | git -C "$r" cat-file --batch-check' _ "$repo" "${cands[@]}"
      [ "$STREAM_RC" = 0 ] || die "could not check the extra revs of $repo"
      types=$SCRATCH/extra.types
      while IFS=$'\t' read -r sha label; do
        [ -n "$sha" ] || continue
        case $(grep -a "^$sha " "$types" | head -1) in
          "$sha commit "*)
            case " ${extras[*]+${extras[*]}} " in *" $sha "*) ;; *) extras+=("$sha") ;; esac
            printf '%s\t%s\t%s\n' "$repo" "$sha" "$label" >> "$DEST/EXTRA-REVS.txt" ;;
          *) note_skip "extra rev $sha ($label) in $repo is not a readable commit; not bundled" ;;
        esac
      done < "$EXTRA_FILE"
    fi
  fi
  gprobe "$repo" rev-parse --verify -q HEAD
  if [ ! -s "$SCRATCH/refs.own" ] && [ "$STREAM_RC" != 0 ]; then
    printf '%s\t-\n' "$common" >> "$DEST/BUNDLES.txt"
    echo "no refs in $repo; nothing to bundle"
    return 0
  fi
  cap "$SCRATCH/du" du -sk "$common"
  kb=$(cut -f1 "$SCRATCH/du" | head -1)
  TOTAL_POD_KB=$((TOTAL_POD_KB + ${kb:-0}))
  echo "bundling $repo (git dir on the pod: ${kb:-?} KiB)"
  stream_to "$DEST/bundles/$name.bundle" "${GITP[@]}" "${SEL[@]}" bundle create - --all ${extras[@]+"${extras[@]}"}
  [ "$STREAM_RC" = 0 ] || die "git bundle create failed in $repo (exit $STREAM_RC)"
  size=$(wc -c < "$DEST/bundles/$name.bundle" | tr -d ' ')
  TOTAL_BUNDLE_B=$((TOTAL_BUNDLE_B + size))
  printf '%s\t%s.bundle\n' "$common" "$name" >> "$DEST/BUNDLES.txt"
  echo "  bundle $name.bundle: $size bytes"
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

# Files in a worktree's git dir that describe an operation in progress. The first group
# marks one as running; the rest travel with it.
STATE_TRIGGERS="MERGE_HEAD MERGE_AUTOSTASH CHERRY_PICK_HEAD REVERT_HEAD REBASE_HEAD rebase-merge rebase-apply sequencer BISECT_LOG BISECT_START"
STATE_NAMES="$STATE_TRIGGERS MERGE_AUTOSTASH MERGE_MSG MERGE_MODE AUTO_MERGE ORIG_HEAD SQUASH_MSG BISECT_TERMS BISECT_EXPECTED_REV BISECT_ANCESTORS_OK BISECT_NAMES"

# Git-dir files whose content can be the only reference to a commit (an autostash, a
# stopped rebase step, a bisect or notes-merge state ...). Every sha found in them, in
# these files and in everything under rebase-merge/, rebase-apply/ and sequencer/, rides
# in the repository bundle as an extra rev.
SHA_FILES="MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD REBASE_HEAD ORIG_HEAD MERGE_AUTOSTASH AUTO_MERGE FETCH_HEAD BISECT_START BISECT_LOG BISECT_TERMS BISECT_EXPECTED_REV BISECT_ANCESTORS_OK BISECT_NAMES NOTES_MERGE_PARTIAL NOTES_MERGE_REF"

# export_stash_commit DIR PREFIX WT SHA: a stash-shaped commit (stash entry or autostash)
# as patches: PREFIX.patch (tracked change), PREFIX.index.patch (staged part) and
# PREFIX.untracked.patch (third parent, as new files).
export_stash_commit() {
  local dir=$1 prefix=$2 w=$3 sha=$4
  stream_to "$dir/$prefix.patch" "${GITP[@]}" -C "$w" diff "${DIFFARGS[@]}" "$sha^1" "$sha"
  [ "$STREAM_RC" = 0 ] || die "git diff failed for $prefix in $w"
  stream_to "$dir/$prefix.index.patch" "${GITP[@]}" -C "$w" diff "${DIFFARGS[@]}" "$sha^1" "$sha^2"
  [ "$STREAM_RC" = 0 ] || die "git diff failed for the index part of $prefix in $w"
  gprobe "$w" rev-parse --verify -q "$sha^3"
  case $STREAM_RC in
    0) stream_to "$dir/$prefix.untracked.patch" "${GITP[@]}" -C "$w" diff "${DIFFARGS[@]}" "$EMPTY_TREE" "$sha^3"
       [ "$STREAM_RC" = 0 ] || die "git diff failed for the untracked part of $prefix in $w" ;;
    1) ;;
    *) die "git rev-parse failed for $prefix in $w" ;;
  esac
}

# add_note FILE TEXT: a line for the worktree's NOTE.txt (written at the end).
add_note() { echo "$2" >> "$1"; }

# capture_worktree WT IS_MAIN: counts, then (unless LIVE_ONLY) the uncommitted state of
# one worktree, read-only on the pod. A clean worktree with no stash writes nothing.
capture_worktree() {
  local w=$1 is_main=$2 st=$SCRATCH/status.z m u n=0 h=0 um=0 sf=0 dir i sha base rc line p gd e nm
  local notes=$SCRATCH/note.txt
  : > "$notes"
  add_note "$notes" "Restore: bash scripts/retire-secure-agent-pod.sh restore-worktree --dest <this archive> --worktree '$w' --target <empty or fresh clone dir>  (runs locally; never contacts the pod)"
  gfile "$st" "$w" status --porcelain=v1 -z --untracked-files=all --ignore-submodules=none
  read -r m u < <(pl_status_counts "$st")
  gfile "$SCRATCH/lsv.z" "$w" ls-files -v -z
  pl_hidden "$SCRATCH/lsv.z" > "$SCRATCH/hidden.z"
  h=$(perl -0777 -ne 'my @a=split /\0/; print scalar(@a)' < "$SCRATCH/hidden.z")
  gfile "$SCRATCH/unmerged.z" "$w" ls-files -u -z
  um=$(perl -0777 -ne 'my %s; for (split /\0/){ next unless /\t(.*)$/s; $s{$1}=1 } print scalar(keys %s)' < "$SCRATCH/unmerged.z")
  # Operation in progress (merge, rebase, cherry-pick, revert, bisect)?
  gfile "$SCRATCH/gd" "$w" rev-parse --absolute-git-dir
  gd=$(cat "$SCRATCH/gd")
  # shellcheck disable=SC2016,SC2086  # the script runs on the pod; STATE_NAMES is a word list
  cap "$SCRATCH/state.names" bash -c 'cd "$1" || exit 3; shift; for n in "$@"; do if [ -e "$n" ]; then printf "%s\0" "$n"; fi; done' _ "$gd" $STATE_NAMES
  [ "$STREAM_RC" = 0 ] || die "could not look for in-progress state in $gd"
  while IFS= read -r -d '' nm; do
    case " $STATE_TRIGGERS " in *" $nm "*) sf=1 ;; esac
  done < "$SCRATCH/state.names"
  # Every sha the git dir names (see SHA_FILES) is reachable from no ref necessarily; it
  # goes into the repository bundle as an extra rev. Autostash commits are remembered for
  # patch export too.
  : > "$SCRATCH/autostash.shas"
  if [ "$LIVE_ONLY" != 1 ]; then
    # shellcheck disable=SC2016,SC2086  # the script runs on the pod; SHA_FILES is a word list
    cap "$SCRATCH/gd.shas" bash -c "$PODGITFN"'; cd "$1" || exit 3; shift
      { for n in "$@"; do if [ -f "$n" ]; then printf "%s\0" "$n"; fi; done
        find rebase-merge rebase-apply sequencer -type f -print0 2>/dev/null; } |
      while IFS= read -r -d "" f; do
        grep -aEo "[0-9a-f]{40}" "$f" | while IFS= read -r sha; do printf "%s\t%s\n" "$sha" "$f"; done
      done' _ "$gd" $SHA_FILES
    [ "$STREAM_RC" = 0 ] || die "could not read the sha-bearing git-dir files of $gd"
    while IFS=$'\t' read -r sha nm; do
      [ -n "$sha" ] || continue
      printf '%s\t%s\n' "$sha" "$w:$nm" >> "$EXTRA_FILE"
      case ${nm##*/} in autostash|MERGE_AUTOSTASH) echo "$sha" >> "$SCRATCH/autostash.shas" ;; esac
    done < "$SCRATCH/gd.shas"
  fi
  if [ "$is_main" = 1 ]; then
    gprobe "$w" show-ref --verify -q refs/stash
    case $STREAM_RC in
      0) gfile "$SCRATCH/stash.shas" "$w" rev-list -g refs/stash
         n=$(awk 'NF {c++} END {print c+0}' "$SCRATCH/stash.shas")
         # older entries are reachable only through the reflog: extra revs, so they can be
         # restored as real stash entries
         if [ "$LIVE_ONLY" != 1 ]; then
           while IFS= read -r sha; do [ -z "$sha" ] || printf '%s\t%s\n' "$sha" "$w:stash" >> "$EXTRA_FILE"; done < "$SCRATCH/stash.shas"
         fi ;;
      1) n=0 ;;
      *) die "git show-ref failed in $w (exit $STREAM_RC)" ;;
    esac
  fi
  if [ "$m" -eq 0 ] && [ "$u" -eq 0 ] && [ "$n" -eq 0 ] && [ "$h" -eq 0 ] && [ "$um" -eq 0 ] && [ "$sf" -eq 0 ]; then return 0; fi
  local counts="modified=$m untracked=$u stash=$n hidden=$h unmerged=$um state=$sf"
  if [ "$LIVE_ONLY" = 1 ]; then
    echo "$w $counts" >> "$SCRATCH/live.dirty"
    return 0
  fi

  dir=$(dirty_dir "$w")
  mkdir -p "$dir"
  echo "$w $counts" >> "$DEST/DIRTY.txt"
  adopt "$st" "$dir/status.txt"
  # meta.txt: what the restore helper needs (which bundle, the HEAD to check out).
  gprobe "$w" rev-parse --verify -q HEAD
  local headsha=unborn headref=detached
  if [ "$STREAM_RC" = 0 ]; then headsha=$(cat "$SCRATCH/probe"); fi
  gprobe "$w" symbolic-ref -q HEAD
  if [ "$STREAM_RC" = 0 ]; then headref=$(cat "$SCRATCH/probe"); fi
  printf 'bundle=%s.bundle\nhead=%s\nheadref=%s\nworktree=%s\n' "$(wtname "$REPO_FIRST")" "$headsha" "$headref" "$w" > "$SCRATCH/meta.txt"
  adopt "$SCRATCH/meta.txt" "$dir/meta.txt"

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
         add_note "$notes" "HEAD is unborn in $w; staged.patch is the index against the empty tree" ;;
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

  if [ "$um" -gt 0 ]; then
    # Conflicted paths: the patches cannot carry them. Keep the working-tree files (conflict
    # markers intact), the index listing (mode, blob, stage), and every stage's content.
    adopt "$SCRATCH/unmerged.z" "$dir/unmerged.z"
    # shellcheck disable=SC2016  # the script runs on the pod
    stream_to "$dir/conflicted.tar.gz" bash -c "$PODGITFN"'; set -o pipefail; w=$1; shift; cd "$w" || exit 3
      git ls-files -u -z |
      while IFS= read -r -d "" e; do
        mode=${e%% *}; f=${e#*$'"'"'\t'"'"'}
        if [ "$mode" != 160000 ] && [ -e "$f" ]; then printf "%s\0" "$f"; fi
      done | tarlist "$@"' _ "$w" "${EXCLUDES[@]}"
    case $STREAM_RC in 0|1) ;; *) die "tar of conflicted files failed in $w (exit $STREAM_RC)" ;; esac
    gzip -t "$dir/conflicted.tar.gz" || die "conflicted tarball of $w fails gzip -t"
    # shellcheck disable=SC2016  # the script runs on the pod
    cap "$SCRATCH/stages.batch" bash -c "$PODGITFN"'; set -o pipefail; w=$1; cd "$w" || exit 3
      git ls-files -u -z |
      while IFS= read -r -d "" e; do rest=${e%%$'"'"'\t'"'"'*}; mode=${rest%% *}; sha=${rest#* }; sha=${sha%% *}; if [ "$mode" != 160000 ]; then printf "%s\n" "$sha"; fi; done |
      git cat-file --batch' _ "$w"
    [ "$STREAM_RC" = 0 ] || die "could not read the conflict stage blobs in $w (exit $STREAM_RC)"
    perl -MArchive::Tar -e '
      local $/; open my $u,"<:raw",$ARGV[0] or die; my $ul=<$u>; open my $b,"<:raw",$ARGV[1] or die; my $bd=<$b>;
      my (%blob,$pos); $pos=0;
      while ($pos < length $bd) { my $nl=index($bd,"\n",$pos); last if $nl<0; my $hd=substr($bd,$pos,$nl-$pos);
        my ($sha,$type,$size)=split / /,$hd; die "missing blob $hd" if $type eq "missing" || !defined $size;
        $blob{$sha}=substr($bd,$nl+1,$size); $pos=$nl+1+$size+1; }
      my $t=Archive::Tar->new;
      for my $e (split /\0/,$ul) { next unless $e =~ /^(\d+) ([0-9a-f]+) (\d)\t(.*)$/s; my ($mode,$sha,$stg,$p)=($1,$2,$3,$4); next if $mode eq "160000";
        die "missing blob $sha" unless exists $blob{$sha}; $t->add_data("stage$stg/$p",$blob{$sha},{mode=>oct(substr($mode,-3))}); }
      $t->write($ARGV[2]) or die $t->error;' "$SCRATCH/unmerged.z" "$SCRATCH/stages.batch" "$SCRATCH/stages.tar" \
      || die "could not assemble the conflict stages of $w"
    gzip -c "$SCRATCH/stages.tar" > "$SCRATCH/stages.tar.gz"
    adopt "$SCRATCH/stages.tar.gz" "$dir/conflict-stages.tar.gz"
    local gl
    gl=$(perl -0777 -ne 'my %s; for (split /\0/){ next unless /^160000 [0-9a-f]+ \d\t(.*)$/s; $s{$1}=1 } print join(", ", sort keys %s)' < "$SCRATCH/unmerged.z")
    add_note "$notes" "CONFLICTED: $um unmerged path(s). conflicted.tar.gz holds the working-tree files (conflict markers intact); conflict-stages.tar.gz holds stage1/2/3 of every unmerged path; unmerged.z is the 'git ls-files -u -z' listing. Patches that hold only conflicts have nothing to apply; the restore helper skips them."
    if [ -n "$gl" ]; then add_note "$notes" "Conflicted submodule path(s) (gitlink, no blob to save; their index entries are rebuilt from unmerged.z): $gl"; fi
  fi

  if [ "$sf" -eq 1 ]; then
    local names=()
    while IFS= read -r -d '' nm; do names+=("$nm"); done < "$SCRATCH/state.names"
    stream_to "$dir/inprogress.tar.gz" tar -C "$gd" -czf - "${names[@]}"
    case $STREAM_RC in 0|1) ;; *) die "tar of in-progress state failed in $w (exit $STREAM_RC)" ;; esac
    gzip -t "$dir/inprogress.tar.gz" || die "in-progress tarball of $w fails gzip -t"
    add_note "$notes" "IN PROGRESS: inprogress.tar.gz holds the git-dir state files (${names[*]}). The commits MERGE_HEAD, CHERRY_PICK_HEAD, REVERT_HEAD, REBASE_HEAD and ORIG_HEAD name (every line) are in the repository bundle; their shas are in EXTRA-REVS.txt."
  fi

  if [ "$u" -gt 0 ]; then
    gfile "$SCRATCH/untracked.z" "$w" ls-files --others --exclude-standard -z
    while IFS= read -r -d '' p; do
      if excluded_hit "$p"; then note_excluded "untracked: $w: $p"; fi
    done < "$SCRATCH/untracked.z"
    # shellcheck disable=SC2016  # the script runs on the pod
    stream_to "$dir/untracked.tar.gz" bash -c "$PODGITFN"'; set -o pipefail; w=$1; shift; cd "$w" || exit 3
      git ls-files --others --exclude-standard -z | tarlist "$@"' _ "$w" "${EXCLUDES[@]}"
    case $STREAM_RC in 0|1) ;; *) die "tar of untracked files failed in $w (exit $STREAM_RC)" ;; esac
    gzip -t "$dir/untracked.tar.gz" || die "untracked tarball of $w fails gzip -t"
  fi

  if [ "$h" -gt 0 ]; then
    pl_lines "$SCRATCH/hidden.z" > "$SCRATCH/hidden.txt"
    adopt "$SCRATCH/hidden.txt" "$dir/hidden.txt"
    # skip-worktree / assume-unchanged files: invisible to status and diff, so tar them.
    # The class is spelled out: [a-z] depends on the pod's locale.
    # shellcheck disable=SC2016  # the script runs on the pod
    stream_to "$dir/hidden.tar.gz" bash -c "$PODGITFN"'; set -o pipefail; w=$1; shift; cd "$w" || exit 3
      git ls-files -v -z |
      while IFS= read -r -d "" e; do
        case $e in [abcdefghijklmnopqrstuvwxyzS]\ *) f=${e#? }; if [ -e "$f" ]; then printf "%s\0" "$f"; fi ;; esac
      done | tarlist "$@"' _ "$w" "${EXCLUDES[@]}"
    case $STREAM_RC in 0|1) ;; *) die "tar of skip-worktree files failed in $w (exit $STREAM_RC)" ;; esac
    gzip -t "$dir/hidden.tar.gz" || die "hidden-files tarball of $w fails gzip -t"
  fi

  if [ "$n" -gt 0 ]; then
    gfile "$SCRATCH/stash.list" "$w" stash list
    adopt "$SCRATCH/stash.list" "$dir/stash-list.txt"
    adopt "$SCRATCH/stash.shas" "$dir/stash-shas.txt"
    # Every entry is exported from its commits, so no git-version feature is needed:
    # stash-N.patch is the tracked change (base -> stash commit), stash-N.index.patch the
    # staged part (base -> index commit, second parent), stash-N.untracked.patch the
    # untracked part (third parent) as a new-files patch.
    i=0
    while [ "$i" -lt "$n" ]; do
      sha=$(sed -n "$((i + 1))p" "$SCRATCH/stash.shas")
      export_stash_commit "$dir" "stash-$i" "$w" "$sha"
      i=$((i + 1))
    done
  fi

  if [ -s "$SCRATCH/autostash.shas" ]; then
    # An autostash holds uncommitted work while a rebase or merge is stopped. It stays
    # named by the state file (restored with it); the patches make it recoverable even if
    # the operation is aborted.
    i=0
    while IFS= read -r sha; do
      [ -n "$sha" ] || continue
      export_stash_commit "$dir" "autostash-$i" "$w" "$sha"
      i=$((i + 1))
    done < <(sort -u "$SCRATCH/autostash.shas")
    add_note "$notes" "AUTOSTASH: uncommitted work is held by the autostash commit(s) named in the in-progress state; they are in the repository bundle, and autostash-N.patch/.index.patch/.untracked.patch export them. The restored state file lets 'git rebase --continue' / 'git merge --continue' re-apply them."
  fi

  if [ -s "$notes" ]; then adopt "$notes" "$dir/NOTE.txt"; fi
}

REPO_FIRST=""
# process_repo REPO KIND COMMON: the bundle and dirty state of one repository and its
# worktrees. KIND "orphan" is a deinitialised submodule's git dir: refs and bundle only.
process_repo() {
  local repo=$1 kind=${2:-repo} common=${3:-} name i wt
  ORPHAN=0
  EXTRA_FILE=$SCRATCH/extra.revs
  : > "$EXTRA_FILE"
  if [ "$kind" = orphan ]; then
    ORPHAN=1
    name=$(wtname "$repo")
    load_remotes "$repo"
    if [ "$LIVE_ONLY" = 1 ]; then collect_refs "$repo" "$name"; else bundle_refs "$repo" "$name" "$common"; fi
    ORPHAN=0
    return 0
  fi
  load_worktrees "$repo"
  load_remotes "$repo"
  REPO_FIRST=${WT_PATH[0]}
  name=$(wtname "$REPO_FIRST")
  i=0
  while [ "$i" -lt "${#WT_PATH[@]}" ]; do
    wt=${WT_PATH[$i]}
    if [ "${WT_BARE[$i]}" = 0 ] && [ "${WT_PRUN[$i]}" = 0 ]; then
      if [ "${WT_DET[$i]}" = 1 ] && [ -n "${WT_HEAD[$i]}" ]; then
        printf '%s\t%s\n' "${WT_HEAD[$i]}" "$wt:HEAD" >> "$EXTRA_FILE"
      fi
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
  # The bundle comes last: it needs the extra revs the worktrees contributed.
  if [ "$LIVE_ONLY" = 1 ]; then collect_refs "$repo" "$name"; else bundle_refs "$repo" "$name" "$common"; fi
}

# process_all: per-repo processing of what discover found.
process_all() {
  local repo kind common
  while IFS=$'\t' read -r repo kind common; do
    [ -n "$repo" ] || continue
    echo "$common" >> "$SCRATCH/clone.list"
    process_repo "$repo" "$kind" "$common"
  done < "$SCRATCH/clones.tsv"
}

# scan_all: discovery plus per-repo processing (archive) or counting only (LIVE_ONLY).
scan_all() { discover; process_all; }

# space_preflight PRESENT_PATHS: the bundles hold complete histories, so compare what the
# pod holds (git dirs plus the home paths) with the free space at DEST before streaming.
space_preflight() {
  local present=$1 repo kind common kb need free total=0 p args=()
  while IFS=$'\t' read -r repo kind common; do
    [ -n "$repo" ] || continue
    cap "$SCRATCH/du" du -sk "$common"
    kb=$(cut -f1 "$SCRATCH/du" | head -1)
    total=$((total + ${kb:-0}))
  done < "$SCRATCH/clones.tsv"
  for p in $present; do args+=("$POD_HOME/$p"); done
  if [ ${#args[@]} -gt 0 ]; then
    cap "$SCRATCH/du" du -sk "${args[@]}"
    while IFS=$'\t' read -r kb _; do total=$((total + ${kb:-0})); done < "$SCRATCH/du"
  fi
  need=$((total * 12 / 10))
  free=$("$DF" -Pk "$DEST" | awk 'NR == 2 { print $4 }')
  echo "space check: the pod holds about $total KiB to archive (x1.2 = $need KiB needed); $free KiB free at $DEST"
  if [ "${free:-0}" -lt "$need" ]; then
    if [ "$SKIP_SPACE_CHECK" = 1 ]; then
      echo "WARNING: not enough free space ($free KiB < $need KiB); continuing because of --skip-space-check" >&2
    else
      die "not enough free space at $DEST: $free KiB free, about $need KiB needed (pod data $total KiB x 1.2). Free some space, point --dest elsewhere, or pass --skip-space-check."
    fi
  fi
}

# claude_exclusions: record in EXCLUDED.txt what the tarball leaves out of ~/.claude, read
# on the pod with find (read-only): credentials one line each, cache directories one line
# per directory.
claude_exclusions() {
  local base=$POD_HOME/.claude c n p prune=() creds=() rel
  for c in $CLAUDE_CACHES; do
    case $c in *\**) ;; *) prune+=(-o -path "$POD_HOME/$c") ;; esac
  done
  # cache directories (and node_modules) first: pruned, listed once
  cap "$SCRATCH/cl.caches" find -H "$base" -type d \( -name node_modules ${prune[@]+"${prune[@]}"} \) -prune -print0
  case $STREAM_RC in 0|1) ;; *) die "find (.claude caches) failed on the pod (exit $STREAM_RC)" ;; esac
  while IFS= read -r -d '' p; do note_excluded ".claude excluded (cache dir): ${p#"$POD_HOME"/}"; done < "$SCRATCH/cl.caches"
  cap "$SCRATCH/cl.locks" find -H "$base" -type f -path "$base/*.lock" -print0
  case $STREAM_RC in 0|1) ;; *) die "find (.claude lock files) failed on the pod (exit $STREAM_RC)" ;; esac
  while IFS= read -r -d '' p; do note_excluded ".claude excluded (lock file): ${p#"$POD_HOME"/}"; done < "$SCRATCH/cl.locks"
  # credentials, not looking inside the caches
  set -f
  for n in $CRED_NAMES; do
    case $n in */*) creds+=(-o -path "*/$n") ;; *) creds+=(-o -name "$n") ;; esac
  done
  for n in $CLAUDE_CREDS; do creds+=(-o -path "$POD_HOME/$n"); done
  set +f
  cap "$SCRATCH/cl.creds" find -H "$base" \( -type d \( -name node_modules ${prune[@]+"${prune[@]}"} \) -prune \) -o \( -false "${creds[@]}" \) -print0 -prune
  case $STREAM_RC in 0|1) ;; *) die "find (.claude credentials) failed on the pod (exit $STREAM_RC)" ;; esac
  while IFS= read -r -d '' p; do
    rel=${p#"$POD_HOME"/}
    note_excluded ".claude excluded (credential): $rel"
  done < "$SCRATCH/cl.creds"
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
  rm -f "$DEST/LOCAL-ONLY.txt" "$DEST/EXTRA-REVS.txt" "$DEST/BUNDLES.txt"
  rm -f "$DEST/REMOTE.sha256" "$DEST/SKIPPED.txt" "$DEST/DETACHED.txt" "$DEST/DIRTY.txt" \
        "$DEST/EXCLUDED.txt" "$DEST/CLONES.txt" "$DEST/ACCEPTED.txt" "$DEST/MANIFEST.sha256" "$DEST/secure-agent-pod-home.tar.gz"
  mkdir -p "$DEST/bundles"
  : > "$DEST/REMOTE.sha256"; : > "$DEST/SKIPPED.txt"; : > "$DEST/DETACHED.txt"
  : > "$DEST/DIRTY.txt"; : > "$DEST/EXCLUDED.txt"; : > "$DEST/CLONES.txt"
  : > "$DEST/LOCAL-ONLY.txt"; : > "$DEST/EXTRA-REVS.txt"; : > "$DEST/BUNDLES.txt"
  : > "$SCRATCH/clone.list"

  EXCLUDES=()
  local n
  set -f
  for n in $CRED_NAMES; do EXCLUDES+=("--exclude=$n"); done
  set +f
  EXCLUDES+=("--exclude=node_modules")
  # The home tarball also drops the ~/.claude credentials and caches (not applied to clones).
  HOME_EXCLUDES=("${EXCLUDES[@]}")
  set -f
  for n in $CLAUDE_CREDS $CLAUDE_CACHES; do HOME_EXCLUDES+=("--exclude=$n"); done
  set +f

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

  # Transcripts under ~/.claude/projects are only complete once no session writes them.
  case " $present " in
    *" .claude "*)
      # shellcheck disable=SC2016  # the script runs on the pod
      cap "$SCRATCH/have" sh -c 'if [ -e "$1" ]; then echo yes; else echo no; fi' _ "$POD_HOME/.claude/projects"
      [ "$STREAM_RC" = 0 ] || die "could not probe .claude/projects on the pod"
      if [ "$(cat "$SCRATCH/have")" = no ]; then
        echo ".claude/projects" >> "$DEST/SKIPPED.txt"; echo "WARNING: .claude/projects not found on the pod" >&2
      fi
      claude_exclusions ;;
  esac

  local tarflags=() tv
  cap "$SCRATCH/tarv" tar --version || true
  tv=$(cat "$SCRATCH/tarv")
  case $tv in *"GNU tar"*) tarflags+=("--warning=no-file-changed") ;; esac

  discover
  space_preflight "$present"
  echo "archiving home tree from $POD_HOME ..."
  # shellcheck disable=SC2086  # $present is a space-separated list of simple paths
  stream_to "$DEST/secure-agent-pod-home.tar.gz" tar -C "$POD_HOME" -czf - ${tarflags[@]+"${tarflags[@]}"} "${HOME_EXCLUDES[@]}" $present
  case $STREAM_RC in
    0) ;;
    1) echo "WARNING: tar reported files changing while it read them (exit 1); archive kept" >&2 ;;
    *) die "tar failed on the pod with exit $STREAM_RC" ;;
  esac
  gzip -t "$DEST/secure-agent-pod-home.tar.gz" || die "tarball fails gzip -t"
  tar -tzf "$DEST/secure-agent-pod-home.tar.gz" >/dev/null || die "tarball cannot be listed"

  process_all
  sort -u "$SCRATCH/clone.list" > "$DEST/CLONES.txt"
  echo "bundles: $TOTAL_BUNDLE_B bytes in total (pod git dirs: $TOTAL_POD_KB KiB); $(grep -c . "$DEST/LOCAL-ONLY.txt" || true) ref(s) hold commits no network remote has (LOCAL-ONLY.txt)"
  if [ "$ACCEPT_UNREADABLE" = 1 ]; then
    grep -E '^(unreadable|not a usable)' "$DEST/SKIPPED.txt" > "$DEST/ACCEPTED.txt" || true
    echo "NOTE: --accept-unreadable: $(wc -l < "$DEST/ACCEPTED.txt" | tr -d ' ') unreadable or unusable path(s) accepted; see ACCEPTED.txt" >&2
  fi

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
    if printf '%s\n' "$listing" | grep -q '^\(\./\)\{0,1\}\.claude/projects/'; then
      echo "INFO .claude/projects is in the tarball (session transcripts; complete only if no session ran during the archive)"
    else
      echo "WARN .claude/projects is not in the tarball (no session transcripts archived)"
    fi
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
  if [ -f "$DEST/SKIPPED.txt" ]; then
    if grep -Eq '^(pruned|prunable)' "$DEST/SKIPPED.txt"; then
      echo "WARN regenerable caches were pruned (not archived); see SKIPPED.txt"
    fi
    if grep -Eq '^(unreadable|not a usable)' "$DEST/SKIPPED.txt"; then
      if [ -s "$DEST/ACCEPTED.txt" ]; then
        echo "WARN unreadable or unusable paths, accepted by the operator (--accept-unreadable):"; sed 's/^/     /' "$DEST/ACCEPTED.txt"
      else
        fail "no unreadable or unusable paths (SKIPPED.txt):"; grep -E '^(unreadable|not a usable)' "$DEST/SKIPPED.txt" | sed 's/^/     /'
      fi
    else
      pass "no unreadable or unusable paths"
    fi
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
    local dline dpath ddir dm du dn dh dum dsf bad="" k
    while IFS= read -r dline; do
      [ -n "$dline" ] || continue
      dpath=${dline%% modified=*}
      dm=$(sed -n 's/.* modified=\([0-9]*\) .*/\1/p' <<<"$dline")
      du=$(sed -n 's/.* untracked=\([0-9]*\) .*/\1/p' <<<"$dline")
      dn=$(sed -n 's/.* stash=\([0-9]*\) .*/\1/p' <<<"$dline")
      dh=$(sed -n 's/.* hidden=\([0-9]*\).*/\1/p' <<<"$dline")
      dum=$(sed -n 's/.* unmerged=\([0-9]*\).*/\1/p' <<<"$dline")
      dsf=$(sed -n 's/.* state=\([0-9]*\)$/\1/p' <<<"$dline")
      ddir=$(dirty_dir "$dpath")
      if [ ! -d "$ddir" ] || [ -z "$(ls -A "$ddir" 2>/dev/null)" ]; then bad="$bad $dpath(missing)"; continue; fi
      [ -f "$ddir/status.txt" ] || bad="$bad $dpath(status.txt)"
      if [ "${dm:-0}" -gt 0 ]; then
        [ -f "$ddir/staged.patch" ] && [ -f "$ddir/tracked.patch" ] || bad="$bad $dpath(patches)"
      fi
      if [ "${du:-0}" -gt 0 ]; then [ -f "$ddir/untracked.tar.gz" ] || bad="$bad $dpath(untracked.tar.gz)"; fi
      if [ "${dh:-0}" -gt 0 ]; then [ -f "$ddir/hidden.tar.gz" ] && [ -f "$ddir/hidden.txt" ] || bad="$bad $dpath(hidden)"; fi
      if [ "${dum:-0}" -gt 0 ]; then
        [ -f "$ddir/conflicted.tar.gz" ] && [ -f "$ddir/conflict-stages.tar.gz" ] && [ -f "$ddir/unmerged.z" ] || bad="$bad $dpath(conflicted)"
      fi
      if [ "${dsf:-0}" -gt 0 ]; then [ -f "$ddir/inprogress.tar.gz" ] || bad="$bad $dpath(inprogress.tar.gz)"; fi
      k=0
      while [ "$k" -lt "${dn:-0}" ]; do
        [ -f "$ddir/stash-$k.patch" ] && [ -f "$ddir/stash-$k.index.patch" ] || bad="$bad $dpath(stash-$k)"
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
      PP="${wf#"$DEST"/}" awk '{ l=$0; sub(/^[0-9a-f]+  /, "", l); if (l == ENVIRON["PP"]) f=1 } END { exit f ? 0 : 1 }' "$DEST/REMOTE.sha256" \
        || unlisted="$unlisted ${wf#"$DEST"/}"
      case $wf in
        */untracked.tar.gz|*/hidden.tar.gz|*/conflicted.tar.gz|*/conflict-stages.tar.gz|*/inprogress.tar.gz)
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

  if [ -d "$DEST/ignored" ]; then
    local ig
    echo "WARN ignored files are listed under ignored/, not saved (outside interviews/ and orgs/ they exist only on the pod):"
    for ig in "$DEST"/ignored/*.txt; do
      [ -e "$ig" ] || continue
      echo "     $(wc -l < "$ig" | tr -d ' ') ignored path(s): $(basename "$ig")"
    done
  fi

  if [ -s "$DEST/LOCAL-ONLY.txt" ]; then
    echo "INFO $(grep -c . "$DEST/LOCAL-ONLY.txt") ref(s) hold commits no network remote has (LOCAL-ONLY.txt); the bundles carry all refs regardless"
  fi
  # One self-contained bundle per repository: no prerequisites, so `git bundle verify`
  # must pass in an empty repository.
  local scratch common bf
  scratch=$(mktemp -d)
  git init -q "$scratch"
  if [ -f "$DEST/CLONES.txt" ] && [ -f "$DEST/BUNDLES.txt" ]; then
    while IFS= read -r common; do
      [ -n "$common" ] || continue
      bf=$(C="$common" awk -F'\t' '$1 == ENVIRON["C"] { print $2; exit }' "$DEST/BUNDLES.txt")
      if [ -z "$bf" ]; then
        fail "bundle recorded for $common"
      elif [ "$bf" = "-" ]; then
        pass "no refs to bundle in $common"
      elif [ ! -f "$DEST/bundles/$bf" ]; then
        fail "bundle present: $bf"
      elif ! bundle_pack_ok "$DEST/bundles/$bf"; then
        fail "bundle pack checksum: $bf"
      elif git -C "$scratch" bundle verify "$DEST/bundles/$bf" >/dev/null 2>&1; then
        pass "bundle is self-contained and verifies: $bf"
      else
        fail "bundle verifies in an empty repository: $bf"
      fi
    done < "$DEST/CLONES.txt"
  else
    fail "CLONES.txt and BUNDLES.txt present"
  fi
  # An autostash named by a state file holds uncommitted work: its commit must be in the bundle.
  local wd2 bfile ip sha2 missing2=""
  if [ -d "$DEST/worktrees" ]; then
    for wd2 in "$DEST"/worktrees/*/; do
      [ -f "$wd2/inprogress.tar.gz" ] || continue
      ip=$(mktemp -d)
      tar -xzf "$wd2/inprogress.tar.gz" -C "$ip" 2>/dev/null || true
      bfile=$(sed -n 's/^bundle=//p' "$wd2/meta.txt" 2>/dev/null)
      for sha2 in $( { cat "$ip/MERGE_AUTOSTASH" "$ip/rebase-merge/autostash" "$ip/rebase-apply/autostash"; } 2>/dev/null | grep -aEo '[0-9a-f]{40}'); do
        if ! grep -q "$sha2" "$DEST/EXTRA-REVS.txt" 2>/dev/null; then missing2="$missing2 $sha2"; continue; fi
        git -C "$scratch" bundle unbundle "$DEST/bundles/$bfile" >/dev/null 2>&1 || true
        git -C "$scratch" cat-file -e "$sha2^{commit}" 2>/dev/null || missing2="$missing2 $sha2"
      done
      rm -rf "$ip"
    done
  fi
  if [ -z "$missing2" ]; then pass "autostash commits are in the bundles"; else fail "autostash commits are in the bundles (missing:$missing2)"; fi
  rm -rf "$scratch"

  if [ "$LIVE" = 1 ]; then
    # Re-scan the pod, read-only, and compare with what the archive recorded.
    LIVE_ONLY=1
    : > "$SCRATCH/live.dirty"; : > "$SCRATCH/live.skipped"; : > "$SCRATCH/clone.list"
    mkdir -p "$SCRATCH/live.refs"
    scan_all
    sort -u "$SCRATCH/clone.list" > "$SCRATCH/live.clones"
    LIVE_ONLY=0
    if [ -f "$DEST/CLONES.txt" ] && diff <(sort -u "$DEST/CLONES.txt") "$SCRATCH/live.clones" >/dev/null; then
      pass "live clone list matches the archive"
    else
      fail "live clone list matches the archive (diff: $(diff <(sort -u "$DEST/CLONES.txt" 2>/dev/null) "$SCRATCH/live.clones" | tr '\n' ';'))"
    fi
    mkdir -p "$SCRATCH/arch.refs"
    if [ -d "$DEST/refs" ]; then cp "$DEST"/refs/*.txt "$SCRATCH/arch.refs/" 2>/dev/null || true; fi
    if diff -r "$SCRATCH/arch.refs" "$SCRATCH/live.refs" >/dev/null; then
      pass "live refs match the archive"
    else
      fail "live refs match the archive (diff: $(diff -r "$SCRATCH/arch.refs" "$SCRATCH/live.refs" | grep -E '^(Only|diff|[<>])' | head -6 | tr '\n' ';'))"
    fi
    local skp='^(pruned|unreadable|not a usable|prunable)'
    if diff <(grep -E "$skp" "$DEST/SKIPPED.txt" 2>/dev/null | sort) <(grep -E "$skp" "$SCRATCH/live.skipped" | sort) >/dev/null; then
      pass "live skipped paths match the archive"
    else
      fail "live skipped paths match the archive"
    fi
    if diff <(sort "$DEST/DIRTY.txt") <(sort "$SCRATCH/live.dirty") >/dev/null; then
      pass "live dirty state matches the archive"
    else
      fail "live dirty state matches the archive (diff: $(diff <(sort "$DEST/DIRTY.txt") <(sort "$SCRATCH/live.dirty") | tr '\n' ';'))"
    fi
  fi

  [ "$fail" = 0 ] || exit 1
}

# restore_worktree: rebuild one worktree's saved state in a fresh checkout. Runs
# purely locally against the archive; it never contacts the pod.
#   restore-worktree --dest ARCHIVE --worktree ORIGINAL_PATH --target DIR
# DIR is an empty directory or a fresh clone of anything (it becomes a repository).
cmd_restore_worktree() {
  [ -n "$RW_PATH" ] && [ -n "$RW_TARGET" ] || usage
  local dir meta bundle head headref t ref sha cur x f p line
  dir=$(dirty_dir "$RW_PATH")
  meta=$dir/meta.txt
  [ -f "$meta" ] || die "no saved state for $RW_PATH in $DEST (not listed in DIRTY.txt?). For a clean repository: git fetch <bundle> 'refs/*:refs/*'"
  bundle=$(sed -n 's/^bundle=//p' "$meta"); head=$(sed -n 's/^head=//p' "$meta"); headref=$(sed -n 's/^headref=//p' "$meta")
  mkdir -p "$RW_TARGET"
  t=$(cd "$RW_TARGET" && pwd -P)
  [ -d "$t/.git" ] || git init -q "$t"
  if [ ! -f "$DEST/bundles/$bundle" ]; then
    # No bundle means the repository had no refs: only an unborn HEAD can be restored.
    [ "$head" = unborn ] || die "bundle $bundle is missing from $DEST"
    case $headref in refs/heads/*) git -C "$t" symbolic-ref HEAD "$headref" ;; esac
  else
    # 1. every ref and object of the repository, from the bundle alone
    git -C "$t" fetch -q "$DEST/bundles/$bundle" '+refs/*:refs/archive/*' '+HEAD:refs/archive/HEAD' 2>/dev/null \
      || git -C "$t" fetch -q "$DEST/bundles/$bundle" '+refs/*:refs/archive/*'
    # park the checkout on a throwaway ref, then recreate every ref under its own name
    if [ "$head" != unborn ]; then git -C "$t" checkout -q -f --detach "$head"; fi
    while read -r sha ref; do
      case $ref in refs/archive/HEAD|"") continue ;; esac
      git -C "$t" update-ref --create-reflog "refs/${ref#refs/archive/}" "$sha"
    done < <(git -C "$t" for-each-ref --format='%(objectname) %(refname)' refs/archive/)
    while read -r ref; do git -C "$t" update-ref -d "$ref"; done < <(git -C "$t" for-each-ref --format='%(refname)' refs/archive/)
    # stash entries: replay oldest first, so stash@{0..n-1} come back in order with their messages
    if [ -f "$dir/stash-shas.txt" ] && [ -f "$dir/stash-list.txt" ]; then
      git -C "$t" update-ref -d refs/stash 2>/dev/null || true
      local total k msg
      total=$(grep -c . "$dir/stash-shas.txt" || true)
      k=$((total - 1))
      while [ "$k" -ge 0 ]; do
        sha=$(sed -n "$((k + 1))p" "$dir/stash-shas.txt")
        msg=$(sed -n "$((k + 1))p" "$dir/stash-list.txt"); msg=${msg#*: }
        git -C "$t" stash store -m "$msg" "$sha"
        k=$((k - 1))
      done
    fi
  fi
  # 2. the checked-out state
  case $headref in
    refs/heads/*) [ "$head" = unborn ] || git -C "$t" checkout -q -f "${headref#refs/heads/}" 2>/dev/null || git -C "$t" checkout -q -f -B "${headref#refs/heads/}" "$head" ;;
    *) [ "$head" = unborn ] || git -C "$t" checkout -q -f --detach "$head" ;;
  esac
  # 3. index and working tree: staged changes, then unstaged ones (patches holding only
  #    conflicts carry nothing to apply and are skipped)
  if [ -f "$dir/staged.patch" ] && grep -aq '^diff --git ' "$dir/staged.patch"; then
    git -C "$t" apply --index "$dir/staged.patch" || die "staged.patch does not apply"
  fi
  if [ -f "$dir/tracked.patch" ] && grep -aq '^diff --git ' "$dir/tracked.patch"; then
    git -C "$t" apply "$dir/tracked.patch" || die "tracked.patch does not apply"
  fi
  for x in untracked hidden conflicted; do
    if [ -f "$dir/$x.tar.gz" ]; then tar -xzf "$dir/$x.tar.gz" -C "$t"; fi
  done
  # skip-worktree / assume-unchanged bits: the files came back with the tarball, so
  # re-hide them (hidden.txt lines are "<ls-files -v tag> <path>").
  if [ -f "$dir/hidden.txt" ]; then
    while IFS= read -r line; do
      f=${line#? }
      case ${line%% *} in
        S) git -C "$t" update-index --skip-worktree -- "$f" ;;
        [a-z]) git -C "$t" update-index --assume-unchanged -- "$f" ;;
      esac
    done < "$dir/hidden.txt"
  fi
  # 4. an operation in progress: its state files go back into the git dir
  if [ -f "$dir/inprogress.tar.gz" ]; then
    tar -xzf "$dir/inprogress.tar.gz" -C "$(git -C "$t" rev-parse --absolute-git-dir)"
  fi
  # 5. unmerged paths: drop the stage-0 entry the checkout made, store the stage blobs,
  #    then re-add stages 1/2/3 (gitlink entries carry no blob).
  if [ -f "$dir/unmerged.z" ]; then
    cur=$(mktemp -d)
    perl -0777 -ne 'my %s; for (split /\0/){ next unless /\t(.*)$/s; $s{$1}=1 } print "$_\0" for sort keys %s' "$dir/unmerged.z" \
      | git -C "$t" update-index --force-remove -z --stdin
    if [ -f "$dir/conflict-stages.tar.gz" ]; then
      tar -xzf "$dir/conflict-stages.tar.gz" -C "$cur"
      while IFS= read -r -d '' f; do git -C "$t" hash-object -w --no-filters "$f" >/dev/null; done < <(find "$cur" -type f -print0)
    fi
    git -C "$t" update-index -z --index-info < "$dir/unmerged.z"
    rm -rf "$cur"
  fi
  p=$(git -C "$t" status --porcelain=v1 | wc -l | tr -d ' ')
  echo "restored $RW_PATH into $t (HEAD $head; $p status line(s))"
  [ ! -f "$dir/NOTE.txt" ] || sed 's/^/  note: /' "$dir/NOTE.txt"
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
RW_PATH=""
RW_TARGET=""
LIVE=0
SKIP_SPACE_CHECK=0
ACCEPT_UNREADABLE=0
while [ $# -gt 0 ]; do
  case $1 in
    --dest) [ $# -ge 2 ] || usage; DEST=$2; shift 2 ;;
    --session-ended-confirmed) CONFIRMED=1; shift ;;
    --live) LIVE=1; shift ;;
    --skip-space-check) SKIP_SPACE_CHECK=1; shift ;;
    --worktree) [ $# -ge 2 ] || usage; RW_PATH=$2; shift 2 ;;
    --target) [ $# -ge 2 ] || usage; RW_TARGET=$2; shift 2 ;;
    --accept-unreadable) ACCEPT_UNREADABLE=1; shift ;;
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
  restore-worktree) cmd_restore_worktree ;;
  *) usage ;;
esac
