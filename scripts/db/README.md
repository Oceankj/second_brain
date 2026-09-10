# Local Database

Local development uses Docker Compose for PostgreSQL + pgvector and, through
the repo-level infra wrapper, Ollama. These scripts are small wrappers around
`docker compose`; they are not part of the MCP runtime.

The application runtime only reads `DATABASE_URL` and connects to PostgreSQL.
Starting local infra and applying migrations are explicit dev/ops steps.

## Environment

Start from the template:

```bash
cp .env.example .env
```

The scripts load `.env` from the repository root when it exists. The relevant
variables are:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/personal_agent_memory
LOCAL_POSTGRES_DB=personal_agent_memory
LOCAL_POSTGRES_USER=postgres
LOCAL_POSTGRES_PASSWORD=postgres
LOCAL_POSTGRES_PORT=5432
```

`DATABASE_URL` is the database used by the MCP server. It can point at local
Compose PostgreSQL, Supabase, or another PostgreSQL target.

`LOCAL_POSTGRES_*` variables configure only the local Compose database.

Runtime embedding behavior is configured in `memory.json`, not `.env`.
`embedding.provider` selects `ollama` or `cloudflare`, and
`embedding.dimension` controls the pgvector column dimension for fresh database
creation.

## Commands

Start PostgreSQL:

```bash
scripts/db/up.sh
```

Apply SQL migrations:

```bash
scripts/db/migrate.sh
```

`scripts/db/migrate.sh` applies migrations to the local Compose database.

Apply SQL migrations to the database pointed at by `DATABASE_URL`, such as
Supabase:

```bash
scripts/db/migrate_url.sh
```

Supabase migration was verified on 2026-09-03 with an embedding dimension of
1024. The runner connected to the Supabase
`postgres` database and applied `migrations/001_p0_schema.sql` successfully.

`DATABASE_URL` must be a PostgreSQL connection string that starts with
`postgresql://` or `postgres://`. Supabase project API URLs that start with
`https://` are not database connection strings and cannot be used for
migrations.

Both migration commands pass `memory.json`'s `embedding.dimension` into the
migration as the `embedding_dimension` value. This controls the
`memory_chunks.embedding` dimension for fresh table creation.

You can confirm which value reached the migration by checking the migration
output:

```bash
scripts/db/migrate.sh
```

The migration should print:

```text
Using embedding_dimension=1024
```

If `memory.json` has no `embedding.dimension`, the scripts fall back to legacy
`MEMORY_EMBEDDING_DIMENSION`, or `1024` when that variable is absent.

Use `scripts/db/doctor.sh` to compare that configured value with the actual
database column type.

Inspect the database pointed at by `DATABASE_URL`, such as Supabase:

```bash
scripts/db/doctor_url.sh
```

Supabase doctor checks were verified on 2026-09-03. The script confirmed
`pgcrypto`, `vector`, the memory tables, memory enum types, required indexes,
and `vector(1024)` embedding columns on `memory_chunks.embedding` and
`tags.embedding`.

Re-running migrations does not change the dimension of an existing
`memory_chunks.embedding` column. Changing embedding models across dimensions
requires a fresh database or a dedicated migration plus re-embedding existing
chunks.

Inspect the Compose database:

```bash
scripts/db/doctor.sh
```

Stop PostgreSQL:

```bash
scripts/db/down.sh
```

Start all local infra:

```bash
scripts/infra/up.sh
```

Stop all local infra:

```bash
scripts/infra/down.sh
```

## Existing PostgreSQL

If you already have a Docker PostgreSQL container or another managed local
PostgreSQL instance, you do not need this Compose service. Point
`DATABASE_URL` at your database and apply `migrations/*.sql` in filename order
with your normal migration workflow.

If an existing database already has memory tables and the schema differs from
`DB.md`, stop and decide whether to write a migration. Do not hide that decision
inside a bootstrap script.
