#!/bin/bash
set -e

# Seed ComfyUI-Manager into the PVC if not already present.
# The image bakes Manager into /app/default_custom_nodes/ComfyUI-Manager,
# but /app/custom_nodes is a PVC mount that shadows any baked-in content.
if [ ! -d /app/custom_nodes/ComfyUI-Manager ]; then
  echo "First boot: seeding ComfyUI-Manager into custom_nodes PVC..."
  cp -r /app/default_custom_nodes/ComfyUI-Manager /app/custom_nodes/
fi

# Manager 4.x is a pyproject.toml package — ensure it's pip-installed
# so ComfyUI can discover it. The editable install points at the PVC copy.
if ! python -c "import comfyui_manager" 2>/dev/null; then
  echo "Installing ComfyUI-Manager package..."
  pip install --no-cache-dir -e /app/custom_nodes/ComfyUI-Manager
fi

exec python main.py "$@"
