#!/usr/bin/env bash
# STT language auto-detect check (speech service Test Plan step 2, #1006).
# Records a short clip per language, POSTs it to /v1/audio/transcriptions
# WITHOUT a language hint, and shows the auto-detected language and text.
# Ends with a PASS/FAIL table.
#
# Usage:
#   bash scripts/speech/speech-stt-check.sh                    # record en, de, el in turn
#   bash scripts/speech/speech-stt-check.sh el                 # just Greek
#   bash scripts/speech/speech-stt-check.sh --file clip.wav de # use an existing file
# Env overrides:
#   SPEECH_URL   (default https://speech.cluster.derio.net)
#   STT_MODEL    (default the deployed preload: deepdml/faster-whisper-large-v3-turbo-ct2)
#   SECONDS_REC  (default 8)   MIC (default ":0", macOS avfoundation audio device)
# List mic devices: ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A9 audio
set -euo pipefail

SPEECH_URL=${SPEECH_URL:-https://speech.cluster.derio.net}
STT_MODEL=${STT_MODEL:-deepdml/faster-whisper-large-v3-turbo-ct2}
SECONDS_REC=${SECONDS_REC:-8}
MIC=${MIC:-:0}

FILE=""
if [ "${1:-}" = "--file" ]; then
  FILE=${2:?--file needs a path}
  shift 2
fi
LANGS=("$@")
[ ${#LANGS[@]} -eq 0 ] && LANGS=(en de el)
if [ -n "$FILE" ] && [ ${#LANGS[@]} -ne 1 ]; then
  echo "--file takes exactly one expected language (en|de|el)" >&2
  exit 2
fi

command -v curl >/dev/null || { echo "curl missing" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 missing" >&2; exit 2; }
[ -n "$FILE" ] || command -v ffmpeg >/dev/null || { echo "ffmpeg missing (needed to record)" >&2; exit 2; }

prompt_for() {
  case "$1" in
    en) echo "Say in ENGLISH, e.g.: 'The cluster is called Frank and it lives in a cupboard.'" ;;
    de) echo "Sag auf DEUTSCH, z.B.: 'Der Cluster heisst Frank und wohnt in einem Schrank.'" ;;
    el) echo "Πες στα ΕΛΛΗΝΙΚΑ, π.χ.: 'Το cluster λέγεται Frank και μένει σε μια ντουλάπα.'" ;;
    *)  echo "Speak in '$1'" ;;
  esac
}

# Reachability first, so a dead route does not look like a recognition failure.
if ! curl -fsS --max-time 10 "$SPEECH_URL/v1/models" >/dev/null; then
  echo "ERROR: $SPEECH_URL/v1/models not reachable. Is speech scaled up (gpu-switcher: activate ollama) and are you on the LAN/mesh?" >&2
  exit 1
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
RESULTS="$WORK/results.tsv"
: > "$RESULTS"

for lang in "${LANGS[@]}"; do
  if [ -n "$FILE" ]; then
    clip=$FILE
  else
    clip="$WORK/$lang.wav"
    echo
    prompt_for "$lang"
    read -r -p "Press Enter, then speak for ${SECONDS_REC}s... " _
    ffmpeg -hide_banner -loglevel error -f avfoundation -i "$MIC" -t "$SECONDS_REC" -ac 1 -ar 16000 -y "$clip"
    echo "recorded $(python3 -c 'import os,sys; print(os.path.getsize(sys.argv[1]))' "$clip") bytes"
  fi

  start=$(python3 -c 'import time; print(time.time())')
  resp="$WORK/$lang.json"
  code=$(curl -sS --max-time 300 -o "$resp" -w '%{http_code}' \
    -F "file=@${clip}" \
    --form-string "model=${STT_MODEL}" \
    --form-string "response_format=verbose_json" \
    "$SPEECH_URL/v1/audio/transcriptions")
  end=$(python3 -c 'import time; print(time.time())')

  python3 - "$lang" "$code" "$resp" "$start" "$end" >> "$RESULTS" <<'PY'
import json, sys
expected, code, path, start, end = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
# speaches/faster-whisper may report an ISO code ("el") or OpenAI's full name ("greek").
names = {"english": "en", "german": "de", "greek": "el"}
body = open(path, encoding="utf-8", errors="replace").read()
if code != "200":
    print(f"{expected}\t-\tFAIL\tHTTP {code}: {body[:200]!r}\t-")
    sys.exit(0)
try:
    d = json.loads(body)
except ValueError:
    print(f"{expected}\t-\tFAIL\tnon-JSON response: {body[:200]!r}\t-")
    sys.exit(0)
got = str(d.get("language", "?")).lower()
got = names.get(got, got)
text = " ".join(str(d.get("text", "")).split())
verdict = "PASS" if got == expected and text else "FAIL"
dur = d.get("duration")
rtf = f"{(end-start)/dur:.2f}" if isinstance(dur, (int, float)) and dur else "-"
print(f"{expected}\t{got}\t{verdict}\t{text}\t{rtf}")
PY
  tail -1 "$RESULTS" | awk -F'\t' '{printf "  expected=%s detected=%s %s\n  text: %s\n", $1, $2, $3, $4}'
done

echo
echo "== STT language auto-detect ($SPEECH_URL, model $STT_MODEL) =="
printf '%-8s %-9s %-6s %-6s %s\n' expected detected result rtf text
awk -F'\t' '{printf "%-8s %-9s %-6s %-6s %s\n", $1, $2, $3, $5, $4}' "$RESULTS"
echo "(rtf = request wall time / audio duration, includes network and any model load; the first call after idle loads the model)"
if grep -q $'\tFAIL\t' "$RESULTS"; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
