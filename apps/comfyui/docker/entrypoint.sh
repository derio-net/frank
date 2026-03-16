#!/bin/bash
set -e

# Seed ComfyUI-Manager into the PVC if not already present.
# The image bakes Manager into /app/default_custom_nodes/ComfyUI-Manager,
# but /app/custom_nodes is a PVC mount that shadows any baked-in content.
if [ ! -d /app/custom_nodes/ComfyUI-Manager ]; then
  echo "First boot: seeding ComfyUI-Manager into custom_nodes PVC..."
  cp -r /app/default_custom_nodes/ComfyUI-Manager /app/custom_nodes/
fi

# Manager 4.x is a pyproject.toml package — create editable link on each boot.
# Dependencies are pre-installed in the image; --no-deps makes this instant.
# The .egg-link is ephemeral (in-container, not on PVC) so this runs every boot.
pip install --no-deps --break-system-packages -e /app/custom_nodes/ComfyUI-Manager 2>&1 | tail -1

exec python main.py "$@"
