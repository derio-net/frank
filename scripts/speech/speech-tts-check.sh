#!/usr/bin/env bash
# TTS per-language listening check (speech service Test Plan step 3, #1006):
# synthesize a sentence per language through /v1/audio/speech, play it on this
# Mac, ask whether it is acceptable, and print a ready-to-paste, colon-free
# answer for the DevOps gate.
#
# Voices: English uses Kokoro-82M (af_heart). Kokoro has NO German or Greek
# voice (with af_heart, German had an English accent and Greek was spelled
# letter by letter), so German and Greek use Piper de_DE-thorsten-high and
# el_GR-rapunzelina-low (the only Greek Piper voice). Both are preloaded since
# frank#1018. `--kokoro-only` reproduces the old Kokoro-for-everything result.
#
# Usage:
#   bash scripts/speech/speech-tts-check.sh                # Kokoro en, Piper de/el
#   bash scripts/speech/speech-tts-check.sh --kokoro-only  # Kokoro for all three
#   bash scripts/speech/speech-tts-check.sh --ensure-piper # download Piper if missing
#   bash scripts/speech/speech-tts-check.sh --cleanup      # delete the Piper models
# Env: SPEECH_URL (default https://speech.cluster.derio.net), PLAY=0 to skip playback,
#      ANSWERS="y n n" to answer non-interactively, OUT_DIR to choose where audio is kept.
set -euo pipefail

SPEECH_URL=${SPEECH_URL:-https://speech.cluster.derio.net}
PLAY=${PLAY:-1}
KOKORO=speaches-ai/Kokoro-82M-v1.0-ONNX
PIPER_DE=speaches-ai/piper-de_DE-thorsten-high
PIPER_EL=speaches-ai/piper-el_GR-rapunzelina-low

MODE=piper
ENSURE=0
case "${1:-}" in
  "") ;;
  --kokoro-only) MODE=default ;;
  --ensure-piper) ENSURE=1 ;;
  --cleanup) MODE=cleanup ;;
  *) echo "usage: $0 [--kokoro-only|--ensure-piper|--cleanup]" >&2; exit 2 ;;
esac

command -v curl >/dev/null && command -v python3 >/dev/null || { echo "need curl and python3" >&2; exit 2; }

if ! curl -fsS --max-time 10 "$SPEECH_URL/v1/models" >/dev/null; then
  echo "ERROR: $SPEECH_URL/v1/models not reachable (speech scaled up? on LAN/mesh?)" >&2
  exit 1
fi

model_present() { [ "$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' "$SPEECH_URL/v1/models/$1")" = 200 ]; }

if [ "$MODE" = cleanup ]; then
  echo "Note: both Piper models are in PRELOAD_MODELS, so a pod restart downloads them again."
  for m in "$PIPER_DE" "$PIPER_EL"; do
    if model_present "$m"; then
      code=$(curl -sS --max-time 60 -o /dev/null -w '%{http_code}' -X DELETE "$SPEECH_URL/v1/models/$m")
      echo "delete $m -> HTTP $code"
    else
      echo "$m not installed"
    fi
  done
  exit 0
fi

ensure_model() {
  if model_present "$1"; then
    echo "  $1 installed"
    return
  fi
  if [ "$ENSURE" != 1 ]; then
    echo "  $1 is NOT installed (expected from PRELOAD_MODELS); rerun with --ensure-piper to download it" >&2
    exit 1
  fi
  echo "  downloading $1 into the speech PVC ..."
  code=$(curl -sS --max-time 600 -o /dev/null -w '%{http_code}' -X POST "$SPEECH_URL/v1/models/$1")
  case "$code" in 200|201) echo "  downloaded ($code)" ;; *) echo "  download failed (HTTP $code)" >&2; exit 1 ;; esac
}

# lang | model | voice | native? | sentence
plan() {
  echo "en|$KOKORO|af_heart|yes|The cluster is called Frank and it lives in a cupboard. Today it learned to speak."
  if [ "$MODE" = piper ]; then
    echo "de|$PIPER_DE|thorsten|yes|Der Cluster heißt Frank und wohnt in einem Schrank. Heute hat er sprechen gelernt."
    echo "el|$PIPER_EL|rapunzelina|yes|Το cluster λέγεται Frank και μένει σε μια ντουλάπα. Σήμερα έμαθε να μιλάει."
  else
    echo "de|$KOKORO|af_heart|no|Der Cluster heißt Frank und wohnt in einem Schrank. Heute hat er sprechen gelernt."
    echo "el|$KOKORO|af_heart|no|Το cluster λέγεται Frank και μένει σε μια ντουλάπα. Σήμερα έμαθε να μιλάει."
  fi
}

