# Frank's persona invariants — reference-pool notes

**Why this file exists.** `.reference-pool/README.md` is **blog-craft-owned**
(`framework`-classified in blog-craft's manifest), so `/blog-craft:update`
replaces it wholesale. It documents the *generic* v5 reference contract. This
file holds the parts that are specific to **Frank** and would otherwise be lost
on the next update. blog-craft materializes only `README.md` and
`generic/subjects/.gitkeep` in this directory and never deletes unknown paths,
so `PERSONA.md` survives every update.

Read `README.md` for the mechanism (one `primary` per entry, `clothing:`
anchors, order is load-bearing). Read this for what Frank must look like.

## The eye design is the invariant

Frank has **large solid-black eyes with a small white pupil highlight**. There
is **never any white sclera**. This is the single most load-bearing detail of
the character: get it wrong and the figure stops reading as Frank even when the
costume, proportions and line work are all correct.

Every sheet under `<series>/reference/` encodes it. When generating a new sheet,
review **every face on the sheet** before promoting it — a sheet with one
off-model face will drag every cover generated from it off-model too.

### The startled-expression trap

A *startled / surprised* expression pulls the image model toward generic
cartoon eyes — white sclera, small dark iris. It is the reliable way to break
the invariant, and it does so silently: the rest of the sheet looks fine.

**Pin the expression row to steady expressions** — neutral / grin / angry /
worried. Do not ask for startled, surprised, shocked, or wide-eyed.

Measured on Gemini; treat it as a property of image models generally rather
than of one vendor, and re-check it after any generator change. Anchoring on
2–3 already-approved sheets is the other half of the defence.

## Pool layout as Frank actually uses it

```
.reference-pool/
  <series>/reference/          # the v5 anchors — one sheet per outfit variant
  <series>/reference-<series>.png   # legacy v4 master ref; unused by v5 entries
  generic/reference/           # entries with no series
    frank-favicon.png          # HEAD-ONLY icon sheet — favicon/tile work only,
                               #   not a full turnaround; don't point a cover at it
```

Series in use: `building`, `operating`, `papers`, plus `generic`.

Filenames are descriptive of the **outfit**, because that is the selection key:
an entry's `clothing:` modifier and its `reference_images.primary` must agree.
Pointing a `papers[white_lab_coat]` entry at a `building/` gear-shirt sheet
produces a technically on-model Frank in the wrong costume, and nothing warns
you — verify with `scripts/generate-images.py --dry-run`.

## Related

- `blog/prompt_for_images.yaml` — the entries that consume these sheets.
- `.blog-craft.yaml` → `image.layers` — the shared character/atmosphere/clothing
  prose; `image.character_sheet.layers` — the sheet-generation prompt.
- `docs/runbooks/banner-generation-handoff/README.md` — banner generation
  (a different pipeline: Codex three-stripe, not character sheets).
- `docs/runbooks/blog-craft-resync.md` — which paths blog-craft owns and how
  frank pulls updates.
