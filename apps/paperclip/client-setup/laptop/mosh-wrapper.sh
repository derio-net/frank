#!/usr/bin/env bash
# Mosh into the paperclip-shell sidecar.
#
# Why a wrapper:
#   - mosh-server picks one UDP port from a *fixed range* at session start.
#     We pin that range to 60000–60015 to match the LoadBalancer Service
#     (apps/paperclip/manifests/service-shell.yaml). Default 60000–61000
#     would wander outside the published range and the session would
#     never reach the client.
#   - Single LB IP for paperclip-shell (TCP/22 + UDP 60000–60015), like
#     ruflo-shell. So mosh's positional argument doubles as the SSH host:
#     192.168.55.221.
set -euo pipefail
exec mosh \
    --server="mosh-server new -p 60000:60015" \
    --ssh="ssh -i ~/.ssh/lab/id_rsa_raspi" \
    "$@" \
    agent@192.168.55.221
