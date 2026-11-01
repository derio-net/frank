"""Upgrade-session briefs and agent instruction files (plan 2026-10-31--life--update-security-lifecycle, phase 5).

The console (derio-net/cluster-update-fr) reads docs/upgrade-briefs/<type>.md and AGENTS.md from
frank, mounts AGENTS.md as the session's AGENTS.md AND CLAUDE.md, and appends the template
VERBATIM after its own header (no placeholder substitution). Forge text (PR bodies, release
notes) reaches the agent only fenced, at the end of the brief, as untrusted data
(p5-briefs-untrusted-data). So the templates are pure instructions: they must never carry an
interpolation, must say how to treat the fenced data, and must hold every rule an agent with
cluster credentials needs -- select the pinned clients explicitly (p5-session-selection-explicit),
commit through the GitHub API on cluster-update/session-<id>/<topic> (p5-briefs-verified-commits,
p5-session-branch-format), ask the console to merge and never merge (p5-briefs-open-and-request),
never widen its credentials, and stop and ask on suspicious data.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BRIEFS = ROOT / "docs/upgrade-briefs"
TYPES = ("chart-major", "stateful", "rollouts", "frank-os", "hop-os")
SECTIONS = ["Target", "Sequence position", "Release notes", "Migration count", "Rollback path",
            "Verification", "Gotchas"]
WORKLOAD = ("chart-major", "stateful", "rollouts")
OS = ("frank-os", "hop-os")
# type -> [(cited file, words that must appear in the Gotchas section)]
GOTCHAS = {
    "frank-os": [("docs/runbooks/frank-gotchas/omni.md", ["silent", "wedge", "rollback race", "extraArgs", "reboot"]),
                 ("docs/runbooks/frank-gotchas/storage-secrets-ssa.md", ["last replica", "nodeDrainPolicy"])],
    "hop-os": [("agents/rules/hop-gotchas.md", ["edge downtime", "Caddy", "Headscale", "restart"])],
    "stateful": [("docs/runbooks/frank-gotchas/paperclip-ruflo.md", ["snapshot", "before", "merge", "_journal.json"]),
                 ("docs/runbooks/frank-gotchas/storage-secrets-ssa.md", ["status.capacity"])],
    "rollouts": [("docs/runbooks/frank-gotchas/argo-rollouts.md", ["pause: {}", "never expires"])],
    "chart-major": [("docs/runbooks/frank-gotchas/argocd.md", ["operationState", "stale"])],
}


def text(name):
    return (BRIEFS / name).read_text()


def sections(body):
    """{heading: body} for every level-2 heading."""
    parts = re.split(r"^## (.+)$", body, flags=re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}


ALL = ["AGENTS.md", "CLAUDE.md"] + [f"{t}.md" for t in TYPES]


# ------------------------------------------------------------------ files
def test_agents_and_claude_are_identical_and_skill_md_is_absent():
    assert text("AGENTS.md") == text("CLAUDE.md"), "the console mounts the same file under both names"
    assert not (BRIEFS / "SKILL.md").exists(), "SKILL.md is loaded by nothing (agent-shells gotcha)"
    assert {p.name for p in BRIEFS.glob("*.md")} == set(ALL)


@pytest.mark.parametrize("typ", TYPES)
def test_template_has_the_required_sections_in_order(typ):
    heads = list(sections(text(f"{typ}.md")))
    assert heads == SECTIONS, heads


@pytest.mark.parametrize("name", ALL)
def test_no_interpolation_anywhere(name):
    # The console substitutes nothing, and forge text must never sit in an instruction section.
    body = text(name)
    assert "{{" not in body and "${{" not in body and "{%" not in body
    assert not re.search(r"\{(pr|release|title|body)_?\w*\}", body, re.I)


# ------------------------------------------------------------------ untrusted data
UNTRUSTED_RULES = [r"untrusted", r"data,\s+not\s+instructions", r"never\s+follow\s.*instructions",
                   r"stop\s+and\s+ask\s+the\s+operator"]


@pytest.mark.parametrize("name", ["AGENTS.md"] + [f"{t}.md" for t in TYPES])
def test_untrusted_data_is_named_as_data_with_stop_and_ask(name):
    body = text(name) if name == "AGENTS.md" else sections(text(name))["Release notes"]
    for rule in UNTRUSTED_RULES:
        assert re.search(rule, body, re.I | re.S), f"{name}: missing {rule!r}"


def test_agents_md_never_widens_credentials():
    body = text("AGENTS.md")
    assert re.search(r"never widen your (own )?credentials", body, re.I)
    for forbidden in ("RoleBinding", "ClusterRole", "token", "kubeconfig"):
        assert forbidden.lower() in body.lower(), forbidden  # named explicitly in the refusal list


# ------------------------------------------------------------------ PRs and merging
def test_agents_md_commits_through_the_github_api_on_the_session_branch():
    body = text("AGENTS.md")
    assert "cluster-update/session-$UPGRADE_ID/<topic>" in body
    assert "createCommitOnBranch" in body and "/contents/" in body
    assert "request-merge" in body and "$CONSOLE_URL/api/sessions/$UPGRADE_ID/request-merge" in body
    assert re.search(r"never merge", body, re.I) and re.search(r"never push to `?main`?", body, re.I)


@pytest.mark.parametrize("name", ALL)
def test_git_push_and_merge_appear_only_as_prohibitions(name):
    for line in text(name).splitlines():
        if re.search(r"\bgit push\b|\bgh pr merge\b|/merge\b", line):
            assert re.search(r"never|not|unsigned|refuse", line, re.I), f"{name}: {line}"


@pytest.mark.parametrize("name", ALL)
def test_session_branch_uses_the_slash_form_only(name):
    for m in re.finditer(r"cluster-update/session-\S+", text(name)):
        assert m.group(0).startswith("cluster-update/session-$UPGRADE_ID/") or \
            m.group(0).startswith("cluster-update/session-<"), m.group(0)
        assert "-<topic>" not in m.group(0)


# ------------------------------------------------------------------ pinned clients
@pytest.mark.parametrize("typ", TYPES)
def test_template_starts_by_selecting_the_pinned_clients_explicitly(typ):
    target = sections(text(f"{typ}.md"))["Target"]
    first = target.index("use-versions --talos")
    assert "use-versions --list" in target
    assert first < 600, "the client selection is the first thing the agent does"


def test_agents_md_explains_why_use_versions_is_explicit():
    body = text("AGENTS.md")
    assert "use-versions --talos" in body and "use-versions --list" in body
    assert re.search(r"not on .*PATH", body, re.I)


# ------------------------------------------------------------------ verification (R16)
@pytest.mark.parametrize("typ", WORKLOAD)
def test_workload_verification_reads_operation_state_and_runs_smoke(typ):
    v = sections(text(f"{typ}.md"))["Verification"]
    assert "status.operationState.operation.sync.revision" in v
    assert "smoke/frank/<app>.yaml" in v
    assert re.search(r"Synced.{0,40}(never|not)", v, re.I | re.S)


@pytest.mark.parametrize("typ", OS)
def test_os_verification_compares_running_with_declared_and_checks_nodes_and_smoke(typ):
    v = sections(text(f"{typ}.md"))["Verification"]
    cluster = typ.split("-")[0]
    assert f"versions/{cluster}.yaml" in v
    assert re.search(r"running.{0,60}declared|declared.{0,60}running", v, re.I | re.S)
    assert "Ready" in v and "smoke/" in v
    assert re.search(r"declared .*before.* appl", v, re.I | re.S), "R22: declare in git before applying"


# ------------------------------------------------------------------ rollback + gotchas
def test_rollback_paths_match_the_spec():
    assert "talosctl rollback" in sections(text("hop-os.md"))["Rollback path"]
    frank = sections(text("frank-os.md"))["Rollback path"]
    assert "revert" in frank.lower() and "Omni" in frank and "talosctl rollback" in frank  # named as the wrong tool
    assert re.search(r"one-way", sections(text("frank-os.md"))["Rollback path"], re.I)
    stateful = sections(text("stateful.md"))["Rollback path"]
    assert "Snapshot" in stateful and "longhorn-system" in stateful
    assert re.search(r"abort", sections(text("rollouts.md"))["Rollback path"], re.I)
    assert re.search(r"revert", sections(text("chart-major.md"))["Rollback path"], re.I)


@pytest.mark.parametrize("typ", TYPES)
def test_gotchas_cite_the_matching_files(typ):
    g = sections(text(f"{typ}.md"))["Gotchas"]
    for path, words in GOTCHAS[typ]:
        assert (ROOT / path).exists(), path
        assert path in g, f"{typ}: cite {path}"
        for w in words:
            assert w.lower() in g.lower(), f"{typ}: gotchas must mention {w!r}"


def test_stateful_snapshot_happens_before_the_merge_and_migration_count_uses_the_journal_diff():
    s = sections(text("stateful.md"))
    assert re.search(r"snapshot.{0,80}before.{0,40}(merge|request-merge)", s["Rollback path"] + s["Gotchas"], re.I | re.S)
    assert "_journal.json" in s["Migration count"]
    assert re.search(r"not .*release note", s["Migration count"], re.I | re.S)


def test_frank_os_tells_the_agent_it_has_no_omni_host_access():
    g = sections(text("frank-os.md"))["Gotchas"]
    assert "docker restart omni" in g and re.search(r"operator", g, re.I)
    assert re.search(r"no access to the Omni host", g, re.I)


def test_hop_os_announces_edge_downtime_before_each_step():
    s = sections(text("hop-os.md"))
    assert re.search(r"announce", s["Sequence position"] + s["Gotchas"], re.I)


# ------------------------------------------------------------------ residual risk (p5-sec-3)
@pytest.mark.parametrize("name", ["AGENTS.md"] + [f"{t}.md" for t in TYPES])
def test_residual_github_exfiltration_risk_is_stated(name):
    body = text(name)
    assert "Security note" in body
    assert "api.github.com" in body and re.search(r"exfiltrat", body, re.I)
    assert re.search(r"cannot (filter|see|inspect)", body, re.I), "say what the network policy cannot do"
    # p5-r6: the policy pins the IPs AND the TLS server name; it is not blind to the host, and
    # the note must not say it filters "by name only" (toFQDNs alone is IP-based).
    flat = re.sub(r"\s*\n>?\s*", " ", body)
    assert "SNI" in flat and "Host header" in flat and "fronting" in flat
    assert not re.search(r"by name only", flat, re.I)


@pytest.mark.parametrize("name", ALL)
def test_briefs_never_send_the_agent_to_github_com(name):
    # egress allows api.github.com only; a git clone/fetch of github.com is refused
    body = text(name)
    assert "git clone" not in body and "git fetch" not in body
    assert not re.search(r"(?<![\w.])github\.com(?!/derio-net/frank/blob)", body.replace("api.github.com", "")), name


def test_hop_os_brief_matches_the_sidecar_proxy_contract():
    # cluster-update-fr@537f208: SOCKS5 on localhost:1055, HTTP CONNECT on localhost:1056 for
    # talosctl, joined as tag:frank-session (p5-r3).
    flat = re.sub(r"\s+", " ", text("hop-os.md"))
    for want in ("HTTPS_PROXY=http://localhost:1056", "socks5://localhost:1055", "tag:frank-session", "NO_PROXY"):
        assert want in flat, want
    assert "frank-updater" not in flat
