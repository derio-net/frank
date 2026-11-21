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


def _parse_multipart(content_type, body):
    """Parse a multipart/form-data body with the stdlib email parser (no cgi)."""
    from email.parser import BytesParser
    from email.policy import HTTP

    msg = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
    )
    out = {}
    for part in msg.iter_parts():
        out[part.get_param("name", header="content-disposition")] = (
            part.get_filename(),
            part.get_payload(decode=True),
        )
    return out


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _fail(self, exc):
        # surface handler-thread errors as test failures (see _stop)
        self.server.errors.append(exc)
        self.send_error(500)

    def do_POST(self):
        try:
            self._handle()
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        mode = self.server.mode
        if mode == "http500":
            self.send_error(500)
            return
        if self.path == "/v1/audio/transcriptions":
            fields = _parse_multipart(self.headers["Content-Type"], body)
            assert {"model", "language", "file"} <= set(fields), sorted(fields)
            lang = fields["language"][1].decode()
            assert lang in ("en", "de", "el"), lang
            self.server.seen_langs.append(lang)
            assert fields["file"][0] == f"{lang}.wav", fields["file"][0]
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
            if mode == "empty-tts":
                self.wfile.write(b"0\r\n\r\n")
                return
            time.sleep(0.3)  # time to first audio
            for chunk in (b"a" * 100, b"b" * 100):
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
                time.sleep(0.1)
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.send_error(404)


def _server(mode="ok"):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    srv.mode = mode
    srv.errors = []
    srv.seen_langs = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _stop(srv):
    srv.shutdown()
    assert not srv.errors, f"fake server handler failed: {srv.errors!r}"


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
        assert 0 < stt["value"] < 1.0  # server sleeps 0.2 s for 2.0 s of audio: RTF ~0.1
        assert srv.seen_langs == ["en"]  # the language field reached the server
        tts = bench.bench_tts(base, "tts-model", "voice", "el", "γειά σου")
        assert tts["metric"] == "ttfa_s"
        assert tts["value"] > 0.1  # first chunk after ~0.3 s (generous lower bound)
        assert tts["seconds"] > tts["value"]  # total includes the later chunks
        assert tts["bytes"] == 200
    finally:
        _stop(srv)


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
        _stop(srv)


def test_main_exits_clearly_when_samples_are_missing(tmp_path):
    import pytest

    with pytest.raises(SystemExit) as e:
        bench.main([
            "--base-url", "http://127.0.0.1:1", "--stt-model", "s",
            "--samples-dir", str(_samples(tmp_path, ("en",))), "--out-dir", str(tmp_path / "a"),
            "--out", str(tmp_path / "r.md"),
        ])
    assert "de.wav" in str(e.value) and "el.wav" in str(e.value)


def test_unknown_tts_language_key_exits_clearly(tmp_path):
    import pytest

    with pytest.raises(SystemExit) as e:
        bench.main([
            "--base-url", "http://127.0.0.1:1", "--stt-model", "s", "--tts", "FR=m:v",
            "--samples-dir", str(_samples(tmp_path)), "--out-dir", str(tmp_path / "a"),
            "--out", str(tmp_path / "r.md"),
        ])
    assert "fr" in str(e.value) and "not benchmarked" in str(e.value)


def test_empty_voice_in_tts_spec_is_rejected():
    import pytest

    for bad in ("EN=model:", "EN=:voice", "EN=", "=m:v"):
        with pytest.raises(ValueError):
            bench.parse_tts_specs([bad])


def test_non_200_response_exits_clearly(tmp_path):
    import pytest

    srv, base = _server("http500")
    try:
        with pytest.raises(SystemExit) as e:
            bench.main([
                "--base-url", base, "--stt-model", "s",
                "--samples-dir", str(_samples(tmp_path)), "--out-dir", str(tmp_path / "a"),
                "--out", str(tmp_path / "r.md"),
            ])
        assert "benchmark failed" in str(e.value)
    finally:
        _stop(srv)


def test_empty_tts_body_is_an_error_not_a_zero_row():
    import pytest

    srv, base = _server("empty-tts")
    try:
        with pytest.raises(RuntimeError, match="empty body"):
            bench.bench_tts(base, "m", "v", "en", "text")
    finally:
        _stop(srv)


def test_garbled_or_empty_smi_log_yields_no_peak(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    garbled = tmp_path / "garbled.csv"
    garbled.write_text("N/A\nnot a number\n[Not Supported]\n")
    assert bench.peak_vram_mib(empty) is None
    assert bench.peak_vram_mib(garbled) is None


def test_baseline_above_peak_is_flagged_not_reported_negative():
    rows = [{"kind": "stt", "lang": "en", "model": "m", "seconds": 1.0, "metric": "rtf", "value": 0.1}]
    table = bench.render_table(rows, peak_vram_mib=9000, baseline_mib=10000)
    assert "-1000" not in table
    assert "WARNING: baseline (10000 MiB) exceeds peak (9000 MiB)" in table
    assert "Speech-only VRAM (peak - baseline): n/a" in table


def test_base_url_scheme_is_validated(tmp_path):
    import pytest

    samples = _samples(tmp_path)
    for bad in ("file:///etc/passwd", "ftp://x", "speech.local:8000"):
        with pytest.raises(SystemExit) as e:
            bench.main([
                "--base-url", bad, "--stt-model", "s",
                "--samples-dir", str(samples), "--out-dir", str(tmp_path / "a"),
                "--out", str(tmp_path / "r.md"),
            ])
        assert "http" in str(e.value)


def test_multipart_escapes_names_and_filenames(tmp_path):
    import pytest

    f = tmp_path / 'a"b\r\nc.wav'
    f.write_bytes(b"x")
    body, ctype = bench._multipart({"model": "m"}, "file", f)
    head = body.split(b"filename=")[1].split(b"\r\n")[0]
    assert b'"' not in head[1:-1] and b"%22" in head and b"%0D%0A" in head
    for bad in ('x"; name="y', "a\nb", ""):
        with pytest.raises(ValueError):
            bench._multipart({bad: "v"}, "file", f)
    with pytest.raises(ValueError):
        bench._multipart({"model": "m\r\n--evil"}, "file", f)
