# Journal: 2026-07-26-blog-render-regression

<!-- fr:journal kind=repro scope=debug id=repro-banner created=2026-07-26T14:21:02 -->
### repro-banner · repro · Banners and covers render upscaled from a 960w variant on every section

Operator report: banners very low res; list elements on /frank/docs/papers/ look like plain HTML.

Repro (no browser needed): fetch any section page and read the <img> markup.
  curl -sS https://blog.derio.net/frank/docs/papers/ | grep -o "<img[^>]*banner[^>]*>"

Observed on ALL four sections (/frank/, building, operating, papers):
  banner: src=...banner-papers_hu_*.webp width=2169 srcset="480w, 960w" (no sizes)
  cover : src=...cover_hu_*.webp        width=1424 srcset="480w, 960w" (no sizes)

The full-resolution primary (2169w banner / 1424w cover) is served and 200s, but
appears ONLY in src. Per the HTML spec, once srcset carries w descriptors, src is
not a selection candidate — so the browser can only pick 480w or 960w. With no
sizes attribute it assumes 100vw, so a full-bleed banner on a 1512px Retina
viewport wants ~3024px and gets 960px: a ~3.15x upscale.

<!-- fr:journal kind=ruled-out scope=debug id=ro-sri created=2026-07-26T14:21:02 -->
### ro-sri · ruled-out · RULED OUT: stylesheet blocked by Subresource-Integrity mismatch

Hypothesis: main.min.<sha>.css carries integrity=sha256-...; if the served bytes
differed the browser would silently refuse the stylesheet while curl still saw 200 —
which would explain BOTH an unstyled list and a banner rendered at natural size.

Test: sha256 the served file, identity and --compressed.
  expected bcf3db04...3849 (filename hash == integrity)
  identity 122419 bytes -> bcf3db04...3849  MATCH
  gzip/br  122419 bytes -> bcf3db04...3849  MATCH
Both stylesheets and all JS return 200 with correct hashes. Not SRI.

<!-- fr:journal kind=ruled-out scope=debug id=ro-cache created=2026-07-26T14:21:03 -->
### ro-cache · ruled-out · RULED OUT (as the current cause): stale cached HTML pointing at 404 fingerprinted assets

Hypothesis: Hugo fingerprints asset filenames; if HTML outlives a deploy the browser
requests asset names that no longer exist -> 404 -> fully unstyled page.

Real but bounded: HTML and assets both send cache-control: public, max-age=3600, so the
mismatch window is <=1h and self-heals. Deploy last-modified 2026-07-25 22:47 GMT (~17h
before this report), so it cannot explain what the operator is seeing now. Noting it as a
latent hazard, not this bug.

<!-- fr:journal kind=root-cause scope=debug id=rc-csp created=2026-07-26T14:25:38 -->
### rc-csp · root-cause · Unstyled lists: blog.derio.net inherited a CSP with style-src self, but the Hugo build emits its card CSS inline

CONFIRMED. Caddy sends on blog.derio.net:
  content-security-policy: ... style-src 'self'; ...   (no 'unsafe-inline')

The papers/roadmap cards ship their entire stylesheet as a single inline <style>
block inside the rendered content. The browser refuses to instantiate it:
  document.querySelectorAll('style').length          -> 1   (element present)
  thatStyleElement.sheet                              -> null (BLOCKED)
  [...document.styleSheets]                           -> only the 2 external files
  getComputedStyle('.roadmap-card')  -> border 0px, background transparent, padding 0px
24 cards, zero styling => the operator's "simple html". Page still returns 200 and the
external stylesheets still apply, which is why nav/sidebar/headings look fine.

