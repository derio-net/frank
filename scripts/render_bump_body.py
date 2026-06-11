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

import re

GH = "https://github.com"
DEFAULT_REPO = "derio-net/agent-images"


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
        ref = f"[agent-images#{number}]({GH}/{repo}/pull/{number})"
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
