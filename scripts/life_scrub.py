#!/usr/bin/env python3
"""Credential redaction for frank (plan 2026-10-31--life--update-security-lifecycle, phase 5; spec R25).

A Python port of derio-net/cluster-update-fr internal/scrub. Two layers, in this order:

  1. Literals -- exact values of credentials you KNOW (registered with Literals.add), plus their
     derived forms: every line of a multi-line value, URL escapes, JSON escaping, lower/upper
     hex, and base64 (standard and URL alphabets) at all three byte alignments. Base64 runs --
     including runs wrapped across lines (any width, CRLF or LF, indented) -- are decoded and
     searched for any registered form; a hit redacts the whole run.
  2. Patterns -- for secrets nobody registered (a token pasted into a doc, a key in a manifest).

Rules that keep the pattern table free of bypasses (each was a console review finding,
journal p5-scrub-*):
  - no pattern CONSUMES a boundary character; boundaries are checked in code against the byte
    before the match, so a match never eats the separator its neighbour needs (adjacent tokens);
  - no pattern is anchored to end of line; a value ends at whitespace, a quote, or (trimmed in
    code) a trailing comma or brace, and a quoted value runs to its matching quote so '#', ','
    and '}' inside it are redacted with it;
  - a value may sit on the NEXT indented line (YAML block style); an unclosed quote redacts to
    the end of its line;
  - redaction repeats until stable; over-redaction is preferred to under-redaction.

One frank-only addition: a key/value whose value is a REFERENCE ({{ .x }}, ${X}, $(cmd)) is not a
secret. Manifests are full of ESO templates and env references, and the repository guard must
not cry wolf on them. A literal secret is never reference-shaped, so this cannot hide one.

The pattern fixtures are shared with the console: scripts/tests/fixtures/life/scrub-cases.json.

Usage: scripts/life_scrub.py FILE...   (exit 1 and list kinds if any file holds a token)
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import sys
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, quote_plus

MIN_LITERAL = 8
MIN_BASE64_RUN = 24

ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
WORD_CHARS = ALNUM + "_"
TOKEN_CHARS = ALNUM + "_-"
B64_CHARS = ALNUM + "_+/-"

SECRET_KEYS = (r"(?:token|access_token|refresh_token|client-key-data|client-certificate-data|key|crt|ca|"
               r"password|passwd|pass|secret|client_secret|private_key|api_key|apikey)")
SEP = r"[ \t]*[:=][ \t]*(?:\r?\n[ \t]+)?"
REFERENCE = re.compile(r"^(?:\{\{.*\}\}|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$\(.*\)?)$", re.S)
# Repository mode only: an unquoted value that is the NAME of a secret, not its value -- an
# ENV/Infisical key (LITELLM_MASTER_KEY), a Secret key (talosconfig, bot-token), or a YAML flow
# mapping ({secretName: ...}), or a nested mapping key on the next line (`secret:\n  secretName:`).
# Letters/dots/hyphens only, or all-caps snake: no digits, so a
# password-like value (hunter2hunter2) is still reported. A redaction never uses this.
KEY_NAME = re.compile(r"^(?:[A-Z][A-Z0-9_]*|[a-z][a-z.-]*|[{\[].*|[A-Za-z][A-Za-z0-9_.-]*:)$")


def _classify_eyj(secret: str) -> str:
    """An Omni service-account key (base64 JSON carrying a PGP key) vs a JWT; both are redacted."""
    first = secret.split(".", 1)[0]
    for alt in (None, b"-_"):
        try:
            raw = base64.b64decode(first + "=" * (-len(first) % 4), altchars=alt, validate=True)
        except (binascii.Error, ValueError):
            continue
        return "omni-sa-key" if b'"pgp_key"' in raw else "jwt"
    return "jwt"


@dataclass(frozen=True)
class Pattern:
    kind: str
    regex: re.Pattern  # group 1 is the secret; text outside it stays readable
    not_before: str = ""  # reject a match whose preceding char is in this set
    classify: Callable[[str], str] | None = None
    trim_right: str = ""  # trailing chars the value class could not exclude without leaking
    key_value: bool = False  # skip reference-shaped values
    unquoted: bool = False  # the unquoted key/value form (repository mode exempts key NAMES)


def _kv(quote_char: str | None, closed: bool = False) -> Pattern:
    """A key/value secret (YAML, JSON, env). Quoted values run to the matching quote (closed) or,
    for an unclosed quote, to end of line; unquoted values run to whitespace or a quote/backtick."""
    if quote_char is None:
        value = r"([^\s\"'`]{8,})"
        return Pattern("yaml-secret", re.compile(r"(?i)\b" + SECRET_KEYS + r"[\"']?" + SEP + value),
                       trim_right=",}", key_value=True, unquoted=True)
    value = quote_char + f"([^{quote_char}\\n]{{8,}})" + (quote_char if closed else "")
    return Pattern("yaml-secret", re.compile(r"(?i)\b" + SECRET_KEYS + r"[\"']?" + SEP + value), key_value=True)


# THE pattern table. Order matters: specific shapes first, key/value last; closed quotes before
# unclosed ones (an already-redacted value is skipped).
PATTERNS: tuple[Pattern, ...] = (
    Pattern("private-key", re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY(?: BLOCK)?-----)")),
    Pattern("jwt", re.compile(r"(eyJ[A-Za-z0-9_+/=-]{20,}(?:\.[A-Za-z0-9_+/=-]+)*)"), B64_CHARS, _classify_eyj),
    Pattern("github-pat", re.compile(r"(github_pat_[A-Za-z0-9_]{22,})"), WORD_CHARS),
    # The lookahead stops the run before an ADJACENT token's prefix ("…A1b2ghs_Z9…"), which the
    # console's RE2 pattern cannot do: it eats the next token's "ghs" and leaves its body behind.
    Pattern("github-token", re.compile(r"((?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}?)(?=gh[pousr]_|[^A-Za-z0-9]|$)"), WORD_CHARS),
    Pattern("api-key", re.compile(r"(sk-[A-Za-z0-9_-]{20,})"), TOKEN_CHARS),
    # Exactly 35 secret chars: a longer run is redacted at its first 35 (harmless over-redaction).
    Pattern("telegram-bot-token", re.compile(r"([0-9]{6,12}:[A-Za-z0-9_-]{35})"), "0123456789"),
    Pattern("bearer", re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{8,})")),
    Pattern("gitea-token", re.compile(r"(?i)\btoken\s+([0-9a-f]{40})")),
    _kv('"', closed=True), _kv("'", closed=True), _kv('"'), _kv("'"), _kv(None),
)


def marker(kind: str) -> str:
    return f"«redacted:{kind}»"


def _is_marker(s: str) -> bool:
    return s.startswith("«redacted:") and s.endswith("»") and s.count("«") == 1


def _matches(p: Pattern, text: str, repository: bool = False) -> list[tuple[int, int, str]]:
    hits = []
    pos = 0
    while pos <= len(text):
        m = p.regex.search(text, pos)
        if m is None or m.start(1) < 0:
            break
        start, end = m.start(1), m.end(1)
        if p.key_value and REFERENCE.match(text[start:end]):
            pos = max(m.end(), pos + 1)
            continue
        while p.trim_right and end > start and text[end - 1] in p.trim_right:
            end -= 1
        value = text[start:end]
        if _is_marker(value) or (p.key_value and REFERENCE.match(value)) or \
                (repository and p.unquoted and KEY_NAME.match(value)):
            pos = max(m.end(), pos + 1)
            continue
        if p.not_before and start > 0 and text[start - 1] in p.not_before:
            pos = m.start() + 1  # resume one char later so an overlapping valid match is found
            continue
        hits.append((start, end, p.classify(value) if p.classify else p.kind))
        pos = max(m.end(), pos + 1)
    return hits


def _patterns(text: str, seen: Callable[[str], None], repository: bool = False) -> str:
    for _ in range(8):
        changed = False
        for p in PATTERNS:
            hits = _matches(p, text, repository)
            if not hits:
                continue
            changed = True
            out, last = [], 0
            for start, end, kind in hits:
                seen(kind)
                out += [text[last:start], marker(kind)]
                last = end
            text = "".join(out) + text[last:]
        if not changed:
            break
    return text


# ------------------------------------------------------------------ literal layer
def _aligned_b64(alphabet: Callable[[bytes], bytes], b: bytes, k: int) -> str:
    """b's base64 as it appears after k bytes inside a larger blob: only chars determined by b."""
    s = alphabet(bytes(k) + b).decode().rstrip("=")
    start, end = (8 * k + 5) // 6, min(8 * (k + len(b)) // 6, len(s))
    return s[start:end] if start < end else ""


