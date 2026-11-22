#!/usr/bin/env bash
# Speech benchmark wrapper (speech service Test Plan step 7, manual-op
# infer-speech-benchmark-run, #1006). Loads the allowlisted Ollama model,
# takes a whole-card baseline with speech idle, samples nvidia-smi during the
# run, and runs scripts/speech-benchmark/run.py (STT real-time factor, TTS time
# to first audio, speech-only VRAM = peak - baseline) for en, de and el with
# the chosen voices (Kokoro af_heart, Piper thorsten, Piper rapunzelina).
#
# Usage:
#   bash scripts/speech/speech-benchmark.sh --samples-dir DIR   # DIR has en.wav de.wav el.wav
#   bash scripts/speech/speech-benchmark.sh --record [SECONDS]   # record them now (default 30 s each)
# Options: --no-idle-wait (skip the 330 s wait for speech to unload its models
#          before the baseline; use only if speech has been idle for 5+ minutes)
# Output: the markdown report, the smi logs and the TTS audio go to OUT_DIR
#   (default ~/Downloads/speech-benchmark-<time>/). Committing a report (as in
#   docs/investigations/2026-11-16--infer--speech-benchmark.md) is a separate PR.
# Reading the numbers: the first call per model after the idle wait is COLD
# (model load), so it measures load time, not steady-state latency.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
# Gitignored operator files (.env_hop, .talos/) live only in the MAIN checkout,
# not in an fr worktree: look in this checkout first, then the main one.
MAIN=$(dirname "$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$REPO/.git")")
repo_file() { if [ -e "$REPO/$1" ]; then echo "$REPO/$1"; else echo "$MAIN/$1"; fi; }
RUNPY=$REPO/scripts/speech-benchmark/run.py
SAMPLES=""
RECORD_SECS=""
IDLE_WAIT=330
while [ $# -gt 0 ]; do
  case "$1" in
    --samples-dir) SAMPLES=${2:?}; shift 2 ;;
    --record) RECORD_SECS=30; shift; if [ "${1:-}" ] && [ "${1#-}" = "$1" ]; then RECORD_SECS=$1; shift; fi ;;
    --no-idle-wait) IDLE_WAIT=0; shift ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
[ -n "$SAMPLES$RECORD_SECS" ] || { echo "need --samples-dir DIR or --record [SECONDS]" >&2; exit 2; }
[ -f "$RUNPY" ] || { echo "$RUNPY not found" >&2; exit 2; }
export KUBECONFIG=${KUBECONFIG:-$(repo_file .talos/Frank_Kubeconfig.yaml)}
SWITCHER=http://192.168.55.214:8080
URL=${SPEECH_URL:-https://speech.cluster.derio.net}
OLLAMA_MODEL=${OLLAMA_MODEL:-gemma4:12b-64k}   # the VRAM-budget allowlist entry
OUT=${OUT_DIR:-$HOME/Downloads/speech-benchmark-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT"

if [ -n "$RECORD_SECS" ]; then
  command -v ffmpeg >/dev/null || { echo "ffmpeg needed to record" >&2; exit 2; }
  SAMPLES="$OUT/samples"; mkdir -p "$SAMPLES"
  for l in en de el; do
    case $l in
      en) p="Read some natural ENGLISH for ${RECORD_SECS}s (a paragraph from anything)." ;;
      de) p="Lies ${RECORD_SECS}s natürliches DEUTSCH vor." ;;
      el) p="Διάβασε ${RECORD_SECS}s φυσικά ΕΛΛΗΝΙΚΑ." ;;
    esac
    echo "$p"; read -r -p "Press Enter, then speak... " _ </dev/tty
    ffmpeg -hide_banner -loglevel error -f avfoundation -i "${MIC:-:0}" -t "$RECORD_SECS" -ac 1 -ar 16000 -y "$SAMPLES/$l.wav"
  done
fi
for l in en de el; do [ -f "$SAMPLES/$l.wav" ] || { echo "missing $SAMPLES/$l.wav" >&2; exit 2; }; done

echo "== Speech and Ollama must be up together"
curl -sS --max-time 10 "$SWITCHER/api/status" | python3 -c "
import json,sys
s={w['name']:(w['replicas'],w['readyReplicas']) for w in json.load(sys.stdin)}
ok = s.get('ollama')==(1,1) and s.get('speech')==(1,1)
print('  ollama', s.get('ollama'), 'speech', s.get('speech'))
sys.exit(0 if ok else 'activate ollama in gpu-switcher first')"

SMI_POD=$(kubectl -n gpu-operator get pod -l app=nvidia-device-plugin-daemonset --field-selector spec.nodeName=gpu-1 -o jsonpath='{.items[0].metadata.name}')
SMI="nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -l 1"

echo "== Loading the allowlisted Ollama model ($OLLAMA_MODEL) so the baseline includes it"
kubectl -n ollama exec deploy/ollama -- ollama run "$OLLAMA_MODEL" "Reply with the single word ok." >/dev/null
kubectl -n ollama exec deploy/ollama -- ollama ps | sed 's/^/  /'

if [ "$IDLE_WAIT" -gt 0 ]; then
  echo "== Waiting ${IDLE_WAIT}s so speech unloads its models (STT_MODEL_TTL=300) before the baseline ..."
  sleep "$IDLE_WAIT"
fi
echo "== Baseline (whole card, Ollama loaded, speech idle), 60 s"
kubectl -n gpu-operator exec "$SMI_POD" -c nvidia-device-plugin -- timeout 60 $SMI > "$OUT/smi-base.csv" || true

echo "== Benchmark run with nvidia-smi sampling"
kubectl -n gpu-operator exec "$SMI_POD" -c nvidia-device-plugin -- timeout 1800 $SMI > "$OUT/smi-run.csv" &
SAMPLER=$!
set +e
python3 "$RUNPY" --base-url "$URL" \
  --stt-model deepdml/faster-whisper-large-v3-turbo-ct2 \
  --samples-dir "$SAMPLES" --out-dir "$OUT/tts-audio" \
  --tts EN=speaches-ai/Kokoro-82M-v1.0-ONNX:af_heart \
  --tts DE=speaches-ai/piper-de_DE-thorsten-high:thorsten \
  --tts EL=speaches-ai/piper-el_GR-rapunzelina-low:rapunzelina \
  --baseline-smi-log "$OUT/smi-base.csv" --nvidia-smi-log "$OUT/smi-run.csv" \
  --out "$OUT/speech-benchmark.md"
RC=$?
set -e
kubectl -n gpu-operator exec "$SMI_POD" -c nvidia-device-plugin -- pkill -f 'nvidia-smi --query-gpu' >/dev/null 2>&1 || true
wait $SAMPLER 2>/dev/null || true

echo
[ $RC = 0 ] && echo "RESULT run.py exited 0" || echo "RESULT run.py exited $RC"
echo "Report - $OUT/speech-benchmark.md (smi logs and TTS audio beside it)"
[ -f "$OUT/speech-benchmark.md" ] && sed -n '1,60p' "$OUT/speech-benchmark.md"
cat <<EOF

Next (not automated)
- Listen to the files in $OUT/tts-audio/.
- If the speech-only VRAM changed, update measured_total_gb in apps/speech/manifests/files/vram-budget.yaml,
  and commit the report under docs/investigations/, in one PR. Do not commit the voice recordings.
EOF
exit $RC
