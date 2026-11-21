#!/usr/bin/env bash
# Exit 0 iff ghcr.io/<owner>/<name>:<tag> exists AND is pullable anonymously.
#
# Frank pulls GHCR images with no imagePullSecret, so "pushed" is not enough:
# a first push creates the package PRIVATE, and the Deployment then sits in
# ImagePullBackOff. This check asks the registry exactly what the kubelet will
# ask: an anonymous pull token, then the manifest.
#
# Needs only curl and python3, so it runs inside frank's ops devcontainer
# (which has no docker). Used by the speech plan's post-merge image ops.
#
# Usage: scripts/ghcr-tag-pullable.sh <owner>/<name> <tag>
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <owner>/<name> <tag>" >&2
  exit 2
fi
repo=$1
tag=$2
case "$repo" in
  */*) ;;
  *) echo "repository must be <owner>/<name>, got: $repo" >&2; exit 2 ;;
esac
if ! printf '%s' "$repo$tag" | grep -Eq '^[A-Za-z0-9._/-]+$'; then
  echo "refusing unexpected characters in: $repo:$tag" >&2
  exit 2
fi

token_json=$(curl -fsS "https://ghcr.io/token?scope=repository:${repo}:pull") || {
  echo "ghcr.io/${repo}: no anonymous pull token (package private or missing)" >&2
  exit 1
}
token=$(printf '%s' "$token_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))')
if [ -z "$token" ]; then
  echo "ghcr.io/${repo}: anonymous token response had no token" >&2
  exit 1
fi

accept='application/vnd.oci.image.index.v1+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.docker.distribution.manifest.v2+json'
code=$(curl -sS -o /dev/null -w '%{http_code}' -I \
  -H "Authorization: Bearer ${token}" -H "Accept: ${accept}" \
  "https://ghcr.io/v2/${repo}/manifests/${tag}")
if [ "$code" = 200 ]; then
  echo "ghcr.io/${repo}:${tag} is present and anonymously pullable"
  exit 0
fi
echo "ghcr.io/${repo}:${tag} not anonymously pullable (HTTP ${code}); if the build ran, set the package public" >&2
exit 1