if [ "$MODE" = piper ]; then
  echo "Piper voices:"
  ensure_model "$PIPER_DE"
  ensure_model "$PIPER_EL"
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
OUT=${OUT_DIR:-$HOME/Downloads/speech-tts-check-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT"
RESULTS="$WORK/results.tsv"
: > "$RESULTS"

while IFS='|' read -r lang model voice native text; do
  echo
  echo "== $lang  model=$model voice=$voice native-voice=$native"
  echo "   \"$text\""
  wav="$OUT/tts-$lang.wav"
  body=$(python3 -c 'import json,sys; print(json.dumps({"model":sys.argv[1],"voice":sys.argv[2],"input":sys.argv[3],"response_format":"wav"}))' "$model" "$voice" "$text")
  metrics=$(curl -sS --max-time 300 -o "$wav" -w '%{http_code} %{time_starttransfer} %{time_total}' \
    -H 'Content-Type: application/json' --data-binary "$body" "$SPEECH_URL/v1/audio/speech")
  read -r code ttfb total <<<"$metrics"
  ttfb=$(printf '%.2f' "$ttfb"); total=$(printf '%.2f' "$total")
  if [ "$code" != 200 ]; then
    echo "   HTTP $code: $(head -c 200 "$wav")"
    printf '%s\t%s\t%s\t%s\tFAIL\tHTTP %s\t-\n' "$lang" "$model" "$voice" "$native" "$code" >> "$RESULTS"
    continue
  fi
  secs=$(python3 - "$wav" <<'PY'
import os, sys, wave
# speaches streams WAV with a placeholder data length in the header, so the
# frame count is bogus: derive the duration from the file size instead.
try:
    with wave.open(sys.argv[1]) as w:
        per_sec = w.getframerate() * w.getnchannels() * w.getsampwidth()
    print(f"{max(os.path.getsize(sys.argv[1]) - 44, 0) / per_sec:.1f}")
except Exception:
    print("?")
PY
)
  echo "   HTTP 200, ${secs}s of audio, first byte after ${ttfb}s, total ${total}s -> $wav"
  [ "$PLAY" = 1 ] && command -v afplay >/dev/null && afplay "$wav" || true
  while :; do
    if [ -n "${ANSWERS:-}" ]; then   # non-interactive runs: ANSWERS="y n n"
      a=${ANSWERS%% *}; ANSWERS=${ANSWERS#"$a"}; ANSWERS=${ANSWERS# }
      echo "   Acceptable for $lang? (from ANSWERS) $a"
    else
      read -r -p "   Acceptable for $lang? [y]es / [n]o / [r]eplay: " a </dev/tty
    fi
    case "$a" in
      r|R) command -v afplay >/dev/null && afplay "$wav" || true ;;
      y|Y) verdict=PASS; break ;;
      n|N) verdict=FAIL; break ;;
    esac
  done
  printf '%s\t%s\t%s\t%s\t%s\tttfb %ss total %ss audio %ss\t-\n' "$lang" "$model" "$voice" "$native" "$verdict" "$ttfb" "$total" "$secs" >> "$RESULTS"
done < <(plan)

echo
echo "== TTS per language ($SPEECH_URL) =="
printf '%-4s %-6s %-7s %-40s %s\n' lang result native model/voice timings
awk -F'\t' '{printf "%-4s %-6s %-7s %-40s %s\n", $1, $5, $4, $2 "/" $3, $6}' "$RESULTS"
echo "Audio kept in $OUT"

# A colon-free one-line answer for the gate (`ran` if every language passed, else `owed`).
python3 - "$RESULTS" "$MODE" <<'PY'
import sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1]) if l.strip()]
mode = sys.argv[2]
def short(m): return m.split("/")[-1]
parts = [f"{r[0]} {r[4]} ({short(r[1])} voice {r[2]}{'' if r[3]=='yes' else ', no native voice'}; {r[5]})" for r in rows]
failed = [r[0] for r in rows if r[4] != "PASS"]
head = "speech-tts-check.sh against speech.cluster.derio.net, listened on the Mac -"
if not failed:
    line = f"ran {head} " + "; ".join(parts)
else:
    why = ("Kokoro-82M has no German or Greek voice, so " if mode == "default" else "")
    line = (f"owed {head} " + "; ".join(parts) + f" - {', '.join(failed)} not acceptable yet; "
            f"{why}the TTS engine for those languages needs another choice")
line = line.replace(":", " -")
print("\nSuggested gate answer (one line, colon-free) -")
print(line)
PY
