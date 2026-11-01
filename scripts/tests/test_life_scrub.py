"""Credential scrubbing guard (plan 2026-10-31--life--update-security-lifecycle, phase 5; spec R25).

scripts/life_scrub.py mirrors the console's internal/scrub: exact values of known secrets first
(with their encoded forms and every line of a multi-line value), patterns second
(p5-scrub-exact-values-first). The pattern fixtures are SHARED with derio-net/cluster-update-fr:
scripts/tests/fixtures/life/scrub-cases.json is a copy of that repo's testdata/scrub/cases.json
(source commit in FIXTURE_SOURCE). frank-local cases below cover the lessons of the console's
review rounds (p5-scrub-*): adjacent tokens, delimiters inside values, next-line YAML values,
unterminated quotes, base64 alignment, wrapped base64, and reference-shaped values.

The repo-wide test is R25's CI half for frank: no file a session, PR body or console page draws
from may carry a token-shaped string.
"""
import base64
import json
import sys
from pathlib import Path
from urllib.parse import quote_plus

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import life_scrub as ls  # noqa: E402

FIXTURE = ROOT / "scripts/tests/fixtures/life/scrub-cases.json"
FIXTURE_SOURCE = "derio-net/cluster-update-fr@cc4bb5c:testdata/scrub/cases.json"
CASES = json.loads(FIXTURE.read_text())


# ------------------------------------------------------------------ fixture loader
def build(segments, secret=""):
    """Join fixture segments; the public repos never hold a literal token."""
    out = []
    lines = secret.splitlines()
    for s in segments:
        if isinstance(s, str):
            out.append(s)
        elif "repeat" in s:
            out.append(s["repeat"] * s["times"])
        elif "base64" in s:
            out.append(base64.b64encode(s["base64"].encode()).decode())
        elif "ref" in s:
            out.append(ref(s["ref"], secret, lines))
        else:
            raise ValueError(s)
    return "".join(out)


def ref(form, secret, lines):
    b = secret.encode()
    if form == "raw":
        return secret
    if form == "base64":
        return base64.b64encode(b).decode()
    if form == "base64url":
        return base64.urlsafe_b64encode(b).decode()
    if form == "rawbase64":
        return base64.b64encode(b).decode().rstrip("=")
    if form == "rawbase64url":
        return base64.urlsafe_b64encode(b).decode().rstrip("=")
    if form == "query":
        return quote_plus(secret)
    if form.startswith("line:"):
        return lines[int(form.split(":")[1]) - 1]
    if form.startswith("line-base64:"):
        return base64.b64encode(lines[int(form.split(":")[1]) - 1].encode()).decode()
    raise ValueError(form)


def long_segments(segments):
    out = []
    for s in segments:
        if isinstance(s, dict) and "repeat" in s:
            v = s["repeat"] * s["times"]
        elif isinstance(s, dict) and "base64" in s:
            v = base64.b64encode(s["base64"].encode()).decode()
        else:
            continue
        if len(v) >= 16:
            out.append(v)
    return out


def assert_redacted(text, kinds, leaks, out):
    for k in kinds:
        assert f"«redacted:{k}»" in out, (k, out)
    for leak in leaks:
        assert leak not in out, (leak, out)


# ------------------------------------------------------------------ shared pattern cases
def test_fixture_is_the_shared_copy():
    assert CASES["_comment"][0].startswith("Shared credential-scrub fixtures")
    assert len(CASES["cases"]) >= 40 and CASES["benign"] and CASES["literal"]


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_shared_case_is_found_and_redacted(case):
    text = build(case["in"])
    assert set(ls.find_tokens(text)) == set(case["kinds"]), case["name"]
    out = ls.scrub(text)
    assert_redacted(text, case["kinds"], case.get("leaks", []) + long_segments(case["in"]), out)
    assert ls.scrub(out) == out, "scrub is idempotent"
    assert ls.find_tokens(out) == [], "a redacted text is clean"


@pytest.mark.parametrize("segments", CASES["benign"], ids=[build(b)[:30] for b in CASES["benign"]])
def test_shared_benign_text_is_untouched(segments):
    text = build(segments)
    assert ls.scrub(text) == text
    assert ls.find_tokens(text) == []