def derived_forms(v: str) -> list[str]:
    b = v.encode()
    go_json = (json.dumps(v, ensure_ascii=False)[1:-1]  # Go's json.Marshal also escapes <>&
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    out = [quote_plus(v, safe=""), quote(v, safe=""), quote(v, safe=":@&=+$,;!*'()"), b.hex(), b.hex().upper(),
           go_json, json.dumps(v)[1:-1]]
    for alphabet in (base64.b64encode, base64.urlsafe_b64encode):
        out.append(alphabet(b).decode())
        out += [_aligned_b64(alphabet, b, k) for k in range(3)]
    return out


_B64_TOKEN = re.compile(r"[A-Za-z0-9+/_-]{4,}={0,2}")
_B64_LINE = re.compile(r"^[ \t]*[A-Za-z0-9+/_-]{4,}={0,2}[ \t]*$")
_WRAP = str.maketrans("", "", "\r\n \t")


def _base64_runs(text: str) -> list[tuple[int, int]]:
    """Base64 runs, including runs WRAPPED across lines: a run reaching the end of its line
    continues through every following line that is nothing but base64; padding ends a blob."""
    lines, st = [], 0
    while True:
        i = text.find("\n", st)
        if i < 0:
            lines.append((st, len(text)))
            break
        end = i - 1 if i > st and text[i - 1] == "\r" else i
        lines.append((st, end))
        st = i + 1
    runs = []
    li = 0
    while li < len(lines):
        ls_, le = lines[li]
        toks = list(_B64_TOKEN.finditer(text, ls_, le))
        nxt = li
        for ti, t in enumerate(toks):
            start, end = t.start(), t.end()
            last = ti == len(toks) - 1 and text[end:le].strip(" \t") == ""
            if last and not text[start:end].endswith("="):
                while nxt + 1 < len(lines) and _B64_LINE.match(text[lines[nxt + 1][0]:lines[nxt + 1][1]]):
                    nxt += 1
                    seg = text[lines[nxt][0]:lines[nxt][1]].rstrip(" \t")
                    end = lines[nxt][0] + len(seg)
                    if seg.endswith("="):
                        break
            runs.append((start, end))
            if nxt != li:
                break
        li = nxt + 1
    return runs


def _decode_loose(run: str) -> bytes | None:
    run = run.rstrip("=")
    for alt in (None, b"-_"):
        for cut in (len(run), len(run) - len(run) % 4):
            if cut <= 0:
                continue
            chunk = run[:cut]
            try:
                return base64.b64decode(chunk + "=" * (-len(chunk) % 4), altchars=alt, validate=True)
            except (binascii.Error, ValueError):
                continue
    return None


class Literals:
    """Exact secret values (the first layer). Child sets see their parent's values too."""

    def __init__(self, parent: "Literals | None" = None):
        self.parent = parent
        self.forms: dict[str, tuple[str, bool]] = {}  # form -> (kind, raw)

    def add(self, kind: str, value: str) -> None:
        value = value.strip()
        if not value:
            return
        candidates = [value]
        if "\n" in value or "\r" in value:
            candidates += [l.strip() for l in re.split(r"[\r\n]+", value) if l.strip()]
        for c in candidates:
            self._put(c, kind, True)
            for f in derived_forms(c):
                self._put(f, kind, False)

    def _put(self, form: str, kind: str, raw: bool) -> None:
        if len(form) < MIN_LITERAL:
            return
        old = self.forms.get(form)
        if old and old[0] == kind and (old[1] or not raw):
            return
        self.forms[form] = (kind, raw)

    def all(self) -> list[tuple[str, str]]:
        out, s = [], self
        while s is not None:
            out += sorted((f, k) for f, (k, _) in s.forms.items())
            s = s.parent
        return out

    def redact(self, text: str, seen: Callable[[str], None]) -> str:
        entries = self.all()
        if not entries:
            return text
        spans = []  # (start, end, kind, weight)
        for form, kind in entries:
            idx = text.find(form)
            while idx >= 0:
                spans.append((idx, idx + len(form), kind, len(form)))
                idx = text.find(form, idx + 1)
        for start, end in _base64_runs(text):
            joined = text[start:end].translate(_WRAP)
            if len(joined) < MIN_BASE64_RUN:
                continue
            decoded = _decode_loose(joined)
            if decoded is None:
                continue
            for form, kind in entries:
                if form.encode() in decoded:
                    spans.append((start, end, kind, len(form)))
                    break
        if not spans:
            return text
        spans.sort(key=lambda s: (s[0], -s[1]))
        merged = [list(spans[0])]
        for s in spans[1:]:
            cur = merged[-1]
            if s[0] <= cur[1]:  # overlapping or adjacent: one redaction
                cur[1] = max(cur[1], s[1])
                if s[3] > cur[3]:
                    cur[2], cur[3] = s[2], s[3]
                continue
            merged.append(list(s))
        out, last = [], 0
        for start, end, kind, _ in merged:
            seen(kind)
            out += [text[last:start], marker(kind)]
            last = end
        return "".join(out) + text[last:]


def scrub(text: str, literals: Literals | None = None) -> str:
    """text with every credential replaced by «redacted:<kind>» (literals first). Idempotent."""
    if literals is not None:
        text = literals.redact(text, lambda _: None)
    return _patterns(text, lambda _: None)


def find_tokens(text: str, literals: Literals | None = None, repository: bool = False) -> list[str]:
    """Kinds of credential present in text, without duplicates, in redaction order. [] = clean.

    repository=True is the CI guard over files in git: it does not report an unquoted value that
    is the NAME of a secret (KEY_NAME). Never use it to decide what to redact.
    """
    kinds: list[str] = []

    def add(k: str) -> None:
        if k not in kinds:
            kinds.append(k)

    if literals is not None:
        text = literals.redact(text, add)
    _patterns(text, add, repository)
    return kinds


def main(argv: list[str]) -> int:
    dirty = 0
    for path in argv:
        with open(path, encoding="utf-8", errors="replace") as fh:
            kinds = find_tokens(fh.read(), repository=True)
        if kinds:
            print(f"{path}: {', '.join(kinds)}")
            dirty = 1
    return dirty


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
