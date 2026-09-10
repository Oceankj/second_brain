#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/compose_env.sh"

require_docker_compose
warn_if_database_url_differs_from_compose

echo "Compose database: $LOCAL_POSTGRES_DB"
echo "Compose host: localhost:$LOCAL_POSTGRES_PORT"
echo
echo "Installed extensions:"
docker_compose exec -T db \
  psql -U "$LOCAL_POSTGRES_USER" -d "$LOCAL_POSTGRES_DB" -v ON_ERROR_STOP=1 -c "
  select extname, extversion
  from pg_extension
  where extname in ('pgcrypto', 'vector')
  order by extname;
"

echo
echo "Memory tables:"
docker_compose exec -T db \
  psql -U "$LOCAL_POSTGRES_USER" -d "$LOCAL_POSTGRES_DB" -v ON_ERROR_STOP=1 -c "
  select table_name
  from information_schema.tables
  where table_schema = 'public'
    and (table_name like 'memory_%' or table_name in ('tags', 'users'))
  order by table_name;
"

echo
echo "Embedding dimension setting:"
echo "embedding.dimension=$MEMORY_EMBEDDING_DIMENSION"

echo
echo "Memory columns:"
docker_compose exec -T db \
  psql -U "$LOCAL_POSTGRES_USER" -d "$LOCAL_POSTGRES_DB" -v ON_ERROR_STOP=1 -c "
  select table_name, column_name, data_type, udt_name, is_nullable
  from information_schema.columns
  where table_schema = 'public'
    and (table_name like 'memory_%' or table_name in ('tags', 'users'))
  order by table_name, ordinal_position;
"

echo
echo "Memory chunk embedding type:"
docker_compose exec -T db \
  psql -U "$LOCAL_POSTGRES_USER" -d "$LOCAL_POSTGRES_DB" -v ON_ERROR_STOP=1 -c "
  select format_type(a.atttypid, a.atttypmod) as embedding_type
  from pg_attribute a
  where a.attrelid = 'memory_chunks'::regclass
    and a.attname = 'embedding'
    and not a.attisdropped;
"
