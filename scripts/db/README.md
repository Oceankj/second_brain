# Local Database

Local development uses Docker Compose for PostgreSQL and pgvector. These
scripts are small wrappers around `docker compose`; they are not part of the
MCP runtime.

The application runtime only reads `DATABASE_URL` and connects to PostgreSQL.
Starting PostgreSQL and applying migrations are explicit dev/ops steps.

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
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/personal_agent_memory
```

`DATABASE_URL` is the database used by the MCP server. `POSTGRES_*` variables
configure the local Compose database.

## Commands

Start PostgreSQL:

```bash
scripts/db/up.sh
```

Apply SQL migrations:

```bash
scripts/db/migrate.sh
```

Inspect the Compose database:

```bash
scripts/db/doctor.sh
```

Stop PostgreSQL:

```bash
scripts/db/down.sh
```

## Existing PostgreSQL

If you already have a Docker PostgreSQL container or another managed local
PostgreSQL instance, you do not need this Compose service. Point
`DATABASE_URL` at your database and apply `migrations/*.sql` in filename order
with your normal migration workflow.

If an existing database already has memory tables and the schema differs from
`DB.md`, stop and decide whether to write a migration. Do not hide that decision
inside a bootstrap script.
