#!/usr/bin/env bash
# Batch transcription + quiet-alerts check (speech service Test Plan step 5, #1006):
# batch-transcribe a LONG recording, optionally cycle the GPU to ComfyUI and back,
# then confirm from Grafana's alert state history that no related alert FIRED
# (Pending is allowed: that is what a rule's `for` window is for). Prints a
# colon-free gate answer.
#
# The recording goes to the in-cluster service, not speech.cluster.derio.net:
# the websecure entrypoint's read timeout would cut a long upload. It is
# re-encoded locally to 16 kHz mono Opus (small) and streamed through
# `kubectl exec` stdin to curl inside the speech pod (127.0.0.1:8000), which
# also avoids gpu-1's flaky port-forwards.
#
# Usage:
#   bash scripts/speech/speech-batch-alerts-check.sh <recording> [--cycle-comfyui] [--settle-min N]
#   bash scripts/speech/speech-batch-alerts-check.sh --record MINUTES [--cycle-comfyui] [--settle-min N]
# --record MINUTES record from the Mac's mic first (after the Grafana preflight),
#                  up to MINUTES; press q to stop early. Kept as recording.ogg
#                  beside the transcript. MIC overrides the device (default ":0").
# --cycle-comfyui  after the transcription, activate ComfyUI, wait until Ollama
#                  and speech are at 0, activate Ollama, wait until both are Ready
# --settle-min N   minutes to wait before reading alert history (default 5)
# Env: KUBECONFIG (default: the repo's .talos/Frank_Kubeconfig.yaml), LANG_HINT to
#      pass a language (default none = auto-detect), STT_MODEL, OUT_DIR.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
# Gitignored operator files (.env_hop, .talos/) live only in the MAIN checkout,
# not in an fr worktree: look in this checkout first, then the main one.
MAIN=$(dirname "$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$REPO/.git")")
repo_file() { if [ -e "$REPO/$1" ]; then echo "$REPO/$1"; else echo "$MAIN/$1"; fi; }
USAGE="usage: $0 <recording>|--record MINUTES [--cycle-comfyui] [--settle-min N]"
REC=""
RECORD_MIN=""
CYCLE=0
SETTLE_MIN=5
while [ $# -gt 0 ]; do
  case "$1" in
    --record) RECORD_MIN=${2:?--record needs MINUTES}; shift 2 ;;
    --cycle-comfyui) CYCLE=1; shift ;;
    --settle-min) SETTLE_MIN=${2:?}; shift 2 ;;
    -*) echo "unknown argument $1" >&2; echo "$USAGE" >&2; exit 2 ;;
    *) [ -z "$REC" ] || { echo "$USAGE" >&2; exit 2; }; REC=$1; shift ;;
  esac
done
if [ -n "$RECORD_MIN" ]; then
  [ -z "$REC" ] || { echo "give a recording OR --record, not both" >&2; exit 2; }
  python3 -c "import sys; float(sys.argv[1]) > 0 or sys.exit(1)" "$RECORD_MIN" 2>/dev/null || { echo "--record MINUTES must be a positive number" >&2; exit 2; }
else
  [ -n "$REC" ] || { echo "$USAGE" >&2; exit 2; }
  [ -f "$REC" ] || { echo "no such file $REC" >&2; exit 2; }
