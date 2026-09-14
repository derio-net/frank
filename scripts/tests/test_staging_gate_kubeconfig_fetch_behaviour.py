"""Execute the fetch-kubeconfig step's real script (plan 2026-06-15-staging-vcluster-gate,
phase 9), not just inspect its text.

The step is `#!/bin/sh; umask 077; kubectl -n vcluster-staging get secret vc-staging-gate -o
jsonpath='{.data.config}' | base64 -d > "$dest"`. Structural tests already assert the umask
and the kubectl invocation appear in the source; this proves the PIPE actually decodes into a
file with the RIGHT permissions and that nothing is echoed to stdout/stderr along the way (the
one property a text-scan literally cannot check -- absence of output). The script honours an
undocumented `VC_KUBECONFIG_PATH` env override (falling back to the real
`/tekton/home/vc.kubeconfig` in production) purely so this test doesn't have to fake that
absolute path.
"""

import os
import stat
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / "apps/staging-gate/tekton/tasks.yaml"

FAKE_KUBECONFIG = "apiVersion: v1\nkind: Config\nusers:\n  - name: gate\n"


def _fetch_kubeconfig_script() -> str:
    for doc in yaml.safe_load_all(TASKS.read_text()):
        if doc and doc.get("kind") == "Task" and doc["metadata"]["name"] == "staging-gate-run-smoke":
            step = next(s for s in doc["spec"]["steps"] if s["name"] == "fetch-kubeconfig")
            return step["script"]
    raise AssertionError("staging-gate-run-smoke's fetch-kubeconfig step not found")


_STUB_KUBECTL = """#!/bin/sh
set -eu
if [ "$1" = "-n" ] && [ "$2" = "vcluster-staging" ] && [ "$3" = "get" ] && [ "$4" = "secret" ] \\
   && [ "$5" = "vc-staging-gate" ]; then
  printf '%s' "$FAKE_SECRET_B64"
  exit 0
fi
echo "stub kubectl: unhandled args: $*" >&2
exit 1
"""


def _run(tmp_path: Path) -> tuple[subprocess.CompletedProcess, Path]:
    import base64

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "kubectl"
    stub.write_text(_STUB_KUBECTL)
    stub.chmod(0o755)

    dest = tmp_path / "vc.kubeconfig"
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "VC_KUBECONFIG_PATH": str(dest),
        "FAKE_SECRET_B64": base64.b64encode(FAKE_KUBECONFIG.encode()).decode(),
    }
    result = subprocess.run(
        ["sh", "-c", _fetch_kubeconfig_script()], env=env, capture_output=True, text=True, timeout=30
    )
    return result, dest


def test_fetches_and_decodes_the_kubeconfig(tmp_path):
    result, dest = _run(tmp_path)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert dest.read_text() == FAKE_KUBECONFIG


def test_writes_the_file_under_umask_077(tmp_path):
    _, dest = _run(tmp_path)

    mode = stat.S_IMODE(dest.stat().st_mode)
    assert mode == 0o600, f"expected 0600 under umask 077, got {oct(mode)}"


def test_never_echoes_the_kubeconfig_content(tmp_path):
    result, _ = _run(tmp_path)

    assert "apiVersion" not in result.stdout and "apiVersion" not in result.stderr, (
        f"the kubeconfig content must never appear on stdout/stderr:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert FAKE_KUBECONFIG not in result.stdout and FAKE_KUBECONFIG not in result.stderr
