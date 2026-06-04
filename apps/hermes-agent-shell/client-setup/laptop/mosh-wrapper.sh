#!/usr/bin/env bash
# Mosh into the hermes-agent-shell pod.
#
# Why a wrapper:
#   - mosh-server picks one UDP port from a *fixed range* at session start.
#     We pin that range to 60032–60047 to match the LoadBalancer Service
#     (apps/hermes-agent-shell/manifests/service.yaml). The default 60000–61000
#     would wander outside the published range and the session would never
#     reach the client.
#   - Single LB IP for this shell (TCP/22 + UDP 60032–60047), like ruflo /
#     paperclip. So mosh's positional argument doubles as the SSH host:
#     192.168.55.226.
#
# Substitute the IdentityFile for your private key (its public half is in the
# hermes-agent-shell-ssh-keys Secret).
set -euo pipefail
exec mosh \
    --server="mosh-server new -p 60032:60047" \
    --ssh="ssh -i ~/.ssh/<your_private_key>" \
    "$@" \
    agent@192.168.55.226
