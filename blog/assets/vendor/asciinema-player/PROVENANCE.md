# asciinema-player — vendored

Upstream: <https://github.com/asciinema/asciinema-player> · Apache-2.0 (`LICENSE`)
**Version: 3.9.0**

| File | sha256 |
|---|---|
| `asciinema-player.min.js` | `07401a2fec038bd9120d861cfab5a6c88d921f97520460024eec1e7822e829b4` |
| `asciinema-player.css` | `60674b3fc74be35708dd6954fb2268c62b1fa69d03f7aca2b1443cdeb7b4fb72` |

## Why vendored rather than loaded from a CDN

`head-end.html` used to pull both files from `unpkg.com`. That was wrong three
ways at once, and each one is invisible until it bites:

1. **CSP.** A blog serving `script-src 'self'` blocks the off-origin script, so
   the player never loads — silently, the same failure mode as the inline
   `<script>` this shortcode used to emit (#56).
2. **Integrity.** The tags carried no `integrity` attribute, so a compromised or
   substituted CDN response would have executed unchecked on every page using
   the shortcode.
3. **Availability.** A third-party CDN outage or an unpublished version takes the
   feature down with it.

Serving from the blog's own origin resolves all three: same-origin satisfies the
CSP, Hugo fingerprints the published asset, and there is no third party in the
request path. That is why there is no `integrity=` attribute in `head-end.html` —
pinning a hash to a URL the CSP rejects anyway would have been motion without
progress.

Hugo publishes an `assets/` resource only when a template actually retrieves it,
and `head-end.html` gates both behind `{{ if .HasShortcode "asciinema" }}`. So a
blog that never uses the shortcode carries these files in its repo and ships zero
bytes of them to readers.

## Updating

```bash
V=3.9.0   # set to the new version
for f in asciinema-player.min.js asciinema-player.css; do
  curl -fsSL "https://unpkg.com/asciinema-player@${V}/dist/bundle/$f" -o "$f"
done
curl -fsSL "https://raw.githubusercontent.com/asciinema/asciinema-player/v${V}/LICENSE" -o LICENSE
shasum -a 256 asciinema-player.min.js asciinema-player.css   # record above
```

Then update the version and hashes in this file. Check the release notes for
changes to `AsciinemaPlayer.create()`'s option names — `assets/js/asciinema-init.js`
maps the shortcode's `data-*` attributes onto them, and a renamed option fails
silently (the player starts with a default instead).
