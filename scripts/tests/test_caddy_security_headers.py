"""Tripwire: Hop's public vhosts stay hardened, and www degrades gracefully.

Three separate traps are pinned here, all of which fail quietly:

1. **CSP vs analytics.** The sites load one external origin —
   counter.derio.net (GoatCounter). A CSP that forgets it blocks analytics in
   the browser while every server-side check still returns 200. Likewise
   `style-src 'self'` requires the site image to emit an external stylesheet;
   agentic-stoa/site pins that with its own build check.

2. **HSTS preload is a one-way door.** `preload` applies to every *.derio.net
   name a browser has seen and is painful to unwind. Promoting to preload is a
   deliberate operator decision, not something to drift into — so this test
   asserts its ABSENCE. Delete the assertion consciously when the decision is
   made.

3. **www must not hard-fail when its backend is absent.** The first site image
   only exists after the operator finishes enrolling agentic-stoa/site in the
   mirror. Without a handle_errors fallback, merging the vhost would turn
   www.derio.net from a holding page into a 502. The fallback also covers the
   steady-state case of a crashed pod.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
# The Caddyfile moved out of an inline ConfigMap into a Kustomize generator
# input (2026-07-26), so that an edit hashes into the pod spec and actually
# reaches the running Caddy. Read the file directly now.
CADDY_FILE = REPO_ROOT / "clusters/hop/apps/caddy/manifests/files/Caddyfile"

ANALYTICS_ORIGIN = "https://counter.derio.net"


def caddyfile() -> str:
    return CADDY_FILE.read_text()


def _block(text: str, host: str) -> str:
    """Return the top-level block for `host` (brace-balanced)."""
    start = text.index(f"\n{host} {{")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"unbalanced block for {host}")


def test_security_headers_snippet_is_defined() -> None:
    text = caddyfile()
    assert "(security_headers) {" in text, "no (security_headers) snippet defined"


def test_hsts_is_strong_but_not_preloaded() -> None:
    text = caddyfile()
    hsts = [ln for ln in text.splitlines() if "Strict-Transport-Security" in ln]
    assert hsts, "no HSTS header"
    line = hsts[0]
    assert "max-age=31536000" in line, "HSTS max-age must be at least one year"
    assert "includeSubDomains" in line
    assert "preload" not in line, (
        "HSTS preload is a one-way door across every *.derio.net name — it is a "
        "deliberate operator decision, not a default. Remove this assertion "
        "only together with that decision."
    )


def test_baseline_headers_present() -> None:
    text = caddyfile()
    for header, expected in (
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        ("Permissions-Policy", "geolocation=()"),
    ):
        matching = [ln for ln in text.splitlines() if header in ln]
        assert matching, f"missing {header}"
        assert expected in matching[0], f"{header} does not contain {expected!r}"


def _snippet(name: str) -> str:
    """Return the body of the named Caddy snippet `(name) { ... }`."""
    text = caddyfile()
    start = text.index(f"({name}) {{")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"unbalanced snippet ({name})")


def _policy(snippet: str) -> str:
    """Return the Content-Security-Policy line from a named CSP snippet."""
    csp = [ln for ln in _snippet(snippet).splitlines() if "Content-Security-Policy" in ln]
    assert csp, f"({snippet}) defines no Content-Security-Policy"
    return csp[0]


def _directive(policy: str, name: str) -> str:
    """Return one directive's full text from a CSP header line."""
    for part in policy.split('"')[1].split(";"):
        part = part.strip()
        if part.split(" ")[0] == name:
            return part
    raise AssertionError(f"no {name!r} directive in {policy!r}")


def test_csp_admits_analytics_and_forbids_framing() -> None:
    for snippet in ("csp_strict", "csp_blog"):
        policy = _policy(snippet)
        assert "default-src 'self'" in policy, f"{snippet}: no default-src"
        assert "frame-ancestors 'none'" in policy, (
            f"{snippet}: frame-ancestors 'none' replaces X-Frame-Options; "
            "without it the site is clickjackable"
        )
        # GoatCounter serves the script and receives the beacon.
        assert f"script-src 'self' {ANALYTICS_ORIGIN}" in policy, (
            f"{snippet}: CSP must allow the GoatCounter script, or analytics "
            "dies silently"
        )
        assert ANALYTICS_ORIGIN in _directive(policy, "connect-src"), (
            f"{snippet}: CSP must allow the GoatCounter beacon in connect-src"
        )


