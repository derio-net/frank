"""Tripwire: `blog_craft_version` must be a blog-craft RELEASE tag, not a branch SHA.

THE FAILURE. `.blog-craft.yaml` / `.blog-craft.sync.yaml` record the blog-craft
ref frank was last synced to; `/blog-craft:update` re-renders AT that ref (a
plain `git archive`, no fetch) to recover the 3-way merge base for hugo.toml,
custom.css and site-banner. A ref that stops resolving does not fail loudly —
the updater degrades every `merged` path to a baseless conflict. A branch-head
SHA is exactly such a ref on derio-net/blog-craft (`allow_squash_merge` +
`delete_branch_on_merge`): once the PR squash-merges, the branch is gone and
the SHA is reachable only via `refs/pull/<n>/head`, which no clone fetches by
default. The only guard was `assert cfg.get("blog_craft_version")` — non-empty.

THE RULE. The pin is `vX.Y.Z`. A SHA is allowed ONLY while it sits in the
exception table below, with the PR it tracks, the release that retires it and
the recovery ref — so a lingering exception is a visible, dated debt rather
than a silent one, and any NEW SHA fails this test on the PR that adds it.
"""
import os
import re

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RELEASE = re.compile(r"v\d+\.\d+\.\d+")

# sha -> why it is tolerated. Delete the row when the re-pin lands.
EXCEPTIONS = {
    "362e2be9fe81306eab35f3540fc37f91748e4470": (
        "head of blog-craft#86 (reader experience), adopted by frank#787 before "
        "v0.22.0 existed. Re-pin to v0.22.0 as soon as it is tagged, BEFORE the "
        "branch is deleted; if it already is, the commit is still fetchable via "
        "`git fetch origin refs/pull/86/head` in a blog-craft clone."
    ),
}


def _pins():
    for name in (".blog-craft.yaml", ".blog-craft.sync.yaml"):
        with open(os.path.join(REPO, name)) as f:
            yield name, str(yaml.safe_load(f).get("blog_craft_version") or "")


def test_pin_is_a_release_tag_or_a_documented_exception():
    for name, pin in _pins():
        assert pin, f"{name}: blog_craft_version is unset"
        if RELEASE.fullmatch(pin):
            continue
        assert pin in EXCEPTIONS, (
            f"{name}: blog_craft_version={pin!r} is not a release tag. A branch "
            "SHA stops resolving after squash-merge + branch deletion and silently "
            "breaks the next /blog-craft:update. Pin a vX.Y.Z tag, or add a dated "
            "row to EXCEPTIONS in this test with the PR, the retiring release and "
            "the recovery ref."
        )


def test_both_pins_agree():
    pins = dict(_pins())
    assert len(set(pins.values())) == 1, f"config and sync snapshot disagree: {pins}"