@pytest.mark.parametrize("case", CASES["literal"], ids=[c["name"] for c in CASES["literal"]])
def test_shared_literal_case_redacts_every_form(case):
    secret = build(case["secret"])
    text = build(case["in"], secret)
    lits = ls.Literals()
    lits.add(case["kind"], secret)
    out = ls.scrub(text, lits)
    assert f"«redacted:{case['kind']}»" in out, out
    for line in [secret] + [l for l in secret.splitlines() if len(l) >= 8]:
        assert line not in out
        assert base64.b64encode(line.encode()).decode().rstrip("=") not in out
    assert case["kind"] in ls.find_tokens(text, lits)


# ------------------------------------------------------------------ plan's named fixtures
GHS = "gh" + "s_" + "A1b2" * 9
PAT = "github" + "_pat_" + "11AB" * 6 + "_" + "cd34" * 12
GITEA = "0a1b2c3d4e" * 4
TELEGRAM = "123456789:" + "AA" + "Bc_-d" * 6 + "xyz"
ANTHROPIC = "sk-" + "ant-api03-" + "Xy9_" * 10
OPENAI = "sk-" + "proj-" + "Qw8-" * 10
OMNI_KEY = base64.b64encode(json.dumps({"name": "frank-os", "pgp_key": "-----BEGIN PGP " + "x" * 40}).encode()).decode()

NAMED = {
    "github app installation token": (f"cloning with {GHS} now", "github-token"),
    "fine-grained pat": (f"GITHUB_TOKEN={PAT}", "github-pat"),
    "gitea token": (f"Authorization: token {GITEA}", "gitea-token"),
    "telegram bot token": (f"https://api.telegram.org/bot{TELEGRAM}/sendMessage", "telegram-bot-token"),
    "omni service-account key": (f"OMNI_SERVICE_ACCOUNT_KEY {OMNI_KEY}", "omni-sa-key"),
    "talosconfig key block": ("contexts:\n  frank:\n    ca: " + "Q0FDQUNB" * 6 + "\n    key: " + "S0VZS0VZ" * 6 + "\n", "yaml-secret"),
    "kubeconfig token": ("users:\n- name: x\n  user:\n    token: " + "eyJ" + "hbGciOi" * 6 + "\n", "jwt"),
    "kubeconfig client-key-data": ("    client-key-data: " + "TFMwdExT" * 8 + "\n", "yaml-secret"),
    "anthropic key": (f"ANTHROPIC_API_KEY {ANTHROPIC}", "api-key"),
    "openai key": (f"export OPENAI {OPENAI}", "api-key"),
}


@pytest.mark.parametrize("name", sorted(NAMED))
def test_plan_named_credential_is_redacted(name):
    text, kind = NAMED[name]
    assert kind in ls.find_tokens(text), (name, ls.find_tokens(text))
    out = ls.scrub(text)
    assert f"«redacted:{kind}»" in out
    for secret in (GHS, PAT, GITEA, TELEGRAM, ANTHROPIC, OPENAI, OMNI_KEY, "S0VZS0VZ" * 6, "TFMwdExT" * 8):
        assert secret not in out


def test_git_shas_after_commit_are_not_redacted():
    for text in ("commit " + "a1b2c3d4e5" * 4, "merged 3f2a1b0c into main", "sha256:" + "ab" * 32,
                 "revision: " + "0f" * 20):
        assert ls.scrub(text) == text, text


# ------------------------------------------------------------------ review-round lessons
def test_adjacent_tokens_are_both_redacted():
    # a pattern that consumed its boundary would miss the second token
    for sep in ("", ",", " ", "\n"):
        text = GHS + sep + GHS.replace("A1b2", "Z9y8")
        out = ls.scrub(text)
        assert "A1b2" * 9 not in out and "Z9y8" * 9 not in out, repr(sep)


def test_yaml_value_with_comment_and_json_pairs():
    for text in ('password: hunter2hunter2 # rotated', '{"password":"hunter2,hunter2}","x":1}',
                 "'api_key': 'p#ss,word}x'", 'token = "ab#cd,ef}gh"'):
        out = ls.scrub(text)
        assert "hunter2" not in out and "p#ss" not in out and "ab#cd" not in out, out


