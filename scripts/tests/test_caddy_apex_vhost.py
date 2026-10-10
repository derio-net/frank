"""Tripwire: Hop's Caddy serves the derio.net apex as a redirect to www (frank#830).

THE FAILURE. The Caddyfile named `www.derio.net` but never the bare apex, and
Caddy only obtains certificates for site addresses it is configured with. So
a TLS handshake carrying SNI `derio.net` got alert 80 (internal_error) from
the origin, and Cloudflare — which proxies the apex record — reported it to
every visitor as **525**. Measured 2026-10-10: `openssl s_client -connect
<hop>:443 -servername derio.net` → alert 80, while the same probe with
`www.derio.net` presented a valid cert. The public site's shortest URL was
down while www, blog and every monitor stayed green, because nothing probed
the apex.

THE FIX. An apex vhost that permanently redirects to www, preserving the
path. Caddy issues the cert by DNS-01 (`acme_dns cloudflare`), so it works
whether the record is proxied or DNS-only.

THE TRAP THIS ALSO PINS. The apex must NOT import `security_headers`: that
snippet's HSTS carries `includeSubDomains`, which on www/blog scopes to names
under those hosts, but sent from the apex binds EVERY *.derio.net name to
HTTPS-only in the browser for a year — the same one-way door the Caddyfile
already refuses for `preload`. A bare redirect has nothing to harden. Nor
may it carry `crowdsec`/`log`: behind Cloudflare's proxy every remote IP is
a Cloudflare edge (see the last test).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CADDY_FILE = REPO_ROOT / "clusters/hop/apps/caddy/manifests/files/Caddyfile"


def _block(text: str, host: str) -> str:
    """Return the top-level block for exactly `host` (brace-balanced).

    Anchored on a preceding newline so `derio.net {` never matches inside
    `www.derio.net {`.
    """
    marker = f"\n{host} {{"
    assert marker in text, f"no top-level `{host} {{` site block in the Caddyfile"
    start = text.index(marker)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"unbalanced block for {host}")


def _directives(block: str) -> list[str]:
    return [
        ln.strip()
        for ln in block.splitlines()[1:]
        if ln.strip() and not ln.strip().startswith("#")
    ]


def test_apex_vhost_exists() -> None:
    _block(CADDY_FILE.read_text(), "derio.net")


def test_apex_permanently_redirects_to_www_preserving_the_path() -> None:
    directives = _directives(_block(CADDY_FILE.read_text(), "derio.net"))
    assert "redir https://www.derio.net{uri} permanent" in directives, (
        "the apex must 301 to www with the request URI preserved, "
        f"got: {directives}"
    )


def test_apex_does_not_send_hsts() -> None:
    block = _block(CADDY_FILE.read_text(), "derio.net")
    assert "import security_headers" not in block, (
        "security_headers carries HSTS includeSubDomains; from the apex that "
        "pins every *.derio.net name to HTTPS-only for a year"
    )
    assert "Strict-Transport-Security" not in block


def test_apex_neither_bounces_nor_logs_cloudflare_edges() -> None:
    """The apex is Cloudflare-proxied, so its remote IP is always a CF edge.

    A `crowdsec` handler there can only ban a Cloudflare POP (and every real
    visitor behind it); a `log` there feeds CrowdSec signals that name
    Cloudflare as the attacker. www, which the redirect lands on, is
    DNS-only and carries both.
    """
    directives = _directives(_block(CADDY_FILE.read_text(), "derio.net"))
    assert "crowdsec" not in directives, directives
    assert "log" not in directives, directives
