"""Table rendering and timing maths of scripts/speech-benchmark/run.py, against a fake server."""
import importlib.util
import io
import json
import struct
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN = REPO / "scripts/speech-benchmark/run.py"


def _load():
    spec = importlib.util.spec_from_file_location("speech_benchmark_run", RUN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bench = _load()


def _wav(path, seconds, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * seconds))


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if self.path == "/v1/audio/transcriptions":
            assert b"multipart/form-data" in self.headers["Content-Type"].encode()
            assert b'name="model"' in body and b'name="file"' in body
            time.sleep(0.2)
            out = json.dumps({"text": "hello"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        elif self.path == "/v1/audio/speech":
            req = json.loads(body)
            assert req["input"] and req["model"] and req["voice"]
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            time.sleep(0.3)  # time to first audio
            for chunk in (b"a" * 100, b"b" * 100):
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
                time.sleep(0.1)
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.send_error(404)


def _server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_rtf_maths():
    assert bench.real_time_factor(elapsed_s=5.0, audio_s=10.0) == 0.5
    assert bench.real_time_factor(elapsed_s=1.0, audio_s=0.0) is None


def test_wav_duration(tmp_path):
    p = tmp_path / "a.wav"
    _wav(p, 2.5)
    assert abs(bench.wav_duration(p) - 2.5) < 0.01


def test_peak_vram_from_nvidia_smi_log(tmp_path):
    log = tmp_path / "smi.csv"
    log.write_text("memory.used [MiB]\n9800 MiB\n12100 MiB\n11000 MiB\n")
    assert bench.peak_vram_mib(log) == 12100
    assert bench.peak_vram_mib(None) is None
    plain = tmp_path / "plain.csv"
    plain.write_text("1, 100\n2, 300\n")
    assert bench.peak_vram_mib(plain) == 300


def test_table_rendering():
    rows = [
        {"kind": "stt", "lang": "en", "model": "m1", "seconds": 0.2, "metric": "rtf", "value": 0.1},
        {"kind": "tts", "lang": "el", "model": "m2", "seconds": 1.2, "metric": "ttfa_s", "value": 0.31},
    ]
    table = bench.render_table(rows, peak_vram_mib=12100)
    lines = table.strip().splitlines()
    assert lines[0].startswith("| kind | lang | model |")
    assert lines[1].startswith("|---")
    assert "| stt | en | m1 |" in lines[2]
    assert "0.100" in lines[2] and "0.310" in lines[3]
    assert "Peak VRAM: 12100 MiB" in table
    assert "n/a" in bench.render_table(rows, peak_vram_mib=None)
    both = bench.render_table(rows, peak_vram_mib=12100, baseline_mib=9800)
    assert "Baseline VRAM (Ollama loaded, speech idle): 9800 MiB" in both
    assert "Speech-only VRAM (peak - baseline): 2300 MiB" in both


def test_parse_tts_specs():
    got = bench.parse_tts_specs(["EN=org/m:af_heart", "el=a/b:c:voice-x"])
    assert got == {"en": ("org/m", "af_heart"), "el": ("a/b:c", "voice-x")}
    try:
        bench.parse_tts_specs(["EN=nocolon"])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_end_to_end_against_fake_server(tmp_path):
    srv, base = _server()
    try:
        a = tmp_path / "en.wav"
        _wav(a, 2.0)
        stt = bench.bench_stt(base, "stt-model", "en", a)
        assert stt["kind"] == "stt" and stt["metric"] == "rtf"
        assert 0.05 < stt["value"] < 0.5  # ~0.2 s / 2.0 s
        tts = bench.bench_tts(base, "tts-model", "voice", "el", "γειά σου")
        assert tts["metric"] == "ttfa_s"
        assert 0.2 < tts["value"] < 0.5  # first chunk after ~0.3 s
        assert tts["seconds"] > tts["value"]  # total includes the later chunks
        assert tts["bytes"] == 200
    finally:
        srv.shutdown()


def _samples(tmp_path, langs=("en", "de", "el")):
    d = tmp_path / "samples"
    d.mkdir()
    for lang in langs:
        _wav(d / f"{lang}.wav", 1.0)
    return d


def test_main_writes_markdown_and_audio(tmp_path):
    srv, base = _server()
    try:
        out = tmp_path / "res.md"
        smi = tmp_path / "run.csv"
        smi.write_text("memory.used [MiB]\n12000 MiB\n")
        base_log = tmp_path / "base.csv"
        base_log.write_text("memory.used [MiB]\n10000 MiB\n")
        rc = bench.main([
            "--base-url", base, "--stt-model", "s",
            "--tts", "EN=m-en:v1", "--tts", "DE=m-de:v2",
            "--samples-dir", str(_samples(tmp_path)), "--out-dir", str(tmp_path / "audio"),
            "--baseline-smi-log", str(base_log), "--nvidia-smi-log", str(smi),
            "--out", str(out),
        ])
        assert rc == 0
        text = out.read_text()
        assert "| stt | en | s |" in text and "| stt | el | s |" in text
        assert text.count("| tts |") == 3  # EN, DE, EL fixed texts
        assert "| tts | en | m-en |" in text and "| tts | de | m-de |" in text
        assert "| tts | el | speaches-ai/Kokoro-82M-v1.0-ONNX |" in text  # default fallback
        assert "Speech-only VRAM (peak - baseline): 2000 MiB" in text
        for lang in ("en", "de", "el"):
            assert (tmp_path / "audio" / f"tts-{lang}.mp3").stat().st_size == 200
    finally:
        srv.shutdown()


def test_main_exits_clearly_when_samples_are_missing(tmp_path):
    import pytest

    with pytest.raises(SystemExit) as e:
        bench.main([
            "--base-url", "http://127.0.0.1:1", "--stt-model", "s",
            "--samples-dir", str(_samples(tmp_path, ("en",))), "--out-dir", str(tmp_path / "a"),
            "--out", str(tmp_path / "r.md"),
        ])
    assert "de.wav" in str(e.value) and "el.wav" in str(e.value)
