#!/usr/bin/env python3
"""Render the PR body for the automated agent-images bump.

The `agent-images-bump.yml` workflow opens a PR each time agent-images (and/or
vk-remote) advances. This script turns the old/new agent-images SHAs (+ the
vk-remote short SHA) into a body that names the upstream agent-images PR(s) the
bump pulls in — number, title, author, a one-line summary, and a compare link —
so a reviewer understands what changed and why without leaving the PR.

Layers:
  - render(bump)            pure formatter; all inclusion logic, no network.
  - collect(old,new,vkr)    gh-api lookup that builds the `bump` dict (added in
                            phase 2).
  - main()                  argv -> collect -> render, with a best-effort
                            fallback to the legacy two-line body so a gh failure
                            never blocks a bump (added in phase 2).

Design: docs/superpowers/specs/2026-06-11-agent-images-bump-context-design.md
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess

GH = "https://github.com"
DEFAULT_REPO = "derio-net/agent-images"
PR_NUM_RE = re.compile(r"\(#(\d+)\)\s*$")


def _short(sha: str | None) -> str:
    return (sha or "")[:7]


def _is_docs_only(pr: dict) -> bool:
    """A PR is bump-irrelevant when every changed path is under docs/.

    Mirrors agent-images build.yaml `paths-ignore: docs/**`: a docs-only push
    rebuilds nothing and never triggers a bump, so it must not be listed as a
    change. An empty path list (unknown) is conservatively kept.
    """
    paths = pr.get("paths") or []
    return bool(paths) and all(p.startswith("docs/") for p in paths)


def _strip_pr_suffix(title: str | None) -> str:
    """Drop a trailing `(#NN)` — the number is shown as the link ref."""
    return re.sub(r"\s*\(#\d+\)\s*$", "", title or "").strip()


def _bullet(pr: dict, repo: str) -> str:
    number = pr.get("number")
    if number:
        # /issues/<n> is GitHub's canonical reference form: it shows the issue,
        # or 302-redirects to the PR when <n> is one. A squash subject's (#NN)
        # may reference either (e.g. agent-images 8606edf -> issue #88), so a
        # hard-coded /pull/<n> would 404 on an issue ref.
        ref = f"[agent-images#{number}]({GH}/{repo}/issues/{number})"
    else:
        sha = pr.get("sha") or ""
        ref = f"[{_short(sha)}]({GH}/{repo}/commit/{sha})"
    author = pr.get("author")
    at = f" (@{author})" if author else ""
    line = f"- {ref} — {_strip_pr_suffix(pr.get('title'))}{at}"
    summary = (pr.get("summary") or "").strip()
    if summary:
        line += f"\n  > {summary}"
    return line


def render(bump: dict) -> str:
    """Build the markdown PR body from a `bump` dict. Pure, no network."""
    repo = bump.get("repo") or DEFAULT_REPO
    old = bump.get("old") or ""
    new = bump.get("new") or ""
    vkr = bump.get("vkr") or ""

    lines = ["## agent-images bump", ""]

    if old and new and old == new:
        lines.append("_agent-images unchanged._")
    else:
        lines.append(
            f"`{_short(old)}` → `{_short(new)}` · "
            f"[compare]({GH}/{repo}/compare/{old}...{new})"
        )
        lines.append("")
        kept = [p for p in (bump.get("prs") or []) if not _is_docs_only(p)]
        if kept:
            n = len(kept)
            lines.append(f"### Upstream changes ({n} PR{'s' if n != 1 else ''})")
            for p in reversed(kept):  # prs arrive oldest->newest; show newest first
                lines.append(_bullet(p, repo))
        else:
            lines.append("_No image-affecting changes (docs-only upstream)._")

    if vkr:
        lines.append("")
        lines.append(f"**vk-remote:** `{vkr}`")

    return "\n".join(lines).rstrip() + "\n"


# --- collection (network) --------------------------------------------------


def _gh_json(path: str):
    """GET a GitHub REST path via `gh api`, parsed as JSON. Raises on failure."""
    out = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def _summary_from_message(message: str | None, limit: int = 200) -> str:
    """First meaningful paragraph of a commit body (the subject line dropped).

    GitHub copies the PR description into the squash commit body, so this is
    the reliable "what it did" — no PR fetch, no issue-vs-PR ambiguity. Leading
    blanks / headings / HTML comments are skipped; the first paragraph's lines
    are joined and truncated.
    """
    para: list[str] = []
    for raw in (message or "").splitlines()[1:]:  # [1:] drops the subject
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            if para:
                break
            continue
        para.append(line)
    text = " ".join(para).strip()
    return (text[: limit - 1] + "…") if len(text) > limit else text


def collect(old: str, new: str, vkr: str, repo: str = DEFAULT_REPO) -> dict:
    """Build a `bump` dict from the agent-images `old...new` range via gh api.

    Squash-merge means one commit per PR. Title/author/summary all come from
    the commit (compare gives the full message + author; `/commits/{sha}` gives
    the changed files). PRs arrive oldest->newest (as `compare` returns them);
    `render()` reverses to newest-first. Raises on any gh failure so `main()`
    can fall back.
    """
    cmp = _gh_json(f"/repos/{repo}/compare/{old}...{new}")
    prs = []
    for c in cmp.get("commits", []):
        sha = c.get("sha", "")
        message = (c.get("commit") or {}).get("message") or ""
        subject = message.splitlines()[0] if message else ""
        author = (c.get("author") or {}).get("login")
        paths = [
            f.get("filename", "")
            for f in _gh_json(f"/repos/{repo}/commits/{sha}").get("files", [])
        ]
        m = PR_NUM_RE.search(subject)
        prs.append(
            {
                "number": int(m.group(1)) if m else None,
                "title": subject,
                "author": author,
                "paths": paths,
                "summary": _summary_from_message(message),
                "sha": sha,
            }
        )
    return {"old": old, "new": new, "vkr": vkr, "repo": repo, "prs": prs}


# --- CLI -------------------------------------------------------------------


def legacy_body(new: str, vkr: str) -> str:
    """The original two-line body — the best-effort fallback."""
    body = f"agent-images: `{new}`"
    if vkr:
        body += f"\nvk-remote: `{vkr}`"
    return body + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render the agent-images bump PR body.")
    ap.add_argument("--old", default="", help="previous agent-images SHA (pre-bump pin)")
    ap.add_argument("--new", default="", help="new agent-images SHA")
    ap.add_argument("--vkr", default="", help="vk-remote short SHA (optional)")
    args = ap.parse_args(argv)
    old, new, vkr = args.old, args.new, args.vkr

    try:
        if not old or not new:
            raise ValueError("missing old/new sha")
        if old == new:
            bump = {"old": old, "new": new, "vkr": vkr, "repo": DEFAULT_REPO, "prs": []}
        else:
            bump = collect(old, new, vkr)
        body = render(bump)
    except Exception:
        body = legacy_body(new, vkr)

    print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
