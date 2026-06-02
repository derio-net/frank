---
name: warn-hextra-weight-zero
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: blog/content/.*\.md$
  - field: content
    operator: regex_match
    pattern: weight:\s*0(?!\d)
---

⚠️ **Hextra sidebar weight trap: `weight: 0`**

This blog post sets `weight: 0`. Hugo treats `weight: 0` as "no weight set" and
sorts those pages **LAST** in the Hextra sidebar — the recurring "00 is at the
bottom" bug.

**Fix — give it a non-zero weight:**

- **Papers:** convention is `weight = paper_number + 1` (Paper 00 → `weight: 1`).
  The `+1` offset exists precisely to dodge the zero-weight trap. Enforced by
  `scripts/validate-papers.py`; see `agents/rules/repo-papers.md`.
- **Building / operating posts:** weight matches the post number, but the **00**
  overview post must use `weight: 1` (not `0`). Apply the same `+1` shift across
  the series if you need to preserve strict numeric order without a collision.

Canonical frontmatter rules: `agents/rules/repo-blog.md`.
