"""Tests for scripts/render_bump_body.py.

The renderer turns a `bump` dict (old/new/vk-remote SHAs + a list of
upstream agent-images PRs) into the markdown body for the automated
agent-images bump PR. `render()` is pure (no network), so these tests
feed crafted dicts and assert on the markdown.

Contract source of truth:
docs/superpowers/specs/2026-06-11-agent-images-bump-context-design.md
"""
import pytest

import scripts.render_bump_body as rbb
from scripts.render_bump_body import render

REPO = "derio-net/agent-images"
OLD = "439a6ef7e269401062b9be1fff5e6b972acc9f1f"
NEW = "8606edfa9c104460fec5805c476cff7162da399c"


def pr(
    number=88,
    title="feat(kali): rotate remote-control sessions past max uptime + debug logs",
    author="YiannisDermitzakis",
    paths=("kali/wrap-claude.py",),
    summary="Rotates the wrap-claude session once it exceeds max uptime.",
    sha=NEW,
):
    return {
        "number": number,
        "title": title,
        "author": author,
        "paths": list(paths),
        "summary": summary,
        "sha": sha,
    }


def bump(old=OLD, new=NEW, vkr="7cebcbb", prs=None, repo=REPO):
    return {
        "old": old,
        "new": new,
        "vkr": vkr,
        "repo": repo,
        "prs": [pr()] if prs is None else list(prs),
    }


# --- header / compare line -------------------------------------------------

def test_header_present():
    assert "## agent-images bump" in render(bump())


def test_compare_line_uses_short_shas_and_full_url():
    out = render(bump())
    assert "`439a6ef` → `8606edf`" in out
    assert f"https://github.com/{REPO}/compare/{OLD}...{NEW}" in out


# --- single PR bullet (Q2 depth) -------------------------------------------

def test_single_pr_bullet_full_shape():
    out = render(bump())
    assert "### Upstream changes (1 PR)" in out
    assert f"[agent-images#88](https://github.com/{REPO}/issues/88)" in out
    assert "feat(kali): rotate remote-control sessions past max uptime + debug logs" in out
    assert "(@YiannisDermitzakis)" in out
    assert "> Rotates the wrap-claude session once it exceeds max uptime." in out


def test_title_strips_trailing_pr_number():
    out = render(bump(prs=[pr(title="feat(kali): widget (#88)")]))
    assert "feat(kali): widget" in out
    assert "(#88)" not in out  # number is shown as the link ref, not in the title


# --- vk-remote line (Q3: unchanged) ----------------------------------------

def test_vkr_line_present_when_set():
    assert "**vk-remote:** `7cebcbb`" in render(bump())


def test_vkr_line_absent_when_empty():
    assert "vk-remote" not in render(bump(vkr=""))


# --- ordering + plural -----------------------------------------------------

def test_multi_pr_newest_first_and_plural_header():
    out = render(bump(prs=[pr(number=80, sha="aaa1111"), pr(number=88, sha="bbb2222")]))
    assert "### Upstream changes (2 PRs)" in out
    assert out.index("#88") < out.index("#80"), "newest PR must render first"


# --- docs-only filter (Q1) -------------------------------------------------

def test_docs_only_pr_filtered_out_and_excluded_from_count():
    out = render(bump(prs=[
        pr(number=90, paths=["docs/runbooks/x.md"], sha="ddd"),
        pr(number=88, paths=["kali/wrap-claude.py"], sha="eee"),
    ]))
    assert "### Upstream changes (1 PR)" in out
    assert "#90" not in out
    assert "#88" in out


def test_mixed_paths_pr_is_kept():
    out = render(bump(prs=[pr(number=91, paths=["docs/a.md", "kali/b.py"])]))
    assert "#91" in out
    assert "### Upstream changes (1 PR)" in out


