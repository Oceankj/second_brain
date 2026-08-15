#!/usr/bin/env sh

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

POSTGRES_DB="${POSTGRES_DB:-personal_agent_memory}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5433}"
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
