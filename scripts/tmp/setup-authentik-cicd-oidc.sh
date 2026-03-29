#!/usr/bin/env bash
# Create Authentik OIDC providers and applications for Gitea and Zot.
# Prints client secrets to store in Infisical.
#
# Usage:
#   export AK_TOKEN="<your authentik api token>"
#   bash scripts/tmp/setup-authentik-cicd-oidc.sh
#
# To get a token (if you don't have one):
#   kubectl exec -n authentik deploy/authentik-server -it -- ak shell -c "
#   from authentik.core.models import Token, TokenIntents, User
#   user = User.objects.get(username='akadmin')
#   token, _ = Token.objects.get_or_create(
#       identifier='cicd-setup',
#       defaults={'user': user, 'intent': TokenIntents.INTENT_API})
#   print(token.key)"

set -euo pipefail

AK_URL="http://192.168.55.211:9000"

if [ -z "${AK_TOKEN:-}" ]; then
  echo "Error: AK_TOKEN not set. Export your Authentik API token first."
  exit 1
fi

api() {
  curl -sf -H "Authorization: Bearer $AK_TOKEN" -H "Content-Type: application/json" "$@"
}

echo "=== Looking up flow PKs ==="

AUTH_FLOW=$(api "$AK_URL/api/v3/flows/instances/?slug=default-provider-authorization-implicit-consent" \
  | jq -r '.results[0].pk')
INVAL_FLOW=$(api "$AK_URL/api/v3/flows/instances/?slug=default-provider-invalidation-flow" \
  | jq -r '.results[0].pk')

if [ "$AUTH_FLOW" = "null" ] || [ -z "$AUTH_FLOW" ]; then
  echo "Error: Could not find authorization flow. Available flows:"
  api "$AK_URL/api/v3/flows/instances/" | jq '.results[] | {slug, pk}'
  exit 1
fi

if [ "$INVAL_FLOW" = "null" ] || [ -z "$INVAL_FLOW" ]; then
  echo "Error: Could not find invalidation flow. Available flows:"
  api "$AK_URL/api/v3/flows/instances/" | jq '.results[] | {slug, pk}'
  exit 1
fi

echo "  Authorization flow: $AUTH_FLOW"
echo "  Invalidation flow:  $INVAL_FLOW"

# --- Gitea ---
echo ""
echo "=== Creating Gitea OIDC provider ==="

GITEA_PROVIDER=$(api -X POST "$AK_URL/api/v3/providers/oauth2/" -d "{
  \"name\": \"Gitea\",
  \"authorization_flow\": \"$AUTH_FLOW\",
  \"invalidation_flow\": \"$INVAL_FLOW\",
  \"redirect_uris\": [{\"matching_mode\": \"strict\", \"url\": \"http://192.168.55.209:3000/user/oauth2/authentik/callback\"}],
  \"client_type\": \"confidential\"
}")

GITEA_PK=$(echo "$GITEA_PROVIDER" | jq -r '.pk')
GITEA_CLIENT_ID=$(echo "$GITEA_PROVIDER" | jq -r '.client_id')
GITEA_CLIENT_SECRET=$(echo "$GITEA_PROVIDER" | jq -r '.client_secret')

echo "  Provider PK:    $GITEA_PK"
echo "  Client ID:      $GITEA_CLIENT_ID"
echo "  Client Secret:  $GITEA_CLIENT_SECRET"

echo "=== Creating Gitea application ==="

api -X POST "$AK_URL/api/v3/core/applications/" -d "{
  \"name\": \"Gitea\",
  \"slug\": \"gitea\",
  \"provider\": $GITEA_PK
}" | jq '{name, slug}'

# --- Zot ---
echo ""
echo "=== Creating Zot OIDC provider ==="

ZOT_PROVIDER=$(api -X POST "$AK_URL/api/v3/providers/oauth2/" -d "{
  \"name\": \"Zot\",
  \"authorization_flow\": \"$AUTH_FLOW\",
  \"invalidation_flow\": \"$INVAL_FLOW\",
  \"redirect_uris\": [{\"matching_mode\": \"strict\", \"url\": \"http://192.168.55.210:5000/auth/callback\"}],
  \"client_type\": \"confidential\"
}")

ZOT_PK=$(echo "$ZOT_PROVIDER" | jq -r '.pk')
ZOT_CLIENT_ID=$(echo "$ZOT_PROVIDER" | jq -r '.client_id')
ZOT_CLIENT_SECRET=$(echo "$ZOT_PROVIDER" | jq -r '.client_secret')

echo "  Provider PK:    $ZOT_PK"
echo "  Client ID:      $ZOT_CLIENT_ID"
echo "  Client Secret:  $ZOT_CLIENT_SECRET"

echo "=== Creating Zot application ==="

api -X POST "$AK_URL/api/v3/core/applications/" -d "{
  \"name\": \"Zot\",
  \"slug\": \"zot\",
  \"provider\": $ZOT_PK
}" | jq '{name, slug}'

# --- Summary ---
echo ""
echo "=========================================="
echo "  Store these in Infisical:"
echo "=========================================="
echo "  GITEA_OIDC_CLIENT_SECRET=$GITEA_CLIENT_SECRET"
echo "  ZOT_OIDC_CLIENT_SECRET=$ZOT_CLIENT_SECRET"
echo ""
echo "  Client IDs (for values.yaml if needed):"
echo "  Gitea: $GITEA_CLIENT_ID"
echo "  Zot:   $ZOT_CLIENT_ID"
echo ""
echo "  OIDC discovery URLs:"
echo "  Gitea: http://192.168.55.211:9000/application/o/gitea/.well-known/openid-configuration"
echo "  Zot:   http://192.168.55.211:9000/application/o/zot/.well-known/openid-configuration"
echo "=========================================="