def test_all_docs_only_range_shows_note_not_count():
    out = render(bump(prs=[
        pr(number=90, paths=["docs/a.md"], sha="ddd"),
        pr(number=92, paths=["docs/b.md"], sha="fff"),
    ]))
    assert "_No image-affecting changes (docs-only upstream)._" in out
    assert "### Upstream changes (" not in out
    # compare link still shown
    assert f"https://github.com/{REPO}/compare/" in out


# --- optional pieces -------------------------------------------------------

def test_empty_body_omits_summary_blockquote():
    out = render(bump(prs=[pr(summary="")]))
    assert "#88" in out
    assert "\n  > " not in out


def test_author_null_omits_at_mention():
    out = render(bump(prs=[pr(author=None)]))
    assert "#88" in out
    assert "(@" not in out


def test_commit_without_pr_number_renders_short_sha_link():
    out = render(bump(prs=[pr(number=None, sha="abc1234deadbeef", summary="")]))
    assert f"[abc1234](https://github.com/{REPO}/commit/abc1234deadbeef)" in out
    assert "#" not in out.split("### Upstream changes")[1].split("**vk-remote")[0]


# --- old == new edge -------------------------------------------------------

def test_old_equals_new_shows_unchanged_note_no_compare():
    out = render(bump(old=NEW, new=NEW, prs=[]))
    assert "_agent-images unchanged._" in out
    assert "### Upstream changes" not in out
    assert "compare" not in out
    assert "**vk-remote:** `7cebcbb`" in out  # vk-remote line still shown


# --- _summary_from_message: derive the "what it did" from the commit body --

def test_summary_takes_first_paragraph_of_commit_body():
    # Real agent-images 8606edf shape: subject, blank, first paragraph, blank, more.
    msg = (
        "feat(kali): rotate remote-control sessions past max uptime + debug logs (#88)\n"
        "\n"
        "The 2026-05-23 incident: a 5d4h-old claude remote-control parent looked\n"
        "healthy while every App-attach child crashed.\n"
        "\n"
        "session-manager.sh now refuses to treat a session as 'already running'.\n"
    )
    s = rbb._summary_from_message(msg)
    assert s.startswith("The 2026-05-23 incident:")
    assert "every App-attach child crashed." in s  # first paragraph joined
    assert "already running" not in s  # second paragraph excluded


def test_summary_empty_for_subject_only_commit():
    assert rbb._summary_from_message("chore: bump deps") == ""


def test_summary_truncates_long_paragraph():
    s = rbb._summary_from_message("subj\n\n" + "x" * 500)
    assert len(s) == 200 and s.endswith("…")


# --- main(): best-effort fallback (enrichment never blocks a bump) ---------

def _raise(*_a, **_k):
    raise RuntimeError("gh unavailable")


def test_main_falls_back_to_legacy_on_collect_error(monkeypatch, capsys):
    monkeypatch.setattr(rbb, "collect", _raise)
    rc = rbb.main(["--old", OLD, "--new", NEW, "--vkr", "7cebcbb"])
    assert rc == 0
    assert capsys.readouterr().out == f"agent-images: `{NEW}`\nvk-remote: `7cebcbb`\n"


def test_main_fallback_when_old_missing_does_not_call_collect(monkeypatch, capsys):
    monkeypatch.setattr(rbb, "collect", _raise)  # would raise AssertionError-style if reached
    rc = rbb.main(["--old", "", "--new", NEW, "--vkr", ""])
    assert rc == 0
    # no vk-remote line when vkr empty
    assert capsys.readouterr().out == f"agent-images: `{NEW}`\n"


def test_main_old_equals_new_renders_unchanged_note(monkeypatch, capsys):
    # old==new must short-circuit collect() and render the note, not fall back.
    monkeypatch.setattr(rbb, "collect", _raise)
    rc = rbb.main(["--old", NEW, "--new", NEW, "--vkr", "7cebcbb"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "_agent-images unchanged._" in out
    assert "**vk-remote:** `7cebcbb`" in out