fi
export KUBECONFIG=${KUBECONFIG:-$(repo_file .talos/Frank_Kubeconfig.yaml)}
STT_MODEL=${STT_MODEL:-deepdml/faster-whisper-large-v3-turbo-ct2}
SWITCHER=http://192.168.55.214:8080
GRAFANA=http://192.168.55.203
for c in kubectl curl python3 ffmpeg ffprobe; do command -v $c >/dev/null || { echo "missing $c" >&2; exit 2; }; done

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
OUT=${OUT_DIR:-$HOME/Downloads/speech-batch-check-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT"

# Grafana admin credentials, read live from the cluster (never stored).
GAUTH="$(kubectl -n monitoring get secret victoria-metrics-grafana -o jsonpath='{.data.admin-user}' | base64 -d):$(kubectl -n monitoring get secret victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)"

echo "== Preflight - Grafana must evaluate the MERGED rules (it reads them only at boot)"
curl -sS -u "$GAUTH" "$GRAFANA/api/prometheus/grafana/api/v1/rules" > "$WORK/rules.json"
python3 - "$WORK/rules.json" <<'PY'
import json, sys
rules = [r for g in json.load(open(sys.argv[1]))["data"]["groups"] for r in g["rules"]]
by = {r["name"]: r for r in rules}
problems = []
s2z = by.get("Workload Unexpectedly Scaled To Zero", {}).get("query", "")
if "speech" not in s2z:
    problems.append("scale-to-zero rule does not exclude speech (stale provisioning? restart Grafana)")
if "Speech Service Degraded" not in by:
    problems.append("'Speech Service Degraded' rule is not loaded (stale provisioning? restart Grafana)")
print("  scale-to-zero query", s2z)
print("  Speech Service Degraded", "loaded" if "Speech Service Degraded" in by else "MISSING")
if problems:
    print("PREFLIGHT FAIL - " + "; ".join(problems)); sys.exit(1)
PY

state() { curl -sS --max-time 10 "$SWITCHER/api/status"; }
wait_for() {  # wait_for "<python expr over dict s of name->(replicas,ready)>" <timeout-s> <label>
  local expr=$1 to=$2 label=$3 t=0
  until state | python3 -c "import json,sys; s={w['name']:(w['replicas'],w['readyReplicas']) for w in json.load(sys.stdin)}; sys.exit(0 if ($expr) else 1)"; do
    t=$((t+10)); [ $t -ge "$to" ] && { echo "  timeout waiting for $label" >&2; return 1; }
    sleep 10
  done
  echo "  $label after ~${t}s"
}

if [ -n "$RECORD_MIN" ]; then
  REC="$OUT/recording.ogg"
  SECS=$(python3 -c "import sys; print(int(float(sys.argv[1]) * 60))" "$RECORD_MIN")
  echo "== Recording up to ${RECORD_MIN} min from mic ${MIC:-:0} (speak or play audio near it; press q to stop early)"
  read -r -p "Press Enter to start recording... " _ </dev/tty
  # Straight to 16 kHz mono Opus: small for a long recording. `q` makes ffmpeg finish the file cleanly.
  ffmpeg -hide_banner -loglevel error -stats -f avfoundation -i "${MIC:-:0}" -t "$SECS" \
    -ac 1 -ar 16000 -c:a libopus -b:a 24k -y "$REC" </dev/tty || true
  [ -s "$REC" ] || { echo "recording failed or empty" >&2; exit 1; }
  echo "  recorded $(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$REC" | python3 -c "import sys; print(f'{float(sys.stdin.read())/60:.1f}')") min -> $REC"
fi

echo "== Speech must be up (gpu-switcher: activate ollama)"
wait_for "s['speech']==(1,1) and s['ollama']==(1,1)" 600 "ollama and speech Ready"

START_MS=$(( $(date +%s) * 1000 ))
START_ISO=$(date -u +%FT%TZ)
DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$REC")
echo "== Encoding $REC ($(python3 -c "print(f'{float(\"$DUR\")/60:.1f}')") min) to 16 kHz mono Opus"
ffmpeg -hide_banner -loglevel error -i "$REC" -ac 1 -ar 16000 -c:a libopus -b:a 24k -y "$WORK/batch.ogg"
echo "  $(du -h "$WORK/batch.ogg" | cut -f1) to stream"

echo "== Transcribing in-cluster (no language hint unless LANG_HINT is set) ..."
LANG_ARG=""
[ -n "${LANG_HINT:-}" ] && LANG_ARG="--form-string language=${LANG_HINT}"
T0=$(date +%s)
# shellcheck disable=SC2086
kubectl -n speech exec -i deploy/speech -- curl -sS --max-time 14400 \
  -F "file=@-;filename=batch.ogg" --form-string "model=${STT_MODEL}" \
  --form-string "response_format=verbose_json" $LANG_ARG \
  -w '\n__HTTP__%{http_code}' http://127.0.0.1:8000/v1/audio/transcriptions \
  < "$WORK/batch.ogg" > "$WORK/resp.txt"
T1=$(date +%s)
python3 - "$WORK/resp.txt" "$OUT" "$DUR" "$((T1-T0))" > "$WORK/batch.summary" <<'PY'
import json, sys, os
raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
body, _, code = raw.rpartition("\n__HTTP__")
out, dur, wall = sys.argv[2], float(sys.argv[3]), int(sys.argv[4])
if code != "200":
    print(f"FAIL HTTP {code} {body[:200]!r}"); sys.exit(0)
d = json.loads(body)
open(os.path.join(out, "transcript.txt"), "w").write(d.get("text", "").strip() + "\n")
json.dump(d, open(os.path.join(out, "transcript.json"), "w"), ensure_ascii=False)
segs = d.get("segments") or []
print(f"OK language={d.get('language')} audio={dur/60:.1f}min wall={wall}s rtf={wall/dur:.3f} segments={len(segs)} chars={len(d.get('text',''))}")
PY
sed 's/^/  /' "$WORK/batch.summary"
echo "  transcript in $OUT"

