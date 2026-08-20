#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/../db/compose_env.sh"

require_docker_compose
warn_if_database_url_differs_from_compose

docker_compose up -d db ollama

attempt=1
while [ "$attempt" -le 30 ]; do
  if docker_compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    echo "PostgreSQL is ready."
    break
  fi

  echo "Waiting for PostgreSQL... ($attempt/30)"
  attempt=$((attempt + 1))
  sleep 1
done

if [ "$attempt" -gt 30 ]; then
  echo "PostgreSQL did not become ready in time." >&2
  exit 1
fi

attempt=1
while [ "$attempt" -le 30 ]; do
  if docker_compose exec -T ollama ollama list >/dev/null 2>&1; then
    echo "Ollama is ready."
    break
  fi

  echo "Waiting for Ollama... ($attempt/30)"
  attempt=$((attempt + 1))
  sleep 1
done

if [ "$attempt" -gt 30 ]; then
  echo "Ollama did not become ready in time." >&2
  exit 1
fi

docker_compose run --rm ollama-pull
echo "Ollama embedding model is ready: $OLLAMA_EMBEDDING_MODEL"
