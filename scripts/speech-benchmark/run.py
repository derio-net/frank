#!/usr/bin/env python3
"""Benchmark the speech service (stdlib only).

Posts fixed audio samples to /v1/audio/transcriptions and fixed EN/DE/EL text to
/v1/audio/speech, and records real-time factor (STT), time-to-first-audio (TTS)
and, from a supplied nvidia-smi log, peak VRAM. Writes a markdown table.

  # in another shell, while the benchmark runs (Ollama loaded alongside):
  nvidia-smi --query-gpu=memory.used --format=csv -l 1 > smi.csv

  python3 scripts/speech-benchmark/run.py --base-url https://speech.cluster.derio.net \
      --stt-model deepdml/faster-whisper-large-v3-turbo-ct2 \
      --tts-model speaches-ai/Kokoro-82M-v1.0-ONNX --voice af_heart \
      --audio en=en.wav de=de.wav el=el.wav --nvidia-smi-log smi.csv --out results.md

Manual operation: infer-speech-benchmark-run.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
import uuid
import wave
from pathlib import Path

# Fixed TTS inputs, so runs are comparable across models.
TTS_TEXTS = {
    "en": "The quick brown fox jumps over the lazy dog. Speech synthesis should sound natural and steady.",
    "de": "Der schnelle braune Fuchs springt über den faulen Hund. Die Sprachausgabe soll natürlich klingen.",
    "el": "Η γρήγορη καφέ αλεπού πηδά πάνω από το τεμπέλικο σκυλί. Η σύνθεση ομιλίας πρέπει να ακούγεται φυσική.",
}


def real_time_factor(elapsed_s, audio_s):
    """Processing time divided by audio duration (lower is faster than real time)."""
    if not audio_s:
        return None
    return elapsed_s / audio_s


def wav_duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def peak_vram_mib(log_path):
    """Max MiB found in an nvidia-smi csv log (last number on each line); None if no log."""
    if not log_path:
        return None
    peak = None
    for line in Path(log_path).read_text().splitlines():
        m = re.findall(r"(\d+(?:\.\d+)?)", line.split(",")[-1])
        if not m or "memory" in line.lower():
            continue
        v = float(m[0])
        peak = v if peak is None else max(peak, v)
    return None if peak is None else int(peak)


def _multipart(fields, file_field, file_path):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    data = Path(file_path).read_bytes()
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{Path(file_path).name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def bench_stt(base_url, model, lang, audio_path, timeout=3 * 3600):
    audio_s = wav_duration(audio_path)
    body, ctype = _multipart({"model": model, "language": lang}, "file", audio_path)
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/audio/transcriptions", data=body, headers={"Content-Type": ctype}
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = json.loads(resp.read()).get("text", "")
    elapsed = time.monotonic() - t0
    return {
        "kind": "stt", "lang": lang, "model": model, "seconds": elapsed,
        "metric": "rtf", "value": real_time_factor(elapsed, audio_s), "chars": len(text),
    }


def bench_tts(base_url, model, voice, lang, text, timeout=600):
    payload = json.dumps(
        {"model": model, "voice": voice, "input": text, "response_format": "mp3"}
    ).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/audio/speech", data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    first = None
    total = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        while True:
            chunk = resp.read(64)
            if not chunk:
                break
            if first is None:
                first = time.monotonic() - t0
            total += len(chunk)
    elapsed = time.monotonic() - t0
    return {
        "kind": "tts", "lang": lang, "model": model, "seconds": elapsed,
        "metric": "ttfa_s", "value": first, "bytes": total,
    }


def _fmt(v):
    return "n/a" if v is None else f"{v:.3f}"


def render_table(rows, peak_vram_mib=None):
    lines = [
        "| kind | lang | model | total s | metric | value |",
        "|------|------|-------|---------|--------|-------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['kind']} | {r['lang']} | {r['model']} | {_fmt(r['seconds'])} | {r['metric']} | {_fmt(r['value'])} |"
        )
    vram = "n/a" if peak_vram_mib is None else f"{peak_vram_mib} MiB"
    lines += ["", f"Peak VRAM: {vram}", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--stt-model", required=True)
    ap.add_argument("--tts-model", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--audio", nargs="+", default=[], metavar="LANG=PATH",
                    help="fixed audio samples, e.g. en=en.wav de=de.wav el=el.wav")
    ap.add_argument("--nvidia-smi-log")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    rows = []
    for spec in args.audio:
        lang, _, path = spec.partition("=")
        rows.append(bench_stt(args.base_url, args.stt_model, lang, path))
    for lang, text in TTS_TEXTS.items():
        rows.append(bench_tts(args.base_url, args.tts_model, args.voice, lang, text))
    table = render_table(rows, peak_vram_mib(args.nvidia_smi_log))
    Path(args.out).write_text(table)
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
