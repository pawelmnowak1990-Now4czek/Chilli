#!/usr/bin/env bash
# Chilli setup: asks a few questions, writes .env, starts the containers and runs the doctor.
#
#   ./setup.sh                 interactive
#   ./setup.sh --force         replace an existing .env (a backup .env.bak-<date> is kept, and the
#                              database password is carried over, because the database was created with it)
#   ./setup.sh --no-start      only write .env (and the nginx site, for the nginx choice)
#   ./setup.sh --dir PATH      work in PATH instead of this script's folder
#   ./setup.sh --non-interactive
#        reads the answers from environment variables instead of asking:
#        CHILLI_WEBSERVER (caddy | nginx | none), CHILLI_DOMAIN (e.g. chilli.example.com),
#        LLM_PROVIDER (anthropic | openai), LLM_MODEL, LLM_API_KEY, LLM_BASE_URL,
#        CONTENT_LANGUAGE (default en), OWNER_NAME (optional),
#        CHILLI_PORT (nginx and none only; host port of the api, default 8000).
#
# Nothing here needs root. Secrets are printed once, to this terminal, at the end; they are not
# written anywhere except .env (mode 600).
# Works with bash 3.2 (macOS) and bash 5 (Linux): no bash-4 features, no `sed -i`.

set -euo pipefail

FORCE=0
START=1
INTERACTIVE=1
DIR="$(cd "$(dirname "$0")" && pwd)"

while [ $# -gt 0 ]; do
    case "$1" in
        --force) FORCE=1 ;;
        --no-start) START=0 ;;
        --non-interactive) INTERACTIVE=0 ;;
        --dir) shift; DIR="$1" ;;
        -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
    shift
done

ENV_FILE="$DIR/.env"

fail() {
    echo "Error: $*" >&2
    exit 1
}

# --- checks before asking anything ----------------------------------------------------------

if [ "$START" -eq 1 ]; then
    command -v docker >/dev/null 2>&1 || fail "docker is not installed (https://docs.docker.com/engine/install/)"
    docker compose version >/dev/null 2>&1 || fail "the docker compose plugin is missing (https://docs.docker.com/compose/install/)"
fi

if [ -e "$ENV_FILE" ] && [ "$FORCE" -eq 0 ]; then
    fail "$ENV_FILE already exists. Edit it by hand, or run ./setup.sh --force to replace it (a backup is kept)."
fi

# --- helpers ------------------------------------------------------------------------------------

# A value goes into .env as KEY=value without quotes, read by two parsers (pydantic and Docker
# Compose's env_file). Characters they treat differently are refused instead of escaped.
check_value() {
    case "$2" in
        *[\"\'\#\$\`\\\ ]* ) fail "$1 must not contain spaces, quotes, #, \$, backslashes or backticks" ;;
    esac
    case "$2" in
        *"
"* ) fail "$1 must be a single line" ;;
    esac
}

# ask VAR "Question" "default" [required]
# Interactive: prompts, empty answer = default. Non-interactive: takes $VAR from the environment.
ask() {
    local var="$1" question="$2" default="$3" required="${4:-}" answer=""
    if [ "$INTERACTIVE" -eq 1 ]; then
        if [ -n "$default" ]; then
            printf '%s [%s]: ' "$question" "$default"
        else
            printf '%s: ' "$question"
        fi
        read -r answer || answer=""
    else
        answer="${!var:-}"
    fi
    answer="${answer:-$default}"
    if [ -n "$required" ] && [ -z "$answer" ]; then
        fail "$var is required$( [ "$INTERACTIVE" -eq 0 ] && echo " (set it in the environment for --non-interactive)")"
    fi
    check_value "$var" "$answer"
    printf -v "$var" '%s' "$answer"
}

# Like ask, but the typed answer is not shown (API keys).
ask_secret() {
    local var="$1" question="$2" required="${3:-}" answer=""
    if [ "$INTERACTIVE" -eq 1 ]; then
        printf '%s: ' "$question"
        read -r -s answer || answer=""
        echo
    else
        answer="${!var:-}"
    fi
    if [ -n "$required" ] && [ -z "$answer" ]; then
        fail "$var is required"
    fi
    check_value "$var" "$answer"
    printf -v "$var" '%s' "$answer"
}

lower() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

new_secret() {
    openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))'
}

