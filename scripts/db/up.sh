#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/compose_env.sh"

require_docker_compose
warn_if_database_url_differs_from_compose

docker_compose up -d db

attempt=1
while [ "$attempt" -le 30 ]; do
  if docker_compose exec -T db pg_isready -U "$LOCAL_POSTGRES_USER" -d "$LOCAL_POSTGRES_DB" >/dev/null 2>&1; then
    echo "PostgreSQL is ready."
    exit 0
  fi

  echo "Waiting for PostgreSQL... ($attempt/30)"
  attempt=$((attempt + 1))
  sleep 1
done

echo "PostgreSQL did not become ready in time." >&2
exit 1
