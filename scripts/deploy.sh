#!/usr/bin/env bash
# Deploy BettingBot to Coolify
# Usage: ./scripts/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

COOLIFY_URL="${COOLIFY_URL:-https://coolify.firmoncloud.com}"
COOLIFY_TOKEN="${COOLIFY_TOKEN:-}"

if [[ -z "$COOLIFY_TOKEN" ]]; then
    echo "❌ COOLIFY_TOKEN not set"
    exit 1
fi

echo "🚀 Deploying BettingBot to Coolify..."

# Check if app exists, create if not
APP_NAME="bettingbot"
APP_UUID=""

# Try to find existing app
RESPONSE=$(curl -s -H "Authorization: Bearer $COOLIFY_TOKEN" \
    "$COOLIFY_URL/api/v1/applications")

APP_UUID=$(echo "$RESPONSE" | python3 -c "
import sys, json
apps = json.load(sys.stdin)
for app in apps:
    if app.get('name') == '$APP_NAME':
        print(app.get('uuid', ''))
        break
" 2>/dev/null || echo "")

if [[ -z "$APP_UUID" ]]; then
    echo "📦 Creating new Coolify application..."
    RESPONSE=$(curl -s -X POST \
        -H "Authorization: Bearer $COOLIFY_TOKEN" \
        -H "Content-Type: application/json" \
        "$COOLIFY_URL/api/v1/applications" \
        -d "{
            \"name\": \"$APP_NAME\",
            \"description\": \"AI Football Prediction Telegram Bot\",
            \"git_repository\": \"https://github.com/kelly-oriabure/bettingbot\",
            \"git_branch\": \"main\",
            \"build_pack\": \"dockerfile\",
            \"dockerfile\": \"Dockerfile\",
            \"ports\": [8080],
            \"project_uuid\": \"xgocwgggkoookkwss080ogcs\"
        }")
    
    APP_UUID=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('uuid', ''))
" 2>/dev/null || echo "")
    
    if [[ -z "$APP_UUID" ]]; then
        echo "❌ Failed to create app. Response: $RESPONSE"
        exit 1
    fi
    
    echo "✅ App created: $APP_UUID"
fi

echo "🔧 Configuring environment variables..."
# Set required env vars
ENVS=(
    "TELEGRAM_BOT_TOKEN"
    "API_FOOTBALL_KEY"
    "ODDS_API_KEY"
    "OPENROUTER_API_KEY"
)

for ENV_KEY in "${ENVS[@]}"; do
    ENV_VALUE="${!ENV_KEY:-}"
    if [[ -n "$ENV_VALUE" ]]; then
        curl -s -X PATCH \
            -H "Authorization: Bearer $COOLIFY_TOKEN" \
            -H "Content-Type: application/json" \
            "$COOLIFY_URL/api/v1/applications/$APP_UUID" \
            -d "{\"environment_variables\": {\"$ENV_KEY\": \"$ENV_VALUE\"}}" \
            > /dev/null
        echo "  ✅ $ENV_KEY set"
    else
        echo "  ⚠️ $ENV_KEY not set (set it in Coolify dashboard)"
    fi
done

echo "🚀 Starting deployment..."
curl -s -X POST \
    -H "Authorization: Bearer $COOLIFY_TOKEN" \
    "$COOLIFY_URL/api/v1/applications/$APP_UUID/start" \
    > /dev/null

echo "✅ Deployment initiated!"
echo ""
echo "📊 Check status: $COOLIFY_URL/applications/$APP_UUID"
echo ""
echo "⚠️ Remember to:"
echo "  1. Set TELEGRAM_BOT_TOKEN in Coolify secrets (never in API calls)"
echo "  2. Create the GitHub repo: kelly-oriabure/bettingbot"
echo "  3. Configure FQDN (domain) in Coolify UI"
echo "  4. Run initial training: exec into container and run 'python -m app.train'"
