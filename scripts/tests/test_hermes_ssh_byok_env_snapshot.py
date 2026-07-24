"""Guard the BYOK-secret env snapshot in Frank's hermes ssh sidecar (frank#688).

The two-container hermes-agent-shell pod runs terminal access in a thin `ssh`
sidecar (image ghcr.io/derio-net/hermes-agent-shell-ssh) that has NO s6/init:
its entrypoint exec's `/usr/sbin/sshd`, so sshd becomes PID 1. OpenSSH
overwrites its argv/environ region with the process title
("sshd: … [listener] …"), so `/proc/1/environ` returns proctitle bytes, not the
environment. The 35-…-byok-env.sh profile.d shim therefore reads junk and
exports nothing — `hermes` launched from an SSH/Mosh login shell has no LiteLLM
auth (OPENAI_BASE_URL / OPENAI_API_KEY).

The sibling frank#686/#689 fix handled the STATIC FR_ISOLATION_TARGET with a
literal fallback export. The DYNAMIC BYOK secrets can't be hardcoded, so the
fix (issue candidate 1, no image rebuild) is:

  1. the ssh container overrides its `command` to snapshot the BYOK secrets from
     the container env — which the wrapper process DOES have — into a
     memory-backed tmpfs file, THEN `exec`s the image entrypoint (so host-key +
     authorized_keys prep still run);
  2. that file lives on an emptyDir `medium: Memory` volume (secrets never touch
     disk, wiped on restart), writable by the UID-1000 sidecar via fsGroup;
  3. the byok-env shim reads the snapshot file for the dynamic vars, as a
     fallback after /proc/1/environ (which still works where an init preserves
     environ, e.g. secure-agent-pod's kali under s6).

All three are load-bearing, so this test locks them.
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
HERMES_DEPLOY = REPO / "apps/hermes-agent-shell/manifests/deployment.yaml"
HERMES_SHIM_CM = REPO / "apps/hermes-agent-shell/manifests/configmap-byok-env.yaml"

# The tmpfs snapshot the ssh sidecar writes at start and the shim reads at login.
SNAPSHOT_FILE = "/run/hermes-env/byok"
SNAPSHOT_DIR = "/run/hermes-env"
# The image entrypoint the command wrapper MUST exec (agent-images
# hermes-agent-shell-ssh/rootfs) — dropping it would skip host-key +
# authorized_keys prep and break sshd.
ENTRYPOINT = "/usr/local/bin/hermes-ssh-sidecar-entrypoint.sh"
# The dynamic secrets that /proc/1/environ can't deliver in this sidecar.
BYOK_VARS = ("OPENAI_BASE_URL", "OPENAI_API_KEY")


def _load(path: Path):
    return yaml.safe_load(path.read_text())


def _containers(deploy_path: Path) -> dict:
    spec = _load(deploy_path)["spec"]["template"]["spec"]
    return {c["name"]: c for c in spec["containers"]}


def _ssh_container() -> dict:
    return _containers(HERMES_DEPLOY)["ssh"]


def _command_script(container: dict) -> str:
    """The full shell text the container runs: command + args joined."""
    return "\n".join((container.get("command") or []) + (container.get("args") or []))


def test_ssh_command_snapshots_byok_before_exec_entrypoint():
    """The ssh container dumps the BYOK secrets to the tmpfs snapshot, then
    exec's the image entrypoint (never raw sshd — that would drop key prep)."""
    ssh = _ssh_container()
    script = _command_script(ssh)

    assert script, "ssh container must override command to snapshot the env before sshd"
    # Redirects the dynamic secrets to the snapshot file.
    assert SNAPSHOT_FILE in script, (
        f"ssh command must write the BYOK env snapshot to {SNAPSHOT_FILE}"
    )
    for var in BYOK_VARS:
        assert var in script, (
            f"ssh command must capture {var} into the snapshot (grep filter)"
        )
    # Hands off to the image entrypoint (keeps host-key/authorized_keys prep),
    # not raw sshd.
    assert f"exec {ENTRYPOINT}" in script, (
        f"ssh command must `exec {ENTRYPOINT}` after the snapshot — exec'ing "
        "sshd directly would skip the entrypoint's host-key + authorized_keys prep"
    )
    assert "/usr/sbin/sshd" not in script, (
        "ssh command must delegate to the entrypoint, not launch sshd itself "
        "(the entrypoint owns the sshd invocation + first-boot prep)"
    )


def test_ssh_snapshot_lives_on_memory_emptydir():
    """The snapshot dir is a memory-backed emptyDir — secrets stay in RAM, and
    the UID-1000 sidecar can write it (fsGroup)."""
    ssh = _ssh_container()
    mounts = [m for m in ssh.get("volumeMounts", []) if m.get("mountPath") == SNAPSHOT_DIR]
    assert mounts, f"ssh container must mount a volume at {SNAPSHOT_DIR}"
    vol_name = mounts[0]["name"]

    pod_spec = _load(HERMES_DEPLOY)["spec"]["template"]["spec"]
    volumes = {v["name"]: v for v in pod_spec.get("volumes", [])}
    assert vol_name in volumes, f"snapshot mount references undefined volume {vol_name!r}"
    emptydir = volumes[vol_name].get("emptyDir")
    assert emptydir is not None, (
        f"volume {vol_name!r} must be an emptyDir so the snapshot is non-persistent"
    )
    assert emptydir.get("medium") == "Memory", (
        f"volume {vol_name!r} must be emptyDir medium: Memory — BYOK secrets must "
        "not land on disk"
    )


def test_shim_reads_snapshot_for_byok_vars():
    """The byok-env profile.d shim reads the tmpfs snapshot for the dynamic
    BYOK vars (the /proc/1/environ loop is vacuous when sshd is PID 1)."""
    cm = _load(HERMES_SHIM_CM)
    assert cm["metadata"]["name"] == "hermes-agent-shell-env"
    script = cm["data"]["35-hermes-agent-shell-byok-env.sh"]

    assert SNAPSHOT_FILE in script, (
        f"the shim must read the BYOK snapshot at {SNAPSHOT_FILE} — /proc/1/environ "
        "is proctitle junk when sshd is PID 1, so it is the only source of the "
        "dynamic secrets in the ssh sidecar"
    )
    for var in BYOK_VARS:
        assert var in script, f"the shim must export {var}"