def test_next_line_yaml_value_and_unterminated_quote():
    out = ls.scrub('client-key-data:\n      ' + "TFMwdExT" * 8 + "\n")
    assert "TFMwdExT" not in out
    out = ls.scrub('secret: "unterminated value runs to the end\nnext: ok')
    assert "unterminated value" not in out and "next: ok" in out


SECRET = "S3cr3t-" + "Kx7" * 8


def lits():
    l = ls.Literals()
    l.add("talosconfig", SECRET + "\nsecond-line-" + "Vb4" * 6)
    return l


@pytest.mark.parametrize("offset", [0, 1, 2])
def test_literal_inside_a_larger_base64_blob_at_every_alignment(offset):
    blob = base64.b64encode(b"x" * offset + b"prefix:" + SECRET.encode() + b":suffix").decode()
    out = ls.scrub(f"data: {blob}", lits())
    assert "«redacted:talosconfig»" in out
    assert blob not in out


@pytest.mark.parametrize("width,eol,indent", [(64, "\n", ""), (76, "\r\n", ""), (64, "\n", "    "), (40, "\n", "\t")])
def test_literal_inside_a_wrapped_base64_run(width, eol, indent):
    enc = base64.b64encode(b"apiVersion: v1\nkind: Config\nkey: " + SECRET.encode() + b"\n" * 20).decode()
    wrapped = eol.join(indent + enc[i:i + width] for i in range(0, len(enc), width))
    text = "config: |" + eol + wrapped + eol + "next: value" + eol
    out = ls.scrub(text, lits())
    assert "«redacted:talosconfig»" in out
    assert enc[:width] not in out and "next: value" in out


def test_double_base64_and_each_line_of_a_multi_line_secret():
    double = base64.b64encode(base64.b64encode(SECRET.encode())).decode()
    assert "«redacted:talosconfig»" in ls.scrub(double, lits())
    out = ls.scrub("line two is second-line-" + "Vb4" * 6, lits())
    assert "Vb4" * 6 not in out


def test_url_and_json_escaped_literal():
    l = ls.Literals()
    l.add("github-token", 'a"b/c d+e' * 2)
    assert "a" not in ls.scrub(quote_plus('a"b/c d+e' * 2), l).replace("«redacted:github-token»", "")
    assert ls.scrub(json.dumps({"x": 'a"b/c d+e' * 2}), l) == '{"x": "«redacted:github-token»"}'


def test_short_values_are_not_registered():
    l = ls.Literals()
    l.add("x", "short")
    assert ls.scrub("a short word", l) == "a short word"


@pytest.mark.parametrize("text", [
    'token: "{{ .token }}"',                  # ESO template reference, not a value
    "password: ${POSTGRES_PASSWORD}",          # env reference
    'key: "$(cat "$CREDENTIALS_DIR/x")"',      # shell substitution
    "secretKey: token",
])
def test_reference_shaped_values_are_not_tokens(text):
    assert ls.find_tokens(text, repository=True) == [], text


@pytest.mark.parametrize("text", [
    'token: "{{ .token }}"', "password: ${POSTGRES_PASSWORD}", 'key: "$(cat /run/credentials/x)"',
])
def test_scrub_never_trusts_a_reference_shape(text):
    # p5-r8: the reference exemption is the repository guard's (manifests are full of ESO
    # templates); a transcript is redacted whatever the value looks like.
    assert "redacted" in ls.scrub(text), text
    assert ls.find_tokens(text) != [], text


@pytest.mark.parametrize("text", [
    # p5-r8: `{{.*}}` spanned two templates, so a literal secret between them was "a reference"
    'password: "{{ a }}hunter2hunter2Zq9{{ b }}"',
    "password: {{a}}hunter2hunter2Zq9{{b}}",
    # p5-r8: `\$\(.*\)?` made the closing paren optional, so any value starting `$(` passed
    "password: $(hunter2hunter2Zq9",
    "token: ${A}ghp_" + "Zq9" * 12,
    "password: $(a)hunter2hunter2Zq9$(b)",
])
def test_a_secret_dressed_as_a_reference_is_still_reported(text):
    assert ls.find_tokens(text, repository=True) != [], text
    assert "redacted" in ls.scrub(text), text