if [ "$CYCLE" = 1 ]; then
  echo "== Cycling the GPU - ComfyUI on, then back to Ollama"
  curl -fsS -X POST "$SWITCHER/api/activate/comfyui" >/dev/null
  wait_for "s['ollama'][0]==0 and s['speech'][0]==0 and s['comfyui']==(1,1)" 900 "ComfyUI Ready, ollama and speech at 0"
  curl -fsS -X POST "$SWITCHER/api/activate/ollama" >/dev/null
  wait_for "s['speech']==(1,1) and s['ollama']==(1,1) and s['comfyui'][0]==0" 900 "ollama and speech back"
fi

echo "== Settling ${SETTLE_MIN} min so any rule whose 'for' window started can fire ..."
sleep $(( SETTLE_MIN * 60 ))
END_MS=$(( $(date +%s) * 1000 ))
curl -sS -u "$GAUTH" "$GRAFANA/api/annotations?type=alert&from=$START_MS&to=$END_MS&limit=2000" > "$WORK/ann.json"
curl -sS -u "$GAUTH" "$GRAFANA/api/prometheus/grafana/api/v1/rules" > "$WORK/rules2.json"

python3 - "$WORK/ann.json" "$WORK/rules2.json" "$WORK/batch.summary" "$START_ISO" "$CYCLE" "$REC" <<'PY'
import json, sys, datetime as dt, os, re
ann, rules = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
summary, start, cycle, rec = open(sys.argv[3]).read().strip(), sys.argv[4], sys.argv[5] == "1", os.path.basename(sys.argv[6])
REL = re.compile(r"speech|ollama|comfyui|gpu|scaled to zero|local inference|media generation", re.I)
def related(name, text): return bool(REL.search(name or "") or REL.search(text or ""))
# GPU-timeshare feature rules (gpu_timeshare="true": Layer 11 inference, Layer 16
# media) fire BY DESIGN whenever the other workload holds the card; they only
# update the health-bridge tile (the pager is gpu-node-both-down). The speech
# rule carries the same label but must count: it fires only while speech is
# desired up and failing.
def by_design(name, labels_text):
    return "gpu_timeshare=true" in labels_text.replace('"', "") and "Speech" not in (name or "")
rule_labels = {r["name"]: ",".join(f"{k}={v}" for k, v in (r.get("labels") or {}).items())
               for g in rules["data"]["groups"] for r in g["rules"]}
fired, pending, design = [], [], []
for a in sorted(ann, key=lambda a: a["time"]):
    n, new = a.get("alertName", ""), a.get("newState", "")
    if not related(n, a.get("text", "")):
        continue
    t = dt.datetime.fromtimestamp(a["time"] / 1000, dt.UTC).strftime("%H:%M:%S")
    line = f"{t} {n} {a.get('prevState')} -> {new}"
    if by_design(n, (a.get("text") or "") + rule_labels.get(n, "")):
        design.append(line)
    elif new.startswith("Alerting"):
        fired.append(line)
    else:
        pending.append(line)
firing = [(r["name"], rule_labels.get(r["name"], "")) for g in rules["data"]["groups"] for r in g["rules"]
          if r.get("state") == "firing" and related(r["name"], r.get("query", ""))]
now_firing = [n for n, l in firing if not by_design(n, l)]
design_now = [n for n, l in firing if by_design(n, l)]
print("\n== Alert state changes since", start, "(related rules)")
for l in fired: print("  FIRED   ", l)
for l in pending: print("  pending ", l)
for l in design: print("  by-design (gpu_timeshare tile)", l)
if not (fired or pending or design): print("  none")
print("  firing now (related, counted):", now_firing or "none")
print("  firing now (by design, gpu_timeshare tile only):", design_now or "none")
ok = summary.startswith("OK") and not fired and not now_firing
print("\nRESULT", "PASS" if ok else "FAIL")
verb = "ran" if ok else "owed"
alerts = "no related alert fired" if not fired and not now_firing else f"FIRED {'; '.join(fired + now_firing)}"
line = (f"{verb} speech-batch-alerts-check.sh on {start} - in-cluster batch transcription of {rec} ({summary.removeprefix('OK ').removeprefix('FAIL ')})"
        f"{', then GPU cycled to ComfyUI and back' if cycle else ''}; Grafana evaluating the merged rules (preflight); "
        f"{alerts}, {len(pending)} transient pending transitions that cleared"
        f"{'; by design (gpu_timeshare health-bridge tile, not paging) ' + ', '.join(design_now) if design_now else ''}")
print("\nSuggested gate answer (one line, colon-free) -")
print(line.replace(":", "-"))
sys.exit(0 if ok else 1)
PY
