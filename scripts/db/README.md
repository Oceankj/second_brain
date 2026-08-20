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
POSTGRES_DB=personal_agent_memory
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_PORT=5432
OLLAMA_PORT=11434
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/personal_agent_memory
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
MEMORY_EMBEDDING_DIMENSION=1024
```

`DATABASE_URL` is the database used by the MCP server. `POSTGRES_*` variables
configure the local Compose database.

`OLLAMA_*` variables configure the local Compose Ollama service and runtime
embedding provider.

## Commands

Start PostgreSQL:

```bash
scripts/db/up.sh
```

Apply SQL migrations:

```bash
scripts/db/migrate.sh
```

`scripts/db/migrate.sh` passes `MEMORY_EMBEDDING_DIMENSION` into psql as the
`embedding_dimension` variable. This controls the `memory_chunks.embedding`
dimension for fresh table creation.

You can confirm which value reached the migration by checking the migration
output:

```bash
MEMORY_EMBEDDING_DIMENSION=777 scripts/db/migrate.sh
```

The migration should print:

```text
Using embedding_dimension=777
```

Without the override, it should print the value from `.env`, or `1024` when the
variable is absent.

Use `scripts/db/doctor.sh` to compare that configured value with the actual
database column type.

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
