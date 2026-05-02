#!/usr/bin/env bash
# Mosh into the ruflo-shell sidecar.
#
# Why a wrapper:
#   - mosh-server picks one UDP port from a *fixed range* at session start.
#     We pin that range to 60016–60031 to match the LoadBalancer Service
#     (apps/ruflo/manifests/service-shell.yaml). Default 60000–61000 would
#     wander outside the published range and the session would never reach
#     the client.
#   - Single LB IP for ruflo (TCP/22 + UDP 60016–60031), unlike
#     secure-agent-pod which splits across two LB IPs. So mosh's positional
#     argument doubles as the SSH host: 192.168.55.222.
set -euo pipefail
exec mosh \
    --server="mosh-server new -p 60016:60031" \
    --ssh="ssh agent@192.168.55.222" \
    "$@" \
    192.168.55.222
