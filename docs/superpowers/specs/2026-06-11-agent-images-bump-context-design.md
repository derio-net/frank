# Spec — Enrich the agent-images bump PR body with upstream context

**Date:** 2026-06-11
**Layer:** `cicd`
**Status:** draft
**Slug:** `agent-images-bump-context`

## Implementation Plans

| Plan | Target repo | Slug | Status |
|------|-------------|------|--------|
| 2026-06-11-agent-images-bump-context | `derio-net/frank` | `2026-06-11-agent-images-bump-context` | — |

## Problem

The `agent-images-bump.yml` workflow opens an automated PR every time
agent-images (and/or vk-remote) advances. Today the PR body is two opaque
lines:

```
agent-images: `8606edfa9c104460fec5805c476cff7162da399c`
vk-remote: `7cebcbb`
```

A reviewer (human or agent) merging that PR has **no idea what changed or
why** without manually diffing two SHAs in another repo. The bump is a
black box: it moves five deployed images (`secure-agent-kali`, `vk-local`,
`paperclip-shell`, `ruflo-server`, `ruflo-shell`) to a new agent-images
commit, but the body never names the upstream PR(s) that produced it.

> **Scope note — "issue" means the PR.** The operator's request says
> "chore gh issue", but the workflow only ever opens a **pull request**
> (`gh pr create`, line 112) — it creates no GitHub issue. This spec
> enriches that PR's body. No issue is involved.

## Goal

Make the bump PR body self-explanatory: name the upstream agent-images
PR(s) the bump pulls in, with a one-line summary of each, plus a compare
link — so a reviewer understands *what* is updated and *why* without
leaving the PR.

## Non-goals

- **Not** enriching vk-remote (operator decision Q3). vk-remote resolves to
  a bare GHCR short-SHA from a separate image with no clean PR mapping; it
  stays the minimal `vk-remote: <sha>` line it is today.
- **Not** changing the commit message, branch naming, or trigger logic.
- **Not** adding an LLM summarization step. The "why" is the upstream PR's
  conventional-commit title + the first line of its body — deterministic,
  no model calls in CI.
- **Not** gating the bump on enrichment. If the upstream lookup fails for
  any reason, the PR must still open with the legacy minimal body.

## Operator decisions (from the batched Q&A)

| # | Decision | Choice |
|---|----------|--------|
| Q1 | Change scope | **Only PRs that triggered (or would trigger) a bump** — i.e. PRs in the `OLD…NEW` range that changed at least one file *outside* `docs/**`. Docs-only PRs are excluded. |
| Q2 | Detail level | **Title + 1-line body summary** per PR (number, title, author, link, blockquoted first line of the PR body). |
| Q3 | vk-remote | **Leave as a SHA line.** |
| Q4 | Verification | **Trigger a real bump + inspect** the generated body, post-merge. |

### Why the Q1 filter is exactly "non-docs-only"

agent-images `build.yaml` triggers on `push: branches:[main]` with
`paths-ignore: docs/**` (and `paths-ignore` matches only when **all**
changed files are ignored). Its terminal `dispatch-frank` job fires the
`agent-images-bumped` repository_dispatch — the very thing that opens our
bump PR — **only after a non-docs build completes**. Therefore a
bump-triggering agent-images PR is, by definition, one that changed at
least one file outside `docs/**`. A docs-only agent-images PR rebuilds
nothing, ships in no image, and must not appear in a "what's being updated"
list. The filter mirrors the upstream trigger contract precisely.

## Design

### New artifact: `scripts/render_bump_body.py` (stdlib only)

A single Python script, runnable as `python3 scripts/render_bump_body.py
--old <sha> --new <sha> --vkr <sha>`, that prints the PR body to stdout.
Stdlib-only (`json`, `re`, `subprocess`, `argparse`) so the workflow needs
no `uv`/pip step. Three layers:

1. **`collect(old, new, vkr, repo="derio-net/agent-images") -> dict`** —
   the network layer. Shells out to `gh api` (the workflow already uses
   `gh`, and `GH_TOKEN` is in scope):
   - `gh api /repos/{repo}/compare/{old}...{new}` → `commits[]`, each with the
     **full** `.commit.message` and `.author.login`.
   - For each commit: `gh api /repos/{repo}/commits/{sha}` → `files[].filename`
     (per-PR paths — squash-merge means 1 commit == 1 PR).
   - `number` = the trailing `(#NN)` parsed from the commit subject (or
     `None`). `title` = subject minus that suffix. `summary` = the first
     meaningful paragraph of the **commit body**.
   - Returns a plain dict:
     ```python
     {
       "old": old, "new": new, "vkr": vkr, "repo": repo,
       "prs": [
         {"number": 88, "title": "feat(kali): rotate …",
          "author": "YiannisDermitzakis", "sha": "8606edf…",
          "paths": ["kali/wrap-claude.py", "kali/tests/…"],
          "summary": "The 2026-05-23 incident: a 5d4h-old remote-control parent…"},
         …  # oldest→newest as GitHub returns them
       ],
     }
     ```
   - **Raises** on any gh failure (caller decides the fallback).