# The value of KEY in the existing .env, without loading the rest of the file into the shell.
old_value() {
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

# --- questions ----------------------------------------------------------------------------------

echo "Chilli setup. Press Enter to accept the value in [brackets]."
echo

ask CHILLI_WEBSERVER "Web server: caddy (automatic HTTPS, needs free ports 80/443), nginx (already on this server), none (local only)" "caddy"
CHILLI_WEBSERVER="$(lower "$CHILLI_WEBSERVER")"
case "$CHILLI_WEBSERVER" in
    caddy|nginx|none) ;;
    *) fail "CHILLI_WEBSERVER must be caddy, nginx or none" ;;
esac

if [ "$CHILLI_WEBSERVER" = "none" ]; then
    ask CHILLI_DOMAIN "Domain (optional for local use)" ""
else
    ask CHILLI_DOMAIN "Domain for Chilli, e.g. chilli.example.com (its DNS A record must point here)" "" required
fi
CHILLI_DOMAIN="$(lower "$CHILLI_DOMAIN")"
case "$CHILLI_DOMAIN" in
    *[!a-z0-9.-]*) fail "CHILLI_DOMAIN must be a bare host name like chilli.example.com (no https://, no path)" ;;
esac
PUBLIC_URL=""
[ -n "$CHILLI_DOMAIN" ] && PUBLIC_URL="https://$CHILLI_DOMAIN"

# Host port of the api (127.0.0.1 only). Matters for nginx and local use; a second Chilli on the same
# server needs its own. Caddy reaches the api inside the compose network, so it is not asked there.
if [ "$CHILLI_WEBSERVER" = "caddy" ]; then
    CHILLI_PORT=8000
else
    ask CHILLI_PORT "Local port for the api (another Chilli on this server needs a different one)" "8000"
    case "$CHILLI_PORT" in
        ''|*[!0-9]*) fail "CHILLI_PORT must be a number between 1024 and 65535" ;;
    esac
    if [ "$CHILLI_PORT" -lt 1024 ] || [ "$CHILLI_PORT" -gt 65535 ]; then
        fail "CHILLI_PORT must be a number between 1024 and 65535"
    fi
fi

ask LLM_PROVIDER "Model provider: anthropic (Claude) or openai (OpenAI, OpenRouter, Gemini, Ollama, LM Studio...)" "anthropic"
LLM_PROVIDER="$(lower "$LLM_PROVIDER")"
case "$LLM_PROVIDER" in
    anthropic)
        ask LLM_MODEL "Model (empty = claude-sonnet-5-5)" ""
        LLM_BASE_URL=""
        ask_secret LLM_API_KEY "Anthropic API key" required
        ;;
    openai)
        ask LLM_BASE_URL "Server address (empty = OpenAI; e.g. https://openrouter.ai/api/v1 or http://host.docker.internal:11434/v1 for Ollama)" ""
        ask LLM_MODEL "Model that can read images, e.g. gpt-4.1-mini or qwen2.5vl:7b" "" required
        ask_secret LLM_API_KEY "API key (empty for a local server without keys)"
        ;;
    *) fail "LLM_PROVIDER must be anthropic or openai" ;;
esac

ask CONTENT_LANGUAGE "Language of titles and summaries (ISO code: en, pl, de...)" "en"
ask OWNER_NAME "Your name, as the AI should call you (optional)" ""

# --- secrets ------------------------------------------------------------------------------------

POSTGRES_PASSWORD=""
if [ -e "$ENV_FILE" ]; then
    # --force: the database volume was created with the old password; a new one would lock the api out.
    POSTGRES_PASSWORD="$(old_value POSTGRES_PASSWORD)"
    BACKUP="$ENV_FILE.bak-$(date +%Y-%m-%d-%H%M%S)"
    cp -p "$ENV_FILE" "$BACKUP"
    chmod 600 "$BACKUP"
    echo "Existing .env backed up to $BACKUP"
fi
[ -n "$POSTGRES_PASSWORD" ] || POSTGRES_PASSWORD="$(new_secret)"
CAPTURE_TOKEN="$(new_secret)"
MCP_SECRET="$(new_secret)"

# --- .env -----------------------------------------------------------------------------------

