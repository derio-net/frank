#!/bin/bash
set -e

# Seed baked stoa custom nodes into the PVC-mounted custom_nodes dir.
# The comfyui-custom-nodes PVC mounts at /app/custom_nodes and SHADOWS any
# nodes baked into the image there, so copy them on boot.
#
# Version-gated re-seed (mirrors the hermes-venv-seed pattern): a baked node
# is (1) seeded when absent, and (2) RE-SEEDED (overwritten) when the image's
# seed-version differs from the PVC's recorded one — i.e. on a deliberate image
# bump (COMFYUI_REF / STOA_NODES). This is what makes a Dockerfile node patch
# actually reach the PVC on a bump; seed-if-absent alone let a stale unpatched
# copy shadow it forever (the kornia-`pad` ImportError after the v0.24 bump).
# Manager-installed / operator-added nodes are NOT in $STAGE, so they are never
# touched; in-PVC edits to a BAKED node are superseded on a version bump (same
# tradeoff as the hermes seed). Unchanged seed-version => behaves as before.
STAGE=/opt/stoa-custom-nodes
DEST=/app/custom_nodes
WANT=""; [ -f "$STAGE/.seed-version" ] && WANT="$(cat "$STAGE/.seed-version")"
HAVE=""; [ -f "$DEST/.stoa-seed-version" ] && HAVE="$(cat "$DEST/.stoa-seed-version")"
if [ -d "$STAGE" ]; then
  for node in "$STAGE"/*/; do
    name="$(basename "$node")"
    if [ ! -d "$DEST/$name" ]; then
      cp -a "$node" "$DEST/$name"
    elif [ -n "$WANT" ] && [ "$WANT" != "$HAVE" ]; then
      rm -rf "$DEST/$name" && cp -a "$node" "$DEST/$name"
    fi
  done
  [ -n "$WANT" ] && printf '%s\n' "$WANT" > "$DEST/.stoa-seed-version"
fi

exec python main.py "$@"
