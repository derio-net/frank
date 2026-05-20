# Reference-pool — curated style anchors for `scripts/generate-all-images.py`

When the generator runs, it passes additional reference images alongside
the primary `--reference` so Gemini has worked examples of the target
visual style. Each image is sampled randomly from the appropriate subdir
on every call.

## Layout

```
.reference-pool/
  generic/     # canonical Frank character signature (applies to every key)
  papers/      # Frank Papers covers — dark navy + glasses + tie
  building/    # Building Frank covers
  operating/   # Operating Frank covers
```

Key → series mapping (`scripts/generate-all-images.py::_key_to_series`):

| Key prefix | Pool subdir |
|---|---|
| `paper-*` | `papers/` |
| `building-*` | `building/` |
| `ops-*` | `operating/` |
| anything else | (generic only) |

`generic/` is sampled for **every** key in addition to its series subdir.

## How many images per call

CLI knobs (defaults shown):

```
--pool-generic 1   # how many from generic/
--pool-series 2    # how many from the key's series subdir
--archive-cap 30   # max entries kept per key in .regen-archive/
--seed N           # seed the sampler for reproducibility (default: system random)
```

Set either pool count to `0` to skip that pool. Image models can be
muddled by too many references; 1+2 is the sweet spot in practice.

## Workflow

1. Run a generation session. Successful outputs land in
   `.regen-archive/<key>/<key>-<sha12>.{png,txt}` — the sidecar `.txt`
   records the exact prompt sections AND the reference images used
   (with their SHA-256). Capped at `--archive-cap` per key (FIFO).
2. Browse the archive after a session. Pair each `.png` with its
   `.txt` to see what produced it.
3. Promote keepers: `cp .regen-archive/<key>/<key>-<sha>.png .reference-pool/<series>/<descriptive-name>.png`
4. Next generation session picks up the new pool entries automatically.

## What belongs in the pool

- **Curated keepers only.** A pool image is a positive anchor — the
  model will steer toward it.
- **Self-consistent palette per subdir.** Mixing wildly different
  styles in one subdir dilutes the anchor.
- **Filenames are descriptive, not auto-generated.** Use
  `frank-thinking-papers-pose.png` not `paper-09-cover-abc123.png`.
- **Keep the pool small.** 3-8 images per subdir is plenty; more
  invites the sampler to pick low-quality entries.

## What does NOT belong

- TODO placeholders, cluster screenshots, anything labelled `-TODO`.
- The reference image itself (`blog/static/images/reference.png`) —
  that's already passed via `-r`.
- Drafts that ended up superseded — clean them out periodically.
