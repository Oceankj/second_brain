#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/compose_env.sh"

require_docker_compose
warn_if_database_url_differs_from_compose

echo "Applying P0 SQL migration to compose database '$POSTGRES_DB'..."
docker_compose exec -T db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
  < "$ROOT_DIR/migrations/001_p0_schema.sql"
