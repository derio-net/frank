#!/bin/bash
set -e

# Seed ComfyUI-Manager into the PVC if not already present.
# The image bakes Manager into /app/default_custom_nodes/ComfyUI-Manager,
# but /app/custom_nodes is a PVC mount that shadows any baked-in content.
if [ ! -d /app/custom_nodes/ComfyUI-Manager ]; then
  echo "First boot: seeding ComfyUI-Manager into custom_nodes PVC..."
  cp -r /app/default_custom_nodes/ComfyUI-Manager /app/custom_nodes/
fi

exec python main.py "$@"
