"""Tripwire: every layer code in blog/data/reader.yaml must exist in docs/layers.yaml.

The topic guides (`{{< reader-topic >}}`) select posts by
`in $topic.layers .Params.layer`, wrapped in `{{ with $matches }}` — a code that
matches no post renders nothing and errors on nothing. A typo (`obsv` for
`obs`) therefore empties a whole section of a topic guide, the PR's promoted
discovery path, with a green build and a passing check_blog_reader.py. This
test makes the registry the authority: an unknown code fails the PR.

Coverage is deliberately NOT asserted (repo/fun posts are reachable via the
series indexes; leaving a layer out of every topic is curation, not a bug).
"""
import os

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _registry_codes():
    with open(os.path.join(REPO, "docs", "layers.yaml")) as f:
        return {entry["code"] for entry in yaml.safe_load(f)["layers"]}


def _reader():
    with open(os.path.join(REPO, "blog", "data", "reader.yaml")) as f:
        return yaml.safe_load(f)


def test_every_topic_layer_code_is_registered():
    codes = _registry_codes()
    unknown = {
        (topic["slug"], code)
        for topic in _reader()["topics"]
        for code in topic.get("layers", [])
        if code not in codes
    }
    assert not unknown, f"reader.yaml topics reference layer codes absent from docs/layers.yaml: {sorted(unknown)}"


def test_every_topic_has_at_least_one_layer():
    empty = [t["slug"] for t in _reader()["topics"] if not t.get("layers")]
    assert not empty, f"topics with no layers render empty guides: {empty}"
