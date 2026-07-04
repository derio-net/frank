# Frank image-optimization adoption — plan

Adopt blog-craft #14+#16 WebP pipeline (merged @ 5dc31f8) in frank so the live
blog serves optimized images instead of 90.9 MB of raw PNG. Spec:
docs/superpowers/specs/2026-07-04--repo--frank-image-optimization-adoption-design.md.

Frank's image templates are the pre-change blog-craft baseline (they differ from
blog-craft@5dc31f8 only by opt-image), so they're replaced wholesale; frank's own
single.html (post covers — the 60 MB bulk) is edited in place. Two phases:

1. **Adopt the mechanism** — config (image.optimize on + version bump) + copy the
   merged templates + the two new partials + edit single.html + hugo.toml param.
2. **Relocate banners** static→assets (so Hugo can process them) + verify the
   build emits WebP and the payload drops, masters otherwise untouched.

The post-merge Test Plan (live payload + visual, light/dark) rides in the spec.
