"""The bump must replace a digest pin with the NEW tag's digest, never keep the old one (frank#965)."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_images_repin as r  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OLD, NEW = "1f89319519ae19e930ec5ba2a33dda0b6c2c0140", "dbdf5f69" + "0" * 32
OLD_D, NEW_D = "sha256:" + "8dcb0ece" + "a" * 56, "sha256:" + "70d1092f" + "b" * 56


def fake(img, sha):
    assert (img, sha) == ("upgrade-session", NEW)
    return NEW_D


def test_digest_pinned_ref_gets_the_new_digest_not_the_old_one():
    t = f"image: ghcr.io/derio-net/upgrade-session:{OLD}@{OLD_D}\nSESSION_IMAGE=ghcr.io/derio-net/upgrade-session:{OLD}@{OLD_D}\n"
    out = r.repin(t, "upgrade-session", NEW, fake)
    assert OLD_D not in out and OLD not in out
    assert out.count(f"upgrade-session:{NEW}@{NEW_D}") == 2


def test_tag_only_ref_keeps_todays_behaviour_and_never_resolves():
    def boom(*a):
        raise AssertionError("must not hit the registry for a tag-only ref")
    out = r.repin(f"image: ghcr.io/derio-net/upgrade-session:{OLD}\n", "upgrade-session", NEW, boom)
    assert out == f"image: ghcr.io/derio-net/upgrade-session:{NEW}\n"


def test_mixed_refs_and_other_images_untouched():
    t = f"a: ghcr.io/derio-net/infra-shell:{OLD}@{OLD_D}\nb: ghcr.io/derio-net/upgrade-session:{OLD}\n"
    out = r.repin(t, "upgrade-session", NEW, fake)
    assert f"infra-shell:{OLD}@{OLD_D}" in out and f"upgrade-session:{NEW}\n" in out


@pytest.mark.parametrize("bad", ["", "sha256:short", None, "latest"])
def test_unresolvable_digest_fails_instead_of_keeping_the_old_one(bad):
    with pytest.raises(r.DigestUnresolved):
        r.repin(f"ghcr.io/derio-net/upgrade-session:{OLD}@{OLD_D}", "upgrade-session", NEW, lambda *a: bad)


def test_cli_exits_nonzero_and_leaves_the_file_when_resolution_fails(tmp_path):
    f = tmp_path / "d.yaml"
    f.write_text(f"image: ghcr.io/derio-net/upgrade-session:{OLD}@{OLD_D}\n")
    p = subprocess.run([sys.executable, str(REPO / "scripts/agent_images_repin.py"), "upgrade-session", NEW, str(f)],
                       capture_output=True, text=True, env={"PATH": "/nonexistent"})
    assert p.returncode != 0
    assert OLD_D in f.read_text()


def test_workflow_uses_the_script_not_a_tag_only_sed():
    wf = (REPO / ".github/workflows/agent-images-bump.yml").read_text()
    assert "scripts/agent_images_repin.py" in wf
    assert not re.search(r"sed -i \"s\|ghcr\.io/derio-net/\$img", wf), "tag-only sed would keep an old @sha256"
    assert "docker/login-action" in wf or "docker login ghcr.io" in wf
