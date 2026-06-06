"""fetch-text ConfigMap script — functional tests via --stdin mode.

The script under test is the exact bytes the ConfigMap ships
(apps/hermes-agent-shell/manifests/configmap-fetch-text.yaml, key
``fetch-text``): the test extracts it from the YAML and runs it as a
subprocess, so manifest and behavior cannot drift apart.
"""
import pathlib
import subprocess
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CM = REPO / "apps/hermes-agent-shell/manifests/configmap-fetch-text.yaml"

FIXTURE = """<html><head><title>Frank Post</title>
<script>var hidden = 'SCRIPT_MUST_NOT_LEAK';</script>
<style>.x{color:red}</style></head>
<body><nav>skip-nav</nav><h1>Hermes Shell</h1>
<p>The cluster runs a 64k context variant now.</p></body></html>"""


def _script(tmp_path):
    doc = yaml.safe_load(CM.read_text())
    script = doc["data"]["fetch-text"]
    p = tmp_path / "fetch-text"
    p.write_text(script)
    return p


def _run(tmp_path, *args):
    return subprocess.run(
        [sys.executable, str(_script(tmp_path)), *args],
        input=FIXTURE, capture_output=True, text=True, timeout=30,
    )


def test_extracts_title_and_body(tmp_path):
    r = _run(tmp_path, "--stdin")
    assert r.returncode == 0, r.stderr
    assert "Frank Post" in r.stdout
    assert "64k context variant" in r.stdout


def test_strips_script_and_style(tmp_path):
    r = _run(tmp_path, "--stdin")
    assert "SCRIPT_MUST_NOT_LEAK" not in r.stdout
    assert "color:red" not in r.stdout


def test_caps_output(tmp_path):
    # Fixture body text is ~65 chars; cap below that to force truncation.
    r = _run(tmp_path, "--stdin", "--max-chars", "30")
    assert "truncated at 30 chars" in r.stdout
    # body is cut: the tail of the fixture text must not survive the cap
    assert "variant now" not in r.stdout