> **Why the summary comes from the commit body, and why `#NN` links to
> `/issues/`.** A squash-merge subject's `(#NN)` is *not* reliably a PR:
> e.g. agent-images `8606edf` ends `(#88)` but #88 is the planning **issue**
> (`Closes #88`); its PR was #114, and `/pulls/88` 404s. `/commits/{sha}/pulls`
> is no better — it returns PRs whose branch merely *contains* the commit
> (it returned the still-open #114, whose merge sha ≠ the commit). The
> reliable source is the **commit itself**: GitHub copies the PR body into the
> squash commit body, so title/author/summary/files all come from `compare` +
> `/commits/{sha}`. The `#NN` reference is rendered as a link to
> `…/issues/{NN}` — GitHub's own canonical reference form, which shows the
> issue or 302-redirects to the PR when `NN` is one (so it is correct for
> both, unlike a hard-coded `/pull/{NN}` that 404s on an issue ref).

2. **`render(bump: dict) -> str`** — the pure, deterministic formatter.
   **All inclusion logic lives here so it is unit-tested**:
   - Drop any PR whose `paths` are *all* under `docs/` (the Q1 filter).
   - Order newest-first.
   - Emit markdown (see format below).
   - No network, no `gh`.

3. **`main()`** — wires argv → `collect()` → `render()` → `print`. Wraps
   `collect()` in `try/except`: on **any** exception (or `old`/`new`
   missing) it prints the **legacy minimal body** so the bump PR still
   opens. `old == new` is *not* a fallback — it short-circuits `collect()`
   and renders the "_agent-images unchanged._" note directly (vk-remote-only
   bump). Enrichment is best-effort, never blocking.

### Rendered body format (Q2 depth)

```markdown
## agent-images bump

`439a6ef` → `8606edf` · [compare](https://github.com/derio-net/agent-images/compare/439a6ef...8606edf)

### Upstream changes (1 PR)
- agent-images#88 — feat(kali): rotate remote-control sessions past max uptime + debug logs (@YiannisDermitzakis)
  > Rotates the wrap-claude session once it exceeds max uptime, adding per-session debug logs.

**vk-remote:** `7cebcbb`
```

Formatting rules (each a test case):
- Header `## agent-images bump`, then the `OLD7 → NEW7 · [compare](…)` line
  (7-char short SHAs; full SHAs in the compare URL).
- `### Upstream changes (N PR[s])` — N = count *after* the docs-only filter;
  singular/plural agree.
- One bullet per PR: `agent-images#<n> — <title> (@<author>)`.
  - Cross-repo `#N` does not autolink in another repo's PR body, so the
    number is rendered as an explicit markdown link to the **canonical
    reference** URL (issue-or-PR, redirecting):
    `[agent-images#88](https://github.com/derio-net/agent-images/issues/88)`.
  - `@<author>` omitted if author is null/empty.
  - The `> summary` blockquote line is omitted when the PR body is empty.
  - A range commit with **no** `(#NN)` (a direct push) renders as a short-SHA
    link instead of `#N`, with the commit subject as the title and no summary.
- `**vk-remote:** \`<sha>\`` line only when `vkr` is non-empty (unchanged
  from today's behavior).

### Legacy / fallback body

The exact current two-line body, emitted by `main()` when enrichment is
unavailable or not applicable:

```
agent-images: `<full-new-sha>`
vk-remote: `<vkr>`        # second line only when vkr present
```

### Edge cases (each a test)

| Case | Behavior |
|------|----------|
| `old == new` (vk-remote-only bump) | No agent-images section; body is the vk-remote line + a note `_agent-images unchanged._` |
| `old` not found in manifest | `main()` passes empty `old` → fallback body |
| compare returns 0 non-docs PRs | Header line + `_No image-affecting changes (docs-only upstream)._`, still shows compare link |
| `gh api` errors | `collect()` raises → `main()` prints fallback body |
| PR with empty body | bullet without the `>` summary line |
| commit with no `(#NN)` | short-SHA-link bullet, no summary |
| author null | bullet without `(@…)` |

### Workflow wiring: `.github/workflows/agent-images-bump.yml`

1. **Capture the OLD agent-images SHA before sed.** In the existing
   *Resolve SHAs* step (runs before *Update manifests*, after checkout),
   grep the live pin and export it:
   ```bash
   OLD_AI_SHA=$(grep -oE 'secure-agent-kali:[a-f0-9]+' \
     apps/secure-agent-pod/manifests/deployment.yaml | head -1 | cut -d: -f2)
   echo "old_ai_sha=$OLD_AI_SHA" >> "$GITHUB_OUTPUT"
   ```
2. **Replace the inline `BODY=…` construction** in the *Open PR* step with a
   call to the script (the step already exports `GH_TOKEN`):
   ```bash
   BODY=$(python3 scripts/render_bump_body.py \
     --old "${{ steps.shas.outputs.old_ai_sha }}" \
     --new "$AI_SHA" --vkr "$VKR_SHA")
   ```
   The `git commit -m` message is **unchanged**; only `--body` changes.
   The `git diff --quiet` / open-PR-dedup guards are unchanged.

No new workflow permissions: reading a **public** repo's compare/commits/
pulls works with the existing `secrets.GITHUB_TOKEN` (verified during
brainstorm — agent-images is public).

## Testing (TDD)

`scripts/tests/test_render_bump_body.py` (pytest, matching the repo's
`scripts/tests/test_*.py` convention). The renderer is pure, so tests feed
crafted `bump` dicts and assert on the markdown — no network:

- Single non-docs PR → full bullet with summary (the happy path above).
- Multi-PR range, newest-first ordering, `(N PRs)` plural.
- **Docs-only PR in the range is filtered out** (the Q1 contract) — and the
  count reflects the post-filter number.
- Mixed PR (docs/** + one code file) is **kept** (paths-ignore semantics).
- All-docs range → `_No image-affecting changes_` note.
- PR with empty body → no `>` line.
- Commit with no `(#NN)` → short-SHA-link bullet.
- Author null → no `(@…)`.
- `vkr` empty → no vk-remote line; `vkr` present → line shown.
- `old == new` → `_agent-images unchanged._`.
- `main()` fallback: monkeypatch `collect` to raise → stdout is the legacy
  two-line body (asserts enrichment never blocks the bump).

Run locally / in the container: `uv run --with pytest pytest
scripts/tests/test_render_bump_body.py -v` (no CI pytest job exists; this is
the same local/pre-commit posture as the other `scripts/tests`).

## Verification

### Pre-merge (no PR opened) — exercises `collect()` live

The gh-api collection path can be proven against the live API **without
opening a PR** by running the script directly in the container with two
real SHAs spanning a known agent-images PR:

```bash
GH_TOKEN=$(gh auth token) python3 scripts/render_bump_body.py \
  --old 439a6ef7e269401062b9be1fff5e6b972acc9f1f \
  --new 8606edfa9c104460fec5805c476cff7162da399c \
  --vkr 7cebcbb
```

Confirm the printed markdown matches the format (compare link, the
`agent-images#88` bullet with title/@author/summary, vk-remote line). This
runs in implementation (step verification), de-risking the API path before
merge. Also run a docs-only-spanning pair to confirm the filter elides it.

### Post-merge, operator-driven — full workflow end-to-end

Because `workflow_dispatch` captures `OLD = current live pin` and seds to
the input SHA, the input must be **strictly newer** than the current frank
pin for the range to be non-empty. After merge, exercise it one of two
ways:

1. **Natural** (preferred): the next real agent-images merge auto-dispatches
   `agent-images-bumped`; observe the bump PR it opens — its body should
   carry the new format. No action needed beyond reading the PR.
2. **Manual**: once agent-images `main` is at a SHA *ahead* of frank's
   current pin, dispatch with it:
   ```bash
   env -u GITHUB_TOKEN gh workflow run agent-images-bump.yml \
     --ref main -f agent_images_sha=<sha-newer-than-current-pin>
   ```
   Open the PR the run produces, confirm the `OLD → NEW · compare` line,
   the `### Upstream changes` bullet(s), the docs-only filter, and the
   `**vk-remote:**` line, then close that throwaway PR (it is real against
   `main`).

Agent reads the rendered body in either path; operator confirms it reads
correctly and closes any throwaway PR.

## Files touched

- **new** `scripts/render_bump_body.py`
- **new** `scripts/tests/test_render_bump_body.py`
- **edit** `.github/workflows/agent-images-bump.yml` (capture old SHA; call script)
