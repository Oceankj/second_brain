#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/compose_env.sh"

require_docker_compose
warn_if_database_url_differs_from_compose

echo "Applying SQL migrations to compose database '$POSTGRES_DB'..."
for migration in "$ROOT_DIR"/migrations/*.sql; do
  echo "Applying $(basename "$migration")..."
  docker_compose exec -T db \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
    < "$migration"
done
