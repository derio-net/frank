#!/usr/bin/env bash
# Remove PaperMod-specific 'cover' block from all post frontmatter.
# Keeps: title, date, draft, tags, summary, weight
# Removes: cover (image, alt, relative)
set -euo pipefail

for f in blog/content/docs/building/*/index.md blog/content/docs/operating/*/index.md; do
  echo "Processing: $f"
  # Use awk to remove the cover block (cover: through next non-indented line)
  awk '
    /^cover:/ { in_cover=1; next }
    in_cover && /^  / { next }
    in_cover && !/^  / { in_cover=0 }
    !in_cover { print }
  ' "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
done

echo "Done. Processed $(find blog/content/docs -name 'index.md' | wc -l) files."
