"""scripts/speech/: the speech service's operator checks stay runnable and documented.

They are walked by hand against the live cluster, so CI cannot run them; this
guards what it can offline: every script parses, is executable, is listed in the
README, and carries no personal machine path (they locate the repo themselves).
"""
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIR = REPO / "scripts/speech"
SCRIPTS = sorted(DIR.glob("*.sh"))


def test_there_are_scripts():
    assert len(SCRIPTS) >= 5


def test_every_script_parses_and_is_executable():
    for s in SCRIPTS:
        r = subprocess.run(["bash", "-n", str(s)], capture_output=True, text=True)
        assert r.returncode == 0, f"{s.name}: {r.stderr}"
        assert os.access(s, os.X_OK), f"{s.name} is not executable"


def test_readme_lists_every_script():
    readme = (DIR / "README.md").read_text()
    for s in SCRIPTS:
        assert f"`{s.name}`" in readme, f"README does not list {s.name}"


def test_no_personal_machine_paths():
    for s in SCRIPTS + [DIR / "README.md"]:
        text = s.read_text()
        assert not re.search(r"/Users/|Docs/projects|DERIO_NET", text), f"{s.name} carries a personal path"
