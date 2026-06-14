#!/bin/bash
set -e

# Seed baked stoa custom nodes into the PVC-mounted custom_nodes dir.
# The comfyui-custom-nodes PVC mounts at /app/custom_nodes and SHADOWS any
# nodes baked into the image there, so copy them on boot. Idempotent: only
# seed a node when it is absent in the PVC (operator edits / Manager installs
# are preserved across restarts).
STAGE=/opt/stoa-custom-nodes
DEST=/app/custom_nodes
if [ -d "$STAGE" ]; then
  for node in "$STAGE"/*/; do
    name="$(basename "$node")"
    if [ ! -d "$DEST/$name" ]; then
      cp -a "$node" "$DEST/$name"
    fi
  done
fi

exec python main.py "$@"