def test_reference_pattern_is_the_reviewed_one():
    assert ls.REFERENCE.pattern == r"^(?:\{\{[^{}]*\}\}|\$\{[A-Za-z_]\w*\}|\$\([^()]*\))$"


# ------------------------------------------------------------------ repo-wide guard (R25)
def guarded_files():
    roots = [ROOT / "docs/upgrade-briefs", ROOT / "smoke", ROOT / "apps/cluster-update-fr",
             ROOT / "apps/upgrade-sessions", ROOT / "apps/renovate"]
    files = [ROOT / "update-policy.yaml", ROOT / "renovate.json5"]
    for r in roots:
        files += [p for p in r.rglob("*") if p.is_file()]
    return files


def test_repo_guard_covers_the_named_paths():
    rel = {str(p.relative_to(ROOT)) for p in guarded_files()}
    for must in ("update-policy.yaml", "renovate.json5", "docs/upgrade-briefs/AGENTS.md",
                 "apps/upgrade-sessions/manifests/networkpolicies.yaml",
                 "apps/cluster-update-fr/manifests/externalsecrets.yaml"):
        assert must in rel, must
    assert any(r.startswith("smoke/frank/") for r in rel) and any(r.startswith("apps/renovate/") for r in rel)


@pytest.mark.parametrize("path", guarded_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_token_shaped_string_in_session_facing_files(path):
    assert ls.find_tokens(path.read_text(), repository=True) == [], path


@pytest.mark.parametrize("text,kind", [
    ("    key: LITELLM_MASTER_KEY", None), ("  - {key: talosconfig, path: talosconfig}", None),
    ("secret: {secretName: x, optional: true}", None), ("password: hunter2hunter2", "yaml-secret"),
    ("password: " + "Zq" * 8, "yaml-secret"), ('key: "talosconfig-material"', "yaml-secret"),
    # p5-sec-2: digits in an all-caps value are a secret shape, not an ENV key name
    ("password: ABC123DEF", "yaml-secret"), ("token: AKIA" + "Q7" * 8, "yaml-secret"),
    ("api_key: DB_PASSWORD", None), ("  key: FRANK_UPDATER_GITEA_TOKEN", None),
    ("password: Zq9Zq9Zq9Zq9:", "yaml-secret"),
    # flow collections: every element must be a key name, else it is reported
    ("secret: {password: hunter2hunter2}", "yaml-secret"), ("secret: [ABC123DEF, x]", "yaml-secret"),
    ("secret: {secretValue: Zq9Zq9Zq9Zq9}", "yaml-secret"), ("secret: {unclosed: talosconfig", "yaml-secret"),
    ("secret: {secretName: x-y, optional: true}", None),
    # p5-r9: a lowercase/dash or one-word all-caps value is a NAME only under a name-bearing key
    # (key, secretKey, secretName, name, path) or as UPPER_SNAKE with an underscore.
    ("password: correct-horse-battery-staple", "yaml-secret"), ("password: correcthorsebattery", "yaml-secret"),
    ("token: PASSWORDPASSWORD", "yaml-secret"), ("secret: [talosconfig, bot-token]", "yaml-secret"),
    ("secret: {password: correct-horse-battery}", "yaml-secret"), ("secret: {apiValue: CORRECTHORSE}", "yaml-secret"),
    ("  key: talosconfig-material", None), ("secret: {secretKey: bot-token, name: telegram-creds}", None),
    ("- {key: tailscale-authkey, path: tailscale-authkey}", None), ("password: DB_PASSWORD", None),
    ("        - key: kubernetes.io/metadata.name", None), ("password: correct/horse-battery", "yaml-secret"),
    ("key: a.b/c.d/e-f-g-h", "yaml-secret"),
])
def test_repository_mode_exempts_secret_names_but_not_values(text, kind):
    assert ls.find_tokens(text, repository=True) == ([kind] if kind else []), text
    assert ls.find_tokens(text) != [] or len(text.split(":", 1)[1].strip()) < 8, "redaction stays strict"
