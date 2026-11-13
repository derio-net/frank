"""Build a Headplane 0.5.5 `hp_sess` cookie signed with a key read from stdin.

Used only to PROBE which key the running Headplane accepts: GET /admin/login
returns 302 to /admin/machines when the cookie's signature verifies, and 200
(the login page) when it does not. The session carries a dummy Headscale API
key, so a verifying cookie still cannot call Headscale.

Format (react-router createCookieSessionStorage): base64(JSON) + "." +
base64(HMAC-SHA256(key, value)) with "=" padding stripped, URI-encoded.
The key is read from stdin and never printed; only the cookie (an HMAC, from
which the key cannot be recovered) is written to stdout.
"""

import base64
import hashlib
import hmac
import json
import sys
import urllib.parse


def forge(key: bytes) -> str:
    value = base64.b64encode(json.dumps({"hsApiKey": "probe-not-a-key"}).encode()).decode()
    sig = base64.b64encode(hmac.new(key, value.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return "hp_sess=" + urllib.parse.quote(f"{value}.{sig}", safe="")


if __name__ == "__main__":
    key = sys.stdin.read().strip().encode()
    if not key:
        sys.exit("forge_cookie: empty key on stdin")
    print(forge(key))
