# Blog build gotchas

Full prose for the `Process / practice` one-liners in `agents/rules/frank-gotchas.md`
that concern the Hugo/Hextra build itself.

## Hextra downloads `@latest` bundles at build time — the theme pin is not a build pin

**Symptom (2026-09-06, #787).** `blog-validate` failed the mermaid width gate on
8 of 186 diagrams (`operating/11-public-edge` measured 2214px against a 1400px
budget; the last green main run had it at 1367px). The PR touched no diagram
source. Two wrong theories cost an hour each: the reader-experience CSS (ruled
out — the gate renders diagrams in a bare page with only the mermaid bundle),
and a Chrome 151→152 bump on the runner (ruled out — the same widths reproduced
locally on both main and the branch, which only proved both builds fetched the
same bundle).

**Cause.** Hextra v0.12.3's `layouts/_partials/scripts/mermaid.html` defaults
`params.mermaid.base` to `https://cdn.jsdelivr.net/npm/mermaid@latest/dist` and
`resources.GetRemote`s the bundle on every build. `go.mod` pins Hextra; nothing
pinned mermaid. Main's last blog build (2026-08-15) got 11.16.1; mermaid 11.17.0
shipped 2026-08-19 and changed flowchart layout; the PR build got 11.17.2. Any
`blog/**` push to main would have failed identically. The same `@latest` default exists for
`imageZoom.base`, `asciinema.base` and `math.katex.base` (unused here today);
flexsearch is the one remote Hextra pins itself (`search.flexsearch.version`,
default 0.8.143), so search does not float.

**Proof.** The same built `public/` with the 11.16.1 bundle copied over the
11.17.2 file passed 186/186 (widest 1363px). After pinning, the rebuilt bundle
hash equals the one live main serves (`mermaid.min.18327bef…`).

**Fix.** `[params.mermaid] base = "https://cdn.jsdelivr.net/npm/mermaid@11.16.1/dist"`
in `blog/hugo.toml`. `scripts/tests/test_mermaid_bundle_pinned.py` fails the PR if
the base is unset or not an exact `X.Y.Z`. To upgrade: bump the version, rebuild, run
`node blog/scripts/validate_mermaid_layout.mjs --public blog/public --max-width 1400`,
and read the diagrams that moved. Never `latest`.

**Lesson.** "Same result locally" is only evidence when the local build is
independent of the thing under suspicion. Both builds pulled the same floating
CDN artifact, so the local reproduction confirmed the symptom and said nothing
about the cause. The pin belongs upstream in blog-craft's `hugo.toml.tmpl` so
every consumer blog stops floating (follow-up on blog-craft#86).
