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


def test_csp_admits_analytics_and_forbids_framing() -> None:
    text = caddyfile()
    csp = [ln for ln in text.splitlines() if "Content-Security-Policy" in ln]
    assert csp, "no Content-Security-Policy"
    policy = csp[0]

    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy, (
        "frame-ancestors 'none' replaces X-Frame-Options; without it the sites "
        "are clickjackable"
    )
    # GoatCounter serves the script and receives the beacon.
    assert f"script-src 'self' {ANALYTICS_ORIGIN}" in policy, (
        "CSP must allow the GoatCounter script, or analytics dies silently"
    )
    assert ANALYTICS_ORIGIN in policy.split("connect-src")[1].split(";")[0], (
        "CSP must allow the GoatCounter beacon in connect-src"
    )
    assert "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0], (
        "no 'unsafe-inline' in script-src — the sites ship no inline scripts"
    )


def test_both_public_sites_import_the_snippet() -> None:
    text = caddyfile()
    for host in ("www.derio.net", "blog.derio.net"):
        assert "import security_headers" in _block(text, host), (
            f"{host} does not import security_headers"
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
