#!/usr/bin/env bash
# scaffold-paper.sh — create a paper page-bundle + research dossier in a
# blog-craft blog. Config-driven: reads content_types.papers (dossier_dir,
# weight_offset) and the papers series key from .blog-craft.yaml.
#
# Usage: scaffold-paper.sh --config <.blog-craft.yaml> <NN> <slug>
set -euo pipefail

# Config parsing needs PyYAML; blogs run this in their venv (see README).
# Override the interpreter with PYTHON=... if python3 lacks pyyaml.
PYTHON="${PYTHON:-python3}"

CONFIG=""
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2;;
    *) ARGS+=("$1"); shift;;
  esac
done
NN="${ARGS[0]:?Usage: scaffold-paper.sh --config <cfg> <NN> <slug>}"
SLUG="${ARGS[1]:?Usage: scaffold-paper.sh --config <cfg> <NN> <slug>}"
CONFIG="${CONFIG:?--config <.blog-craft.yaml> required}"

# Extract config values (weight_offset, dossier_dir, papers series key).
read -r WEIGHT_OFFSET DOSSIER_DIR PAPERS_KEY < <("$PYTHON" - "$CONFIG" <<'PY'
import sys, yaml
c = yaml.safe_load(open(sys.argv[1])) or {}
p = (c.get("content_types") or {}).get("papers") or {}
pk = next((s["key"] for s in (c.get("series") or []) if s.get("content_type") == "papers"), "papers")
print(p.get("weight_offset", 1), p.get("dossier_dir", "docs/papers-dossiers"), pk)
PY
)

ROOT="$(cd "$(dirname "$CONFIG")" && pwd)"
TODAY="$(date +%Y-%m-%d)"
PADDED="$(printf '%02d' "$((10#$NN))")"
DIR="${PADDED}-${SLUG}"
BUNDLE="$ROOT/content/docs/${PAPERS_KEY}/${DIR}"
DOSSIER="$ROOT/${DOSSIER_DIR}/${DIR}"
WEIGHT="$(( 10#$NN + WEIGHT_OFFSET ))"

if [[ -e "$BUNDLE" || -e "$DOSSIER" ]]; then
  echo "ERROR: ${DIR} already exists (bundle or dossier)" >&2
  exit 1
fi
mkdir -p "$BUNDLE/data" "$DOSSIER"

# weight = paper_number + weight_offset (Hextra sorts weight:0 last; enforced by validate_papers.py)
cat > "$BUNDLE/index.md" <<FM
---
title: "TODO: Paper title"
date: ${TODAY}
draft: true
weight: ${WEIGHT}
series: [${PAPERS_KEY}]
layer: TODO
paper_number: ${NN}
publish_order: TODO
status: drafting
tldr: |
  TODO: exec summary, <=150 words. Write last.
tags: ["TODO"]
capabilities: ["TODO"]
related_building: ""
related_operating: ""
---

{{< papers/dossier-link paper="${DIR}" >}}

## TL;DR

*Write last.*

## §1 — The capability

*200–350 words. 1 Mermaid flowchart LR (stack position).*

## §2 — The landscape

*400–600 words. 1 quadrantChart + 1 capability-matrix.*

## §3 — How each option handles the hard part

*800–1400 words. 1 architecture diagram per vendor.*

## §4 — What scale changes

*300–600 words. Charts or ≥2 primary-source citations.*

## §5 — The choice, and what happened

*300–600 words. ≥1 scar callout.*

## §6 — When this answer doesn't generalize

*200–400 words. 1 decision flowchart ≤4 leaves.*

## §7 — Roadmap & where this space is going

*200–400 words.*
FM

# Dossier: markdown `## H2` sections whose bodies are YAML (parsed by dossier_parser.py).
cat > "$DOSSIER/dossier.md" <<DOSS
# Dossier: ${DIR}

Fill the sections below until \`validate_dossier.py --config <cfg> ${DOSSIER_DIR}/${DIR}/dossier.md\` passes.

## Vendors in scope (>=3)
- {name: "TODO", positioning: "TODO one-line claim", primary_url: "https://TODO"}

## Primary sources (>=5, >=3 distinct type values)
- {title: "TODO", type: vendor-docs, url: "https://TODO", relevance: "one sentence"}

## Artefacts (>=3, >=2 distinct kind values)
- {kind: yaml, path_or_url: "TODO", date: "${TODAY}", demonstrates: "one sentence"}

## Named gaps (>=1)
- "TODO: gap description"

## Counter-arguments considered (>=1)
- "TODO: counter-argument"
DOSS

echo "Scaffolded paper ${NN}:"
echo "  bundle:  content/docs/${PAPERS_KEY}/${DIR}/"
echo "  dossier: ${DOSSIER_DIR}/${DIR}/dossier.md"
