#!/usr/bin/env bash
# phase5-soak-daily.sh — Phase 5 of vk-local OOM remediation: daily soak entry.
#
# Cron: 0 8 * * *  (daily at 08:00 UTC)
# Anchor: 2026-05-03 = Soak Day 1 (already filled by gh#156 PR #205).
# Window: Days 2–14 = 2026-05-04 → 2026-05-16 inclusive.
#
# Behavior — purely date-driven:
#  - Pre-window (today < 2026-05-04): no-op, log "pre-window".
#  - In-window (Days 2–14, 2026-05-04 → 2026-05-16): append the Day-N row
#    to the Soak Log table on a follow-up branch
#    (vk/phase-5-soak-data-collection) branched off origin/main, push,
#    and open a PR if none is open. Subsequent fires append commits to
#    the same branch and same PR.
#  - Post-window (today > 2026-05-16): switch to cleanup-nag mode. One
#    open `vk-ready` GitHub issue is the nag — first fire creates it;
#    every subsequent fire adds a one-line comment dated today. The
#    issue stays open until the operator deletes the cron line and the
#    script (and closes the issue).
#
# Note: branch existence is no longer the cleanup trigger. PR #205 merged
# on Day 1 (2026-05-03) and the original branch is gone, but the soak
# itself runs Days 2–14. The script targets a fresh branch off main for
# data collection so the original PR's lifecycle is decoupled.
#
# REMOVE after Day 14 (2026-05-16) and once the cleanup-nag issue is open:
#   1. rm "$HOME/.willikins-agent/phase5-soak-daily.sh"
#   2. delete the matching line in "$HOME/.crontab" (grep phase5-soak-daily)
#   3. close the "cleanup: remove Phase 5 soak …" issue on derio-net/frank

set -o pipefail
# Bash strict mode is intentionally LOOSE here: ~/.bashrc references unbound
# vars (e.g. _TMUX_LAST_PWD) on first source, and supercronic invokes us as a
# non-interactive shell where that file isn't sourced anyway. We rely on
# explicit error checks inside the helpers below, not `set -u`/`set -e`.

REPO_SLUG="derio-net/frank"
SOAK_BRANCH="${SOAK_BRANCH_OVERRIDE:-vk/phase-5-soak-data-collection}"
BASE_BRANCH="main"
PLAN_PATH="docs/superpowers/plans/2026-04-30--agents--vk-local-oom-remediation.md"
CLONE_DIR="$HOME/.willikins-agent/phase5-soak-clone"
LOG="$HOME/.willikins-agent/phase5-soak.log"
SOAK_START="2026-05-03"   # Day 1
SOAK_LAST="2026-05-16"    # Day 14
NS="secure-agent-pod"
CONTAINER="vk-local"
VMSINGLE_DEPLOY="deploy/vmsingle-victoria-metrics-victoria-metrics-k8s-stack"
VMSINGLE_URL="http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack:8428"

ts_iso() { date -u +%FT%TZ; }
log() { echo "[$(ts_iso)] $*" >> "$LOG"; }

mkdir -p "$(dirname "$LOG")"

# --- Repo helpers -----------------------------------------------------------
ensure_clone() {
  if [[ ! -d "$CLONE_DIR/.git" ]]; then
    log "cloning $REPO_SLUG into $CLONE_DIR"
    git clone --quiet "https://github.com/${REPO_SLUG}.git" "$CLONE_DIR"
  fi
}

# --- Cleanup-reminder mode: one open issue, comments after that -------------
#
# Stable title — used by `gh issue list --search` to find the existing issue
# on subsequent fires. Do not include a date in the title, or each fire would
# look like a new issue to the search.
CLEANUP_TITLE="cleanup: remove Phase 5 soak supercronic entry + script"

find_open_cleanup_issue() {
  # Returns the issue number on stdout if exactly one open issue matches, else
  # empty. The `in:title` qualifier scopes the search to titles only so a
  # comment containing the same phrase elsewhere doesn't false-match.
  gh issue list --repo "$REPO_SLUG" --state open --label vk-ready \
    --search "in:title \"${CLEANUP_TITLE}\"" \
    --json number,title --jq '.[].number' 2>>"$LOG" | head -1
}

