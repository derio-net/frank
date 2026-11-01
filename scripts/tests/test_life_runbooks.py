"""Rollback and Omni-upgrade runbooks exist and say the load-bearing things (R19, R24)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLLBACK = ROOT / "docs/runbooks/life-rollback.md"
OMNI = ROOT / "docs/runbooks/omni-upgrade.md"


def _sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*)", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def _find(sections, word):
    hits = [v for k, v in sections.items() if word.lower() in k.lower()]
    assert hits, f"no section mentioning {word!r}: {list(sections)}"
    return hits[0]


def test_rollback_has_one_section_per_path():
    s = _sections(ROLLBACK.read_text())
    for word in ("Revert", "Longhorn", "Frank Talos", "Hop Talos", "Kubernetes"):
        _find(s, word)


def test_longhorn_restore_has_exact_steps():
    body = _find(_sections(ROLLBACK.read_text()), "Longhorn")
    assert "kubectl" in body and "Longhorn UI" in body
    assert "snapshots.longhorn.io" in body and "longhorn-system" in body
    assert "scale" in body.lower()


def test_frank_talos_rollback_is_omni_revert_not_talosctl():
    body = _find(_sections(ROLLBACK.read_text()), "Frank Talos")
    assert "Omni" in body and "versions/frank.yaml" in body
    assert re.search(r"(not|never|do not)[^.\n]*talosctl rollback", body, re.I), body
    assert "talosctl rollback" not in re.sub(r"(?i)(not|never|do not)[^.\n]*talosctl rollback", "", body)


def test_hop_talos_rollback_uses_talosctl_rollback():
    body = _find(_sections(ROLLBACK.read_text()), "Hop Talos")
    assert "talosctl rollback" in body and "versions/hop.yaml" in body


def test_kubernetes_is_one_way():
    body = _find(_sections(ROLLBACK.read_text()), "Kubernetes")
    assert re.search(r"one-way|no rollback|cannot be rolled back", body, re.I)
    assert "etcd" in body.lower()


def test_omni_runbook_is_an_operator_laptop_procedure():
    text = OMNI.read_text()
    s = _sections(text)
    for word in ("Backup", "Upgrade", "Verify", "Recovery"):
        _find(s, word)
    assert "laptop" in text.lower() and "no session" in text.lower()
    assert "derio-net/willikins#528" in text
    up = _find(s, "Upgrade")
    assert "OMNI_VERSION" in up and "OMNI_IMG_TAG" in up
    assert "docker compose pull" in up and "docker compose up" in up
    ver = _find(s, "Verify")
    assert "talosconfig" in ver and re.search(r"rotat", ver, re.I)
    assert "omnictl" in ver
    rec = _find(s, "Recovery")
    assert "scripts/omni-legacy-recovery/" in rec
    assert "docker restart omni" in rec


def test_omni_version_anchor_is_what_the_runbook_edits():
    env = (ROOT / "omni/omni/omni.env.template").read_text()
    assert re.search(r"^OMNI_VERSION=v\d", env, re.M) and re.search(r"^OMNI_IMG_TAG=v\d", env, re.M)
    assert "omni/omni/omni.env.template" in OMNI.read_text()


def test_runbook_links_resolve():
    for doc in (ROLLBACK, OMNI):
        for target in re.findall(r"\]\((?!https?:)([^)#]+)\)", doc.read_text()):
            assert (doc.parent / target).exists(), (doc.name, target)