Origin: clusters/hop/apps/caddy/manifests/configmap.yaml — the blog vhost gained
 in f1ea946e (#704, "blog-parity hardening"), touched again by
5fa500e2 (#705). The snippet was written for agentic-stoa/site, and its own comment
(lines 42-44) states the constraint and predicts the failure mode verbatim:
  "style-src is 'self' with no 'unsafe-inline', which means the site images must emit
   external stylesheets rather than inline <style> blocks. agentic-stoa/site pins that
   with its own build check."
www has that build check. The blog does not, and the blog does emit inline <style>.
The CSP was applied to the blog for parity without the parity constraint being met.

Collateral from the same header: the one inline <script> (the clear-read-history
button handler) is blocked by script-src 'self' and is therefore dead.

<!-- fr:journal kind=root-cause scope=debug id=rc-srcset created=2026-07-26T14:25:38 -->
### rc-srcset · root-cause · Low-res banners: opt-image.html drops the top srcset candidate whenever the source is narrower than the cap

CONFIRMED. blog/layouts/partials/opt-image.html:33-38 builds candidates from
  range $w := (slice 480 960 $maxW)
gated by
  if and (le $w $srcW) (le $w $maxW)

The cap is compared against itself, not against the primary that was actually emitted.
When the SOURCE is narrower than the cap the top candidate fails  and is
dropped, so nothing in the srcset matches the primary's real width:

  banners  src 2169w, bannerMaxWidth 2560 -> 2560 > 2169 -> srcset = 480w, 960w
  covers   src 1424w, maxWidth       1600 -> 1600 > 1424 -> srcset = 480w, 960w

Per the HTML spec, once a srcset carries w descriptors the src attribute stops being a
selection candidate — so the full-resolution file Hugo generated and Caddy serves (200 OK)
is unreachable. There is also no sizes attribute, so the browser assumes 100vw.

Measured live (browser, DPR 2, 849px viewport):
  banner: currentSrc = banner-papers_hu_9ce0a7f02b95736b.webp  (the 960w one)
          displayed 849 CSS px, needs 1698 device px  ->  upscale_factor 2.0
          while a 2169w variant exists at the src URL. has_sizes: false
Wider viewports are worse. Independent of the CSP bug — arithmetic + spec + currentSrc.

<!-- fr:journal kind=finding scope=debug id=f-scope created=2026-07-26T14:38:29 state=open -->
### f-scope · finding [open] · Scope is far wider than reported: the CSP also kills ALL syntax highlighting (9366 inline style attrs from Chroma)

The reported "simple html" lists are the smallest part. A full build (hugo v0.157.0
extended, theme hextra v0.12.1) into /tmp/blogbuild, scanned for CSP-incompatible output:

  <style> blocks   : 7     across 6   files
  inline <script>  : 191   across 111 files
  style= attributes: 9366  across 112 files

The 9366 style attributes are Hugo's Chroma syntax highlighter. hugo.toml has
[markup.highlight] style="monokai" but never sets noClasses=false, and noClasses
defaults to TRUE, so every code token ships as <span style="color:#f92672">.

Live proof on /frank/docs/building/04-gpu-compute/ (24 code blocks, 357 token spans):

  pre.getAttribute("style")   -> "color:#f8f8f2;background-color:#272822;..."
  getComputedStyle(pre).color -> rgb(0, 0, 0)          NOT APPLIED
  token span style="color:#f92672" -> computed rgb(0, 0, 0)

So every code block on a technical blog renders as flat black text with no Monokai
background and no highlighting at all. This was not in the operator report ("perhaps
there are other errors") but is the largest surface by far.

Mermaid survives: .mermaid svg count = 1, because the theme renders diagrams from an
EXTERNAL script; only the inline config script is blocked, so diagrams draw but lose
their theme wiring.

OWNERSHIP (decides what is fixable in this repo):

  OURS   markup.highlight noClasses default             -> 9366 style attrs
  OURS   shortcodes roadmap/papers-roadmap/series-index -> 3 style blocks
  OURS   partials/custom/footer.html                    -> 1 inline script + 1 style attr
  OURS   shortcodes/asciinema.html                      -> 1 inline script
  THEME  _partials/theme-toggle.html:33                 -> style="position: fixed; ..."
  THEME  _partials/language-switch.html:32              -> style="position: fixed; ..."
  THEME  _partials/search.html:26                       -> style="transition: max-height ..."
  THEME  _partials/scripts/mermaid.html                 -> inline mermaid config script

Fixing everything that is ours removes ~99.6% of the inline content, but the pinned
upstream theme still emits ~3 style attributes and 1 script per page. A strict
style-src self therefore cannot be fully satisfied without forking the theme or
hash-allowlisting its residue.

<!-- fr:journal kind=finding scope=debug id=fix-all created=2026-07-26T16:12:18 state=fixed -->
### fix-all · finding [fixed] · Fixed: per-site CSP for the blog, class-based highlighting, externalised scripts, and a reachable srcset top candidate

Two independent root causes, fixed independently.

CSP (clusters/hop/apps/caddy/manifests/configmap.yaml)
  The CSP moved out of the shared (security_headers) snippet into two explicit
  per-site snippets, because www and the blog genuinely need different values and
  hiding that behind a shared default is what caused the incident:

    (csp_strict)  style-src 'self'                     -> www.derio.net
    (csp_blog)    style-src 'self' 'unsafe-inline'     -> blog.derio.net

  script-src stays strict on BOTH. Hextra can never satisfy a strict style-src:
  cards.html renders style="--hextra-cards-grid-cols: {N}" and card.html a
  templated style="{{ $imageStyle | safeCSS }}" — per-invocation computed values
  no external stylesheet can carry. Verified identical in v0.12.3 (latest), so
  waiting for an upstream release was not an option.

  www's handle_errors re-imports both snippets: it runs its own handler chain and
  does not inherit site-level header mutations.

Syntax highlighting (blog/hugo.toml)
  markup.highlight.noClasses = false. Chroma defaulted to true, stamping the
  palette onto ~9,300 token spans as inline style attributes. Class-based output
  is also what Hextra expects — it ships assets/css/chroma/{light,dark}.css at
  `.highlight .chroma .<token>` specificity, so highlighting now follows the
  light/dark toggle instead of being monokai in both.
  A generated chroma.css was tried first and REMOVED: it duplicated the theme's
  stylesheet and lost on specificity every time, silently.

Inline scripts (script-src stays strict, so these had to be externalised)
  blog/assets/js/read-history-clear.js  <- was inline in custom/footer.html; the
      "Clear read history" link had been rendering but doing nothing.
  blog/assets/js/mermaid-init.js        <- external replacement for the theme's
      inline init. Diagrams still drew (mermaid self-starts) but were stuck in
      the light theme and ignored the toggle across all 80 mermaid posts.
  blog/assets/js/asciinema-init.js      <- shortcode now passes config as data-*
      attributes. Latent, not live: 0 posts currently use the shortcode.
  The footer link's inline style attribute became a .clear-read-history class.

srcset (blog/layouts/partials/opt-image.html)
  The top candidate is now $primary.Width instead of $maxW, so the primary is
  always reachable. 179 unreachable-full-resolution images -> 0. The browser now
  selects the 2169w banner and the 1424w cover; it previously could only reach
  960w.

Guards
  scripts/check_blog_build.py — new build-output gate, wired into deploy-blog.yml
  after `hugo --minify`. Asserts no inline <script>, no off-origin assets, and
  that every w-descriptor srcset can reach its own primary. It does NOT police
  inline STYLES: style-src permits them, and policing them would only generate
  busywork against upstream templates frank tracks verbatim. It tolerates exactly
  one documented theme-owned inline script (mermaid), so a theme bump that
  changes that markup surfaces as a failure.

  test_caddy_security_headers.py — previously read only the FIRST CSP line in the
  file, so it never distinguished the two sites and passed straight through the
  regression. Now asserts each vhost imports its own snippet, script-src is
  strict on both, www's style-src is strict AND the blog's is not, and that the
  www fallback re-imports both. Verified non-vacuous by reintroducing the #704
  policy: the suite fails.

  test_image_optimization_adoption.py — the opt-image fix is a divergence from
  blog-craft@5dc31f8, which a byte-equality guard forbids. Rather than overwrite
  the fixture (which would erase the drift signal), the divergence is pinned to
  exactly that hunk: the emit block and preamble must still match byte-for-byte.
  The fix is an UPSTREAM defect and belongs in blog-craft.

Deliberately reverted mid-flight
  The three list shortcodes' <style> blocks were externalised, then put back.
  scripts/tests/test_series_index_resync.py exists specifically so "frank no
  longer carries a divergent copy" of series-index.html and roadmap.html; with
  style-src now permitting inline, that externalisation bought nothing functional
  and re-introduced drift a prior project had removed.

Verification
  hugo build + scripts/check_blog_build.py: OK, 112 pages.
  Full suite: 17 failed / 195 passed — the same 17 that fail on origin/main, and
  zero new failures (baseline captured from `git archive origin/main`).
  Browser: 24 cards styled, banner currentSrc = the 2169w variant, code blocks
  highlighted with 0 inline style attributes in <pre>, mermaid renders.
