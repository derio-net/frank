#!/usr/bin/env bash
# scaffold-paper.sh — create Hugo bundle + dossier for a new Frank Paper.
# Usage: scripts/scaffold-paper.sh <NN> <slug>
# Example: scripts/scaffold-paper.sh 10 self-hosted-inference
set -euo pipefail

NN="${1:?Usage: $0 <NN> <slug>}"
SLUG="${2:?Usage: $0 <NN> <slug>}"
PADDED="$(printf '%02d' "$NN")"
DIR_NAME="${PADDED}-${SLUG}"
TODAY="$(date +%Y-%m-%d)"

BUNDLE_DIR="blog/content/docs/papers/${DIR_NAME}"
DOSSIER_DIR="docs/papers-dossiers/${DIR_NAME}"

if [ -e "$BUNDLE_DIR" ] || [ -e "$DOSSIER_DIR" ]; then
  echo "ERROR: ${DIR_NAME} already exists (bundle or dossier)" >&2
  exit 1
fi

mkdir -p "$BUNDLE_DIR/data"
mkdir -p "$DOSSIER_DIR"

# --- Hugo page bundle ---
cat > "${BUNDLE_DIR}/index.md" <<FRONTMATTER
---
title: "TODO: Paper title"
date: ${TODAY}
draft: true
weight: $((10#${NN} + 1))
series: papers
layer: TODO
paper_number: ${NN}
publish_order: TODO
status: drafting
tldr: |
  TODO: Three-paragraph exec summary, ≤150 words. Write this last.
tags: ["TODO"]
capabilities: ["TODO"]
related_building: ""
related_operating: ""
---

{{< papers/dossier-link paper="${DIR_NAME}" >}}

## TL;DR

*Write last.*

## §1 — The capability

*200–350 words. 1 Mermaid flowchart LR showing stack position.*

## §2 — The landscape

*400–600 words. 1 quadrantChart + 1 capability-matrix.*

## §3 — How each option handles the hard part

*800–1400 words. 1 architecture diagram per vendor.*

## §4 — What scale changes

*300–600 words. Charts or ≥2 primary-source citations.*

## §5 — Frank's choice, and what happened

*300–600 words. ≥1 scar callout.*

## §6 — When Frank's answer doesn't generalize

*200–400 words. 1 decision flowchart ≤4 leaves.*

## §7 — Roadmap & where this space is going

*200–400 words.*
FRONTMATTER

# --- Research dossier ---
cat > "${DOSSIER_DIR}/dossier.md" <<DOSSIER
---
paper: ${DIR_NAME}
status: draft
---

## Vendors in scope (≥3, typically 4–6)
- name: TODO
  positioning: "one-line claim from their own marketing"
  primary_url: "https://TODO"

## Primary sources (≥5, ≥3 distinct type values)
- title: "TODO"
  type: vendor-docs
  url: "https://TODO"
  quoted_passages: []
  relevance: "one sentence"

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "TODO"
  date: ${TODAY}
  demonstrates: "one sentence"

## Diagrams planned
- landscape:
    x_axis: "TODO ↔ TODO"
    y_axis: "TODO ↔ TODO"
    vendors_plotted: []
- architecture_comparison:
    vendors: []
- decision_tree:
    leaves: 4

## Named gaps (≥1)
- "TODO: gap description"

## Counter-arguments considered (≥1)
- "TODO: counter-argument"
DOSSIER

echo "Scaffolded Paper ${NN}:"
echo "  Hugo bundle:  ${BUNDLE_DIR}/"
echo "  Dossier:      ${DOSSIER_DIR}/dossier.md"
echo ""
echo "Next steps:"
echo "  1. Edit ${DOSSIER_DIR}/dossier.md — fill vendors, sources, artefacts"
echo "  2. python scripts/validate-dossier.py ${DOSSIER_DIR}/dossier.md"
echo "  3. Draft ${BUNDLE_DIR}/index.md"
