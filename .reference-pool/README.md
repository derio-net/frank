# Reference-pool — character anchors for `scripts/generate-all-images.py`

Three sources of reference images go into every Gemini call. They stack:

1. **Master per-series reference** (1 image) — auto-picked from
   `<series>/reference-<series>.png`. Set series via the entry's
   `series:` field, or rely on the key-prefix fallback. Override
   for an entire run with `-r path/to/custom.png`.
2. **Explicit `references:` field** on the prompt entry (0–N images) —
   hand-picked anchors, usually from `<series>/subjects/`. The most
   common multi-reference path. Loaded by `select_explicit_refs`.
3. **Random pool sampling** (0–N images per call) — opt in with
   `--pool-generic N` / `--pool-series N`. Samples from `<series>/`
   (NOT `subjects/`); useful when the keeper pool is large enough to
   benefit from rotation.

All three are passed to the model together. Compose, don't replace.

## Layout

```
.reference-pool/
  README.md
  generic/
    reference-generic.png        # master ref for entries with no series/
                                 # unknown key prefix (auto-picked)
    subjects/                    # hand-curated single-character renders
                                 # (transparent-background PNGs)
  papers/
    reference-papers.png         # master ref for entries with series: papers
                                 # or key starting with paper-
    subjects/                    # papers-flavoured character renders
    tile-papers.png              # landing-page tile (also lives at
                                 # blog/static/images/tile-papers.png)
  building/
    reference-building.png       # master ref for series: building / building-
    subjects/                    # building-flavoured character renders
    tile-building.png            # landing-page tile (also at blog/static/)
  operating/
    reference-operating.png      # master ref for series: operating / ops-
    subjects/                    # operating-flavoured character renders
    tile-operating.png           # landing-page tile (also at blog/static/)
```

Key → series mapping (`scripts/generate-all-images.py::_key_to_series`):

| Key prefix | Series |
|---|---|
| `paper-*` | `papers` |
| `building-*` | `building` |
| `ops-*` | `operating` |
| anything else | `generic` (used by site-wide assets — banners, favicon) |

The same prefix table drives both the master-reference picker
(`select_reference_path`) and the pool sampler (`load_pool_refs`).

## Master per-series references

Each `<series>/reference-<series>.png` is the canonical character
anchor for that series — Gemini sees it on every generation in that
series. Keep one image per series. To regenerate:

- **If a clean character render exists in `<series>/subjects/`** (it
  usually does — those PNGs already have transparent backgrounds),
  crop one to its alpha bounding box and save as
  `<series>/reference-<series>.png`. This is the preferred path.
- **If only a scene image (e.g., a tile) is available**, run
  `scripts/extract-subject.swift <input> <output>` to subject-isolate
  it via Apple Vision (macOS 14+; uses `VNGenerateForegroundInstance-
  MaskRequest`). Output is a transparent PNG cropped to the subject
  bounding box. See the script's header for failure modes — Vision
  under-segments Frank in busy scenes and doesn't recognise him as a
  person via `VNGeneratePersonSegmentationRequest`.

Provenance of the current per-series references is in their commit
history: `git log --oneline -- .reference-pool/<series>/reference-*`.

## How many images per call

CLI knobs (master ref is auto-picked, no flag needed):

```
--pool-generic 0   # how many from generic/ — default off
--pool-series 0    # how many from the key's series subdir — default off
--archive-cap 30   # max entries kept per key in .regen-archive/
--seed N           # seed the sampler for reproducibility
-r path.png        # override the master ref for this run (applies to all)
```

`references:` on an image entry is the canonical multi-ref path —
explicit, version-controlled, predictable. The pool flags are for
agentic regenerations where some variation is desirable.

Image models get muddled by too many references; 1 master + 1–2
explicit is the sweet spot. Two `references:` paths plus the master
is the common case.

## Workflow

1. Run a generation session. Successful outputs land in
   `.regen-archive/<key>/<key>-<sha12>.{png,txt}` — the sidecar `.txt`
   records the exact prompt sections AND the reference images used
   (with their SHA-256). Capped at `--archive-cap` per key (FIFO).
2. Browse the archive after a session. Pair each `.png` with its
   `.txt` to see what produced it.
3. Promote keepers as new subjects:
   `cp .regen-archive/<key>/<key>-<sha>.png .reference-pool/<series>/subjects/<descriptive-name>.png`
   Then reference them from `references:` on the relevant prompt entry.
4. To replace the master per-series reference, see "Master per-series
   references" above.

## What belongs in `subjects/`

- **Curated keepers only.** A subject image is a positive anchor — the
  model will steer toward it.
- **Self-consistent palette per subdir.** Mixing wildly different
  styles in one subdir dilutes the anchor.
- **Filenames are descriptive, not auto-generated.** Use
  `frank-white-shirt-black-tie-1.png` not `paper-09-cover-abc123.png`.
- **Transparent-background single-figure PNGs preferred.** Easier for
  Gemini to use as a character anchor; cleaner output.
- **Keep each subdir small.** 3–8 images per series is plenty; more
  invites the sampler to pick low-quality entries when `--pool-series`
  is in use.

## What does NOT belong

- TODO placeholders, cluster screenshots, anything labelled `-TODO`.
- Drafts that ended up superseded — clean them out periodically.
- Tile files in directories where they aren't expected — tile-*.png
  files at the root of papers/, building/, operating/ are pinned for
  use as the landing-page card thumbnails and as fallback sources for
  the Swift Vision tool.
