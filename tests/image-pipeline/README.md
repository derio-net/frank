# Image-Pipeline Tests

Covers the modular cover-image generation pipeline driven by
`blog/prompt_for_images.yaml` and `scripts/generate-all-images.py`.

What the suite checks:

- **Pure functions** in `scripts/generate-all-images.py` — `_key_to_series`,
  `_key_to_torso_default`, `_resolve_reference_guidance`, `_sha256_short`,
  `load_pool_refs`. Pins the homogenisation of `_key_to_series` and
  `_key_to_torso_default` (both recognise the same prefix table).
- **YAML structural integrity** — required top-level keys present, no
  dead `reference_guidance.series` banner-attach block, no legacy
  `base_style` fallback.
- **Per-entry validity** — every image entry has `key`/`output`/`prompt`,
  no duplicate keys, every `torso_variant: <int>` indexes a real option,
  every `mood` is a string, every `references:` path exists on disk.

No external services (no Gemini, no Vision) are touched.

## Run

```bash
uv run --with pytest --with pyyaml --with google-genai --with pillow \
  python -m pytest tests/image-pipeline/ -v
```

`google-genai` and `pillow` are required because the script under test
imports them at module load. The tests themselves never call them.
