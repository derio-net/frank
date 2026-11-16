#!/usr/bin/env python3
"""Benchmark the speech service (stdlib only).

Posts the operator's audio samples to /v1/audio/transcriptions and fixed EN/DE/EL
text to /v1/audio/speech, and records real-time factor (STT), time-to-first-audio
(TTS) and VRAM. Every synthesized clip is saved under --out-dir for listening.
Writes a markdown table.

Samples: --samples-dir must hold en.wav, de.wav and el.wav (16-bit PCM WAV,
supplied by the operator, e.g. a few minutes of each language read aloud); the
script exits with a message if any is missing.

VRAM: record two nvidia-smi logs on gpu-1 (whole-card figures):
  baseline = Ollama loaded, speech idle/unloaded; run = during this benchmark.
Speech-only VRAM = peak(run) - peak(baseline); that is the figure that belongs
in apps/speech/manifests/files/vram-budget.yaml.

  python3 scripts/speech-benchmark/run.py --base-url http://speech.speech.svc.cluster.local:8000 \
      --stt-model deepdml/faster-whisper-large-v3-turbo-ct2 \
      --samples-dir samples --out-dir tts-out \
      --tts EN=speaches-ai/Kokoro-82M-v1.0-ONNX:af_heart \
      --tts DE=speaches-ai/Kokoro-82M-v1.0-ONNX:af_heart \
      --tts EL=speaches-ai/Kokoro-82M-v1.0-ONNX:af_heart \
      --baseline-smi-log base.csv --nvidia-smi-log run.csv --out results.md

--tts LANG=MODEL:VOICE is repeatable (voice = text after the last colon); a
language with no --tts uses --tts-model/--voice, which default to Kokoro-82M /
af_heart.

Manual operation: infer-speech-benchmark-run.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path

# Fixed TTS inputs, so runs are comparable across models.
DEFAULT_TTS_MODEL = "speaches-ai/Kokoro-82M-v1.0-ONNX"
DEFAULT_VOICE = "af_heart"

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


def _field_name(name):
    """A multipart field name must not be able to break out of its quotes."""
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", str(name)):
        raise ValueError(f"unsafe multipart field name: {name!r}")
    return name


def _filename(name):
    """Escape a filename for Content-Disposition (quotes and CR/LF)."""
    return str(name).replace("\r", "%0D").replace("\n", "%0A").replace('"', "%22")


def check_base_url(url):
    """Only http(s): urllib would also open file:// and ftp:// URLs."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"--base-url must start with http:// or https://, got {url!r}")
    return url


def _multipart(fields, file_field, file_path):
    boundary = uuid.uuid4().hex
    parts = []
    file_field = _field_name(file_field)
    for k, v in fields.items():
        k = _field_name(k)
        if "\r" in str(v) or "\n" in str(v):
            raise ValueError(f"multipart value for {k!r} contains a line break")
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    data = Path(file_path).read_bytes()
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{_filename(Path(file_path).name)}"\r\nContent-Type: application/octet-stream\r\n\r\n'
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


def parse_tts_specs(specs):
    """['EN=model:voice', ...] -> {'en': (model, voice)}."""
    out = {}
    for spec in specs:
        lang, _, rest = spec.partition("=")
        model, sep, voice = rest.rpartition(":")
        if not (lang and sep and model and voice):
            raise ValueError(f"--tts expects LANG=MODEL:VOICE, got {spec!r}")
        out[lang.lower()] = (model, voice)
    return out


def bench_tts(base_url, model, voice, lang, text, timeout=600, out_path=None):
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
    sink = open(out_path, "wb") if out_path else None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                chunk = resp.read(64)
                if not chunk:
                    break
                if first is None:
                    first = time.monotonic() - t0
                total += len(chunk)
                if sink:
                    sink.write(chunk)
    finally:
        if sink:
            sink.close()
    elapsed = time.monotonic() - t0
    if not total:
        raise RuntimeError(f"TTS ({model}, {lang}) returned an empty body")
    return {
        "kind": "tts", "lang": lang, "model": model, "seconds": elapsed,
        "metric": "ttfa_s", "value": first, "bytes": total,
    }


def _fmt(v):
    return "n/a" if v is None else f"{v:.3f}"


def render_table(rows, peak_vram_mib=None, baseline_mib=None):
    lines = [
        "| kind | lang | model | total s | metric | value |",
        "|------|------|-------|---------|--------|-------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['kind']} | {r['lang']} | {r['model']} | {_fmt(r['seconds'])} | {r['metric']} | {_fmt(r['value'])} |"
        )
    def mib(v):
        return "n/a" if v is None else f"{v} MiB"

    only = None if peak_vram_mib is None or baseline_mib is None else peak_vram_mib - baseline_mib
    if only is not None and only < 0:
        # a baseline above the run's peak means swapped logs or a model unloaded
        # mid-run; a negative "speech-only" figure would be wrong, not a result
        lines += ["", f"WARNING: baseline ({baseline_mib} MiB) exceeds peak ({peak_vram_mib} MiB); check the logs."]
        only = None
    lines += [
        "",
        f"Baseline VRAM (Ollama loaded, speech idle): {mib(baseline_mib)}",
        f"Peak VRAM: {mib(peak_vram_mib)}",
        f"Speech-only VRAM (peak - baseline): {mib(only)}",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--stt-model", required=True)
    ap.add_argument("--tts-model", default=DEFAULT_TTS_MODEL, help="fallback TTS model")
    ap.add_argument("--voice", default=DEFAULT_VOICE, help="fallback TTS voice")
    ap.add_argument("--tts", action="append", default=[], metavar="LANG=MODEL:VOICE",
                    help="per-language TTS model and voice (repeatable)")
    ap.add_argument("--samples-dir", required=True, help="directory with en.wav, de.wav, el.wav")
    ap.add_argument("--out-dir", required=True, help="where synthesized audio is saved")
    ap.add_argument("--baseline-smi-log", help="nvidia-smi log with speech idle, Ollama loaded")
    ap.add_argument("--nvidia-smi-log", help="nvidia-smi log recorded during the run")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    samples = Path(args.samples_dir)
    missing = [str(samples / f"{lang}.wav") for lang in TTS_TEXTS if not (samples / f"{lang}.wav").is_file()]
    if missing:
        sys.exit("missing audio samples (operator-supplied): " + ", ".join(missing))
    try:
        check_base_url(args.base_url)
        tts_cfg = parse_tts_specs(args.tts)
    except ValueError as e:
        sys.exit(str(e))
    unknown = sorted(set(tts_cfg) - set(TTS_TEXTS))
    if unknown:
        sys.exit(f"--tts language(s) {unknown} not benchmarked; known: {sorted(TTS_TEXTS)}")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    try:
        for lang in TTS_TEXTS:
            rows.append(bench_stt(args.base_url, args.stt_model, lang, samples / f"{lang}.wav"))
        for lang, text in TTS_TEXTS.items():
            model, voice = tts_cfg.get(lang, (args.tts_model, args.voice))
            rows.append(bench_tts(args.base_url, model, voice, lang, text,
                                  out_path=out_dir / f"tts-{lang}.mp3"))
    except (urllib.error.URLError, RuntimeError, ValueError) as e:
        sys.exit(f"benchmark failed: {e}")
    table = render_table(rows, peak_vram_mib(args.nvidia_smi_log), peak_vram_mib(args.baseline_smi_log))
    Path(args.out).write_text(table)
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
