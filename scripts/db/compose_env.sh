#!/usr/bin/env sh

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"

PRESERVED_ENV_VARS="
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_PORT
OLLAMA_PORT
OLLAMA_BASE_URL
OLLAMA_EMBEDDING_MODEL
MEMORY_EMBEDDING_DIMENSION
DATABASE_URL
"

for env_name in $PRESERVED_ENV_VARS; do
  eval "__had_$env_name=\${$env_name+x}"
  eval "__value_$env_name=\${$env_name-}"
done

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

for env_name in $PRESERVED_ENV_VARS; do
  eval "env_was_set=\${__had_$env_name-}"
  if [ -n "$env_was_set" ]; then
    eval "$env_name=\$__value_$env_name"
    export "$env_name"
  fi
done

POSTGRES_DB="${POSTGRES_DB:-personal_agent_memory}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:$OLLAMA_PORT}"
OLLAMA_EMBEDDING_MODEL="${OLLAMA_EMBEDDING_MODEL:-qwen3-embedding:0.6b}"
MEMORY_EMBEDDING_DIMENSION="${MEMORY_EMBEDDING_DIMENSION:-1024}"
COMPOSE_DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@localhost:$POSTGRES_PORT/$POSTGRES_DB"
DATABASE_URL="${DATABASE_URL:-$COMPOSE_DATABASE_URL}"

require_docker_compose() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker was not found. Install Docker first." >&2
    exit 127
  fi

  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose was not found. Install Docker Compose first." >&2
    exit 127
  fi
}

docker_compose() {
  if [ -f "$ROOT_DIR/.env" ]; then
    docker compose --env-file "$ROOT_DIR/.env" "$@"
  else
    docker compose "$@"
  fi
}

warn_if_database_url_differs_from_compose() {
  if [ "$DATABASE_URL" != "$COMPOSE_DATABASE_URL" ]; then
    echo "Warning: DATABASE_URL differs from the Compose database settings." >&2
    echo "  Compose database: $POSTGRES_USER@localhost:$POSTGRES_PORT/$POSTGRES_DB" >&2
    echo "  DATABASE_URL is set separately and may point somewhere else." >&2
    echo "The MCP runtime uses DATABASE_URL; Compose scripts use POSTGRES_* settings." >&2
  fi
}
