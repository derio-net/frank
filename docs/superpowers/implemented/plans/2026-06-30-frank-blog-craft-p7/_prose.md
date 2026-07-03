# P7 — Migrate frank to consume blog-craft (cutover)

The final phase of the config-migration spec, and the only one in the **frank**
repo. blog-craft phases P1–P6 build and *prove* the framework (PRs
derio-net/blog-craft #4/#5/#6); P7 flips frank from its inline blog tooling to
consuming blog-craft + a config.

## Hard precondition (deferred run)

P7 does not run until **blog-craft P1–P6 are merged** and the reproduction
harness is green — specifically, the frank golden test (P5) must already prove
that `blog-craft + frank.blog-craft.yaml` reproduces frank's blog with zero
structural drift. That proof is the safety of this cutover: frank's config is
not authored here, it is *adopted* from the fixture the harness validated.

## Shape

1. **Wire + adopt** — add the blog-craft plugin to frank's Claude config; drop
   in the proven `.blog-craft.yaml`.
2. **Reproduction gate** — re-run the harness against frank's *real* `blog/`;
   zero drift is go/no-go. Any drift is fixed in blog-craft (rework), never
   hand-patched in frank.
3. **Retire inline tooling** — delete the inline skills + diverged scripts now
   owned by blog-craft; keep frank *content* (reference-pool images, prompt
   entries, roadmap data); repoint frank's rules + AGENTS.md at blog-craft.
4. **Verify** — Hugo builds, CI green (repointed at blog-craft validators),
   stoa still green.

## Why one agentic phase

Everything is agent-completable once the precondition holds: config adoption,
deletions, rule edits, and verification are all deterministic. The only
"manual" element — merging the blog-craft PRs — is a cross-repo gate satisfied
before this run starts, not a step inside it.

## Not here

The framework itself (P1–P6) lives in blog-craft. This plan is the thin,
reviewed cutover that makes frank the second proof of "blog-craft + config".