def test_script_src_stays_strict_on_both_sites() -> None:
    """script-src is the half that actually stops XSS, so it stays strict.

    The blog's build gate (scripts/check_blog_build.py) fails on any inline
    <script> precisely so this line can keep holding.
    """
    for snippet in ("csp_strict", "csp_blog"):
        script_src = _directive(_policy(snippet), "script-src")
        assert "'unsafe-inline'" not in script_src, (
            f"{snippet}: no 'unsafe-inline' in script-src — externalise the "
            "script into blog/assets/js/ instead of widening the policy"
        )


def test_www_style_src_is_strict_but_the_blog_is_not() -> None:
    """The asymmetry is deliberate and load-bearing, so assert BOTH halves.

    www (agentic-stoa/site) emits external stylesheets only and pins that with
    its own build check, so it holds style-src 'self'.

    The blog is Hugo + Hextra, and Hextra emits inline style attributes
    structurally, not sloppily: `cards.html` renders
    style="--hextra-cards-grid-cols: {N}" and `card.html` a templated
    style="{{ $imageStyle | safeCSS }}". Those are per-invocation computed
    values no external stylesheet can carry — identical in v0.12.3, the latest
    release as of 2026-07-26, so this is not a "wait for the next version"
    situation. Applying the strict policy to the blog on 2026-07-26 (#704)
    blanked every card list and every syntax-highlighted code block while the
    server still returned 200 and ArgoCD stayed green.

    Dropping 'unsafe-inline' from the blog therefore requires forking the theme
    first. Delete this assertion only together with that work.
    """
    assert "'unsafe-inline'" not in _directive(_policy("csp_strict"), "style-src"), (
        "www must keep style-src 'self' — it emits external stylesheets only"
    )
    assert "'unsafe-inline'" in _directive(_policy("csp_blog"), "style-src"), (
        "the blog needs style-src 'unsafe-inline' until Hextra stops emitting "
        "templated inline style attributes — see this test's docstring"
    )


def test_each_public_site_imports_headers_and_its_own_csp() -> None:
    text = caddyfile()
    for host, csp in (("www.derio.net", "csp_strict"), ("blog.derio.net", "csp_blog")):
        block = _block(text, host)
        assert "import security_headers" in block, (
            f"{host} does not import security_headers"
        )
        assert f"import {csp}" in block, f"{host} does not import {csp}"
        other = "csp_blog" if csp == "csp_strict" else "csp_strict"
        assert f"import {other}" not in block, (
            f"{host} imports {other} — the two policies are not interchangeable"
        )


def test_www_is_logged_crowdsec_gated_and_proxied() -> None:
    block = _block(caddyfile(), "www.derio.net")
    assert "\n  log\n" in block or "\n\tlog\n" in block, "www has no access log"
    assert "crowdsec" in block, "www is not behind the CrowdSec bouncer"
    assert "reverse_proxy www.www-system.svc:8080" in block, (
        "www must proxy to the in-cluster Service on :8080"
    )


def test_www_degrades_to_the_holding_page() -> None:
    block = _block(caddyfile(), "www.derio.net")
    assert "handle_errors" in block, (
        "www.derio.net must fall back to the holding page when its backend is "
        "unreachable — otherwise the first deploy (before any image exists) "
        "serves a 502 instead of today's 'Coming soon.'"
    )
    errors = block[block.index("handle_errors") :]
    assert "Coming soon." in errors and "200" in errors
    # handle_errors runs its own handler chain: the site-level header mutations
    # do NOT reach it (verified live 2026-07-26, when the fallback served 200
    # with no HSTS/CSP and leaked `Server: Caddy`). Both imports must be repeated
    # inside the block or the hardening lapses exactly during an outage.
    assert "import security_headers" in errors, (
        "www's handle_errors fallback does not re-import security_headers"
    )
    assert "import csp_strict" in errors, (
        "www's handle_errors fallback does not re-import csp_strict"
    )