umask 077
TMP_ENV="$ENV_FILE.tmp.$$"
{
    echo "# Written by setup.sh on $(date +%Y-%m-%d). Never commit this file."
    echo "ENV=production"
    echo "PUBLIC_URL=$PUBLIC_URL"
    echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
    echo "CAPTURE_TOKEN=$CAPTURE_TOKEN"
    echo "MCP_SECRET=$MCP_SECRET"
    echo "MCP_SECRET_IN_URL=false"
    echo "LLM_PROVIDER=$LLM_PROVIDER"
    echo "LLM_MODEL=$LLM_MODEL"
    echo "LLM_VISION_MODEL="
    echo "LLM_API_KEY=$LLM_API_KEY"
    echo "LLM_BASE_URL=$LLM_BASE_URL"
    echo "CONTENT_LANGUAGE=$CONTENT_LANGUAGE"
    echo "OWNER_NAME=$OWNER_NAME"
    # Only when it differs from the default, so a plain install keeps the default compose setup.
    if [ "$CHILLI_PORT" != "8000" ]; then
        echo "CHILLI_PORT=$CHILLI_PORT"
    fi
    if [ "$CHILLI_WEBSERVER" = "caddy" ]; then
        echo "# Caddy (docker-compose.caddy.yml): a plain \`docker compose up -d\` includes it."
        echo "CHILLI_DOMAIN=$CHILLI_DOMAIN"
        echo "COMPOSE_FILE=docker-compose.yml:docker-compose.caddy.yml"
    fi
} > "$TMP_ENV"
chmod 600 "$TMP_ENV"
mv "$TMP_ENV" "$ENV_FILE"
echo "Wrote $ENV_FILE (readable only by you)."

# --- web server -----------------------------------------------------------------------------

if [ "$CHILLI_WEBSERVER" = "nginx" ]; then
    TEMPLATE="$DIR/deploy/nginx/chilli.conf.template"
    if [ -e "$TEMPLATE" ]; then
        # The domain (letters, digits, dots, hyphens) and the port (digits) are checked above, so sed
        # needs no escaping. sed instead of envsubst: it is always there, and it leaves nginx's own
        # $host and friends alone because it replaces only these two names.
        sed -e "s/\${CHILLI_DOMAIN}/$CHILLI_DOMAIN/g" -e "s/\${CHILLI_PORT}/$CHILLI_PORT/g" "$TEMPLATE" > "$DIR/chilli.conf"
        # The site file is named after the domain, so a second Chilli on this server gets its own.
        SITE="/etc/nginx/sites-available/$CHILLI_DOMAIN"
        echo
        echo "nginx site written to $DIR/chilli.conf. To enable it (as root):"
        echo "  sudo cp $DIR/chilli.conf $SITE"
        echo "  sudo ln -s $SITE /etc/nginx/sites-enabled/$CHILLI_DOMAIN"
        echo "  sudo nginx -t && sudo systemctl reload nginx"
        echo "  sudo certbot --nginx -d $CHILLI_DOMAIN"
    else
        echo "Note: $TEMPLATE not found, nginx site not written."
    fi
fi

# --- start ----------------------------------------------------------------------------------

if [ "$START" -eq 1 ]; then
    cd "$DIR"
    echo
    echo "Starting the containers (the first build downloads the embedding model, a few minutes)..."
    if [ "$CHILLI_WEBSERVER" = "caddy" ]; then
        docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
    else
        docker compose up -d --build
    fi
    # Wait until the service answers inside its container (port 8000 there, whatever CHILLI_PORT is).
    # Only startup is worth waiting for; a problem the doctor finds (e.g. a wrong API key) is not.
    echo
    echo "Waiting for the service to start..."
    ready=0
    for attempt in $(seq 1 30); do
        if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 2
    done
    if [ "$ready" -eq 0 ]; then
        echo "The service did not answer within a minute. See what happened with: docker compose logs --tail 50 api"
    else
        echo "Checking the installation..."
        if ! docker compose exec -T api python -m app.doctor; then
            echo "The doctor found problems (see above). Fix them in .env, then run:"
            echo "  docker compose up -d && docker compose exec api python -m app.doctor"
        fi
    fi
fi

# --- what next -------------------------------------------------------------------------------

BASE="${PUBLIC_URL:-http://localhost:$CHILLI_PORT}"
echo
echo "Done. Keep these values; they are shown only now (and stored in .env):"
echo
echo "  Capture URL (phone shortcuts, browser extension): $BASE/capture"
echo "  Capture token (header Authorization: Bearer ...): $CAPTURE_TOKEN"
echo
echo "  MCP server URL (Claude, ChatGPT, Cursor...): $BASE/mcp"
echo "  MCP header: Authorization: Bearer $MCP_SECRET"
echo "  In claude.ai: Settings > Connectors > Add custom connector, the URL above, authentication \"No sign-in\","
echo "  and the header above as a custom header (with OAuth chosen, Authorization is reserved)."
echo
echo "Next: shortcuts/README.md for the phone (iPhone or Android), extension/ for the browser."
if [ "$LLM_PROVIDER" = "openai" ] && [ "${LLM_BASE_URL#*host.docker.internal}" != "$LLM_BASE_URL" ]; then
    echo "Note: on Linux, host.docker.internal needs extra_hosts on the api service (docs/dev/17-llm-provider.md)."
fi