nag_for_cleanup() {
  local today; today=$(date -u +%F)
  local existing; existing=$(find_open_cleanup_issue)

  if [[ -n "$existing" ]]; then
    local note="Still firing — ${today}. Cron line + script not yet removed."
    log "cleanup nag: existing issue #${existing} found — adding comment"
    if [[ -n "${DRY_RUN:-}" ]]; then
      log "  DRY_RUN: would gh issue comment ${existing} --body \"${note}\""
      return 0
    fi
    gh issue comment "$existing" --repo "$REPO_SLUG" --body "$note" >> "$LOG" 2>&1 \
      || log "  gh issue comment failed (non-fatal)"
    return 0
  fi

  log "cleanup nag: no open issue — creating one"
  local body
  body=$(cat <<EOF
**This issue is the cleanup nag for the Phase 5 soak script. While it stays
open, the script will add a one-line comment dated each day it fires.**

The Phase 5 vk-local OOM soak script is still firing on the secure-agent-pod
even though the soak window has closed (Day 14 was 2026-05-16). The
script's job is done; it is now just nagging.

To make it stop, on the secure-agent-pod (PVC home \`/home/claude\`):

1. Remove the cron entry from \`\$HOME/.crontab\`:
   \`\`\`bash
   sed -i '/phase5-soak-daily/d' /home/claude/.crontab
   # supercronic auto-reloads on file change — no restart needed.
   \`\`\`
2. Delete the script + supporting files:
   \`\`\`bash
   rm -f /home/claude/.willikins-agent/phase5-soak-daily.sh
   rm -rf /home/claude/.willikins-agent/phase5-soak-clone
   # keep phase5-soak.log if you want the audit trail.
   \`\`\`
3. Close this issue.

If the soak window needs to be extended for a few extra days, edit
\`SOAK_LAST\` in the script (and the cron line is fine as-is) — the
script will resume soak mode automatically on its next fire, and the
daily comments here will stop.

---

Generated by \`/home/claude/.willikins-agent/phase5-soak-daily.sh\` on
$(ts_iso). Plan: \`${PLAN_PATH}\`. Anchor PR: derio-net/frank#205.
EOF
)
  local dry=()
  [[ -n "${DRY_RUN:-}" ]] && dry=(--dry-run) && log "  DRY_RUN: not actually creating an issue"
  if ! command -v vk >/dev/null; then
    log "  vk CLI not found; falling back to gh issue create"
    if [[ -n "${DRY_RUN:-}" ]]; then
      log "  (would gh issue create --repo $REPO_SLUG --title \"$CLEANUP_TITLE\")"
      return 0
    fi
    printf '%s\n' "$body" | gh issue create --repo "$REPO_SLUG" \
      --title "$CLEANUP_TITLE" --body-file - --label vk-ready >> "$LOG" 2>&1 \
      || log "  gh issue create failed (non-fatal)"
    return 0
  fi
  printf '%s\n' "$body" | vk issue create - \
    --repo "$REPO_SLUG" \
    --title "$CLEANUP_TITLE" \
    --label vk-ready \
    --skill "superpowers:using-superpowers" \
    "${dry[@]}" >> "$LOG" 2>&1 \
    || log "  vk issue create failed (non-fatal)"
}

# --- Soak mode: query metrics + append the Day-N row ------------------------
soak_today() {
  local today
  if [[ -n "${OVERRIDE_DATE:-}" ]]; then
    today="$OVERRIDE_DATE"
    log "OVERRIDE_DATE=$today (testing/backfill)"
  else
    today=$(date -u +%F)
  fi

  # Window guard
  if [[ "$today" < "2026-05-04" ]]; then
    log "$today: pre-window (Day 1 already filled by PR #205); skipping"
    return 0
  fi
  if [[ "$today" > "$SOAK_LAST" ]]; then
    log "$today: post-window (Day 14 closed $SOAK_LAST); skipping"
    return 0
  fi

  local day=$(( ( $(date -u -d "$today" +%s) - $(date -u -d "$SOAK_START" +%s) ) / 86400 + 1 ))
  log "Day $day ($today): collecting metrics"

  # restartCount + pod identity
  local pod
  pod=$(kubectl -n "$NS" get pod -l app=secure-agent-pod \
    -o jsonpath='{.items[0].metadata.name}' 2>>"$LOG")
  local rc
  rc=$(kubectl -n "$NS" get pod -l app=secure-agent-pod \
    -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="'"$CONTAINER"'")].restartCount}' 2>>"$LOG")
  local last_reason
  last_reason=$(kubectl -n "$NS" get pod -l app=secure-agent-pod \
    -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="'"$CONTAINER"'")].lastState.terminated.reason}' 2>>"$LOG")
  rc=${rc:-0}

  # vmsingle queries (24 h windows)
  vm_query() {
    kubectl -n monitoring exec "$VMSINGLE_DEPLOY" -- \
      wget -qO- "${VMSINGLE_URL}/api/v1/query?query=$1" 2>>"$LOG"
  }
  local p99_json q_json oom_json
  p99_json=$(vm_query 'max(quantile_over_time(0.99,container_memory_working_set_bytes%7Bnamespace%3D%22secure-agent-pod%22%2Ccontainer%3D%22vk-local%22%2Cmetrics_path%3D%22%2Fmetrics%2Fcadvisor%22%7D%5B1d%5D))')
  q_json=$(vm_query 'max(max_over_time(vibekanban_queued_executions%5B1d%5D))')
  oom_json=$(vm_query 'sum(kube_pod_container_status_restarts_total%7Bnamespace%3D%22secure-agent-pod%22%2Ccontainer%3D%22vk-local%22%7D)')

  # Parse + format
  local row
  row=$(python3 - "$day" "$today" "$rc" "$last_reason" "$pod" \
    "$p99_json" "$q_json" "$oom_json" <<'PY'
import json, sys
day, today, rc, last_reason, pod, p99j, qj, oomj = sys.argv[1:9]
def scalar(j):
    try:
        d = json.loads(j)
        r = d["data"]["result"]
        return r[0]["value"][1] if r else None
    except Exception:
        return None
p99 = scalar(p99j); q = scalar(qj); oom = scalar(oomj)

if p99 is None:
    p99_fmt = "_no series — investigate_"
else:
    p99_fmt = f"{float(p99)/1024**3:.2f} GiB"
q_fmt = q if q is not None else "_no series_"
oom_fmt = oom if oom is not None else "_no series_"

note_bits = []
if last_reason:
    note_bits.append(f"lastReason={last_reason}")
note_bits.append(f"pod={pod}")
note = "; ".join(note_bits)

print(f"| {day} | {today} | {rc} | {oom_fmt} | {p99_fmt} | {q_fmt} | {note} |")
PY
  )
  log "Day $day row: $row"

  # Apply to plan on the soak branch in the dedicated clone.
  #
  # Branch-state decision: an open PR with `--head $SOAK_BRANCH` is the
  # signal that previous fires' commits are still un-merged and we should
  # append to that branch. Without an open PR we treat the branch as
  # post-merge — its commits are already on main (possibly via squash, so
  # SHAs differ but content is identical) — and we reset it to
  # origin/main so today's commit lands on a clean base. Without this
  # reset, a stale branch ref would replay already-merged rows on top of
  # main and the next push would CONFLICT with itself.
  ensure_clone
  cd "$CLONE_DIR"
  git fetch --quiet --prune origin
  local has_open_pr
  has_open_pr=$(gh pr list --repo "$REPO_SLUG" --state open --head "$SOAK_BRANCH" \
    --json number --jq '.[].number' 2>>"$LOG" | head -1)
  local branch_on_origin
  branch_on_origin=$(git ls-remote --heads origin "$SOAK_BRANCH" | head -1)

  if [[ -n "$has_open_pr" && -n "$branch_on_origin" ]]; then
    log "  open PR #${has_open_pr} for $SOAK_BRANCH — appending to existing branch"
    git checkout --quiet -B "$SOAK_BRANCH" "origin/$SOAK_BRANCH"
  else
    if [[ -n "$branch_on_origin" && -z "$has_open_pr" ]]; then
      log "  $SOAK_BRANCH on origin but no open PR — assuming post-merge; resetting to origin/$BASE_BRANCH"
    else
      log "  $SOAK_BRANCH not on origin — branching from origin/$BASE_BRANCH"
    fi
    git checkout --quiet -B "$SOAK_BRANCH" "origin/$BASE_BRANCH"
  fi

  python3 - "$PLAN_PATH" "$day" "$today" "$row" <<'PY'
import re, sys, pathlib
path, day, today, new_row = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
p = pathlib.Path(path)
text = p.read_text()
# Match the exact placeholder row "| <day> | <date> | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _operator entry_ |"
pat = re.compile(
    rf"^\| {day} \| {re.escape(today)} \| _tbd_ \| _tbd_ \| _tbd_ \| _tbd_ \| _operator entry_ \|$",
    re.M,
)
if not pat.search(text):
    # Idempotency / re-run safety: also accept already-replaced row to avoid double-fills.
    already = re.compile(rf"^\| {day} \| {re.escape(today)} \|", re.M)
    if already.search(text):
        print("ALREADY_FILLED")
        sys.exit(0)
    print("NO_MATCH")
    sys.exit(2)
text = pat.sub(new_row.replace("\\", "\\\\"), text, count=1)
p.write_text(text)
print("UPDATED")
PY
  local rc_py=$?
  if [[ $rc_py -eq 2 ]]; then
    log "  no placeholder row matched for Day $day; aborting (table edited externally?)"
    return 1
  fi

  if git diff --quiet -- "$PLAN_PATH"; then
    log "  no diff — Day $day already filled; skipping commit"
    return 0
  fi

  if [[ -n "${DRY_RUN:-}" ]]; then
    log "  DRY_RUN: would commit + push the following diff:"
    git --no-pager diff -- "$PLAN_PATH" >> "$LOG" 2>&1
    git checkout --quiet -- "$PLAN_PATH"
  else
    git add "$PLAN_PATH"
    git -c user.name="Clawdia" -c user.email="clawdia-ai-assistant@gmail.com" \
      commit --quiet -m "agents: Phase 5 soak Day $day (gh#156)" \
      -m "p99 working-set, queue peak, restart count for ${today}. Auto-filled by phase5-soak-daily.sh." >> "$LOG" 2>&1
    # --force-with-lease is needed for the post-merge case: when we reset
    # the local branch to origin/main, the local history diverges from the
    # stale origin ref. The lease check refuses to overwrite if origin has
    # advanced since our fetch, so this is still safe under concurrent
    # work (which we don't expect, but cheap insurance).
    git push --quiet --force-with-lease --set-upstream origin "$SOAK_BRANCH" >> "$LOG" 2>&1
    log "  Day $day pushed to $SOAK_BRANCH"
  fi

  # Open a PR if none is open against this branch (honors DRY_RUN internally).
  ensure_soak_pr
}

ensure_soak_pr() {
  local existing
  existing=$(gh pr list --repo "$REPO_SLUG" --state open --head "$SOAK_BRANCH" \
    --json number --jq '.[].number' 2>>"$LOG" | head -1)
  if [[ -n "$existing" ]]; then
    log "  PR #${existing} already open for $SOAK_BRANCH; nothing to do"
    return 0
  fi
  log "  no open PR for $SOAK_BRANCH — opening one"
  local pr_body
  pr_body=$(cat <<EOF
Phase 5 soak data collection (gh#156). Auto-filled by
\`scripts/phase5-soak-daily.sh\` on the secure-agent-pod each day at
08:00 UTC for the soak window 2026-05-04 → 2026-05-16 (Days 2–14).

The Soak Log table on \`main\` (from #205) ships 14 placeholder rows;
this PR replaces \`_tbd_\` cells with actual readings as the days roll.
Merge when the table is full and the Phase 5 Task 2 decision (a/b/c)
is documented, OR earlier if you want to mid-cycle review.

Once Day 14 (2026-05-16) has been recorded, the daily script switches
to cleanup-nag mode automatically — see \`scripts/phase5-soak-daily.sh\`
header for the manual cleanup steps.
EOF
)
  if [[ -n "${DRY_RUN:-}" ]]; then
    log "  DRY_RUN: would gh pr create --base $BASE_BRANCH --head $SOAK_BRANCH"
    return 0
  fi
  gh pr create --repo "$REPO_SLUG" \
    --base "$BASE_BRANCH" --head "$SOAK_BRANCH" \
    --title "agents: Phase 5 soak data collection (gh#156)" \
    --body "$pr_body" >> "$LOG" 2>&1 \
    || log "  gh pr create failed (non-fatal)"
}

# --- Main -------------------------------------------------------------------
main() {
  # Optional flags:
  #   --date YYYY-MM-DD   override "today" (smoke testing / backfill)
  #   --dry-run           run soak path but don't commit/push or open issues
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --date) OVERRIDE_DATE="$2"; shift 2 ;;
      --dry-run) DRY_RUN=1; shift ;;
      *) log "unknown arg: $1"; exit 2 ;;
    esac
  done
  log "fire: $(date -u +%F\ %T)${OVERRIDE_DATE:+ (override=$OVERRIDE_DATE)}${DRY_RUN:+ (dry-run)}"
  local today; today="${OVERRIDE_DATE:-$(date -u +%F)}"
  if [[ "$today" > "$SOAK_LAST" ]]; then
    nag_for_cleanup
  else
    soak_today
  fi
}

main "$@"
