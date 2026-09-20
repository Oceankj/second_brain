"""PostgreSQL integration checks; all DDL/data are rolled back in an isolated schema.

Set MEMORY_TEST_DATABASE_URL explicitly to enable these tests.
"""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

MIGRATIONS = tuple(
    Path(__file__).resolve().parents[1] / "migrations" / name
    for name in ("003_oauth_storage.sql", "005_oauth_session_recovery.sql")
)
TABLES = {
    "oauth_clients", "oauth_login_sessions", "oauth_authorization_requests",
    "oauth_authorization_codes", "oauth_token_families", "oauth_refresh_tokens",
    "oauth_access_tokens",
}


@pytest.fixture
def db():
    dsn = os.environ.get("MEMORY_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("MEMORY_TEST_DATABASE_URL is not configured")
    conn = psycopg.connect(dsn, connect_timeout=15, prepare_threshold=None)
    try:
        schema = "test_oauth_" + uuid4().hex
        conn.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("set local search_path to {}").format(sql.Identifier(schema)))
        conn.execute("create table users (id text primary key)")
        conn.execute("insert into users values ('test-user')")
        for path in MIGRATIONS:
            migration = path.read_text().strip().removeprefix("begin;").removesuffix("commit;")
            conn.execute(migration)
            conn.execute(migration)  # Existing schema can be migrated again safely.
        yield conn
    finally:
        conn.rollback()
        conn.close()


def seed(db):
    db.execute("""insert into oauth_clients (client_id, redirect_uris)
        values ('test-client', array['https://example.com/callback'])""")
    db.execute("""insert into oauth_login_sessions
        (session_hash, expires_at)
        values (%s, now() + interval '10 minutes')""", ("a" * 64,))
    db.execute("""insert into oauth_authorization_requests
        (request_hash, session_hash, client_id, redirect_uri, resource, scopes,
         state, code_challenge, expires_at)
        values (%s, %s, 'test-client', 'https://example.com/callback',
        'https://example.com/mcp', array['memory:read'], 'original-state', %s,
        now() + interval '5 minutes')""", ("c" * 64, "a" * 64, "A" * 43))
    db.execute("""insert into oauth_authorization_codes
        (code_hash, request_hash, client_id, user_id, redirect_uri, resource,
         scopes, code_challenge, expires_at)
        values (%s, %s, 'test-client', 'test-user', 'https://example.com/callback',
        'https://example.com/mcp', array['memory:read'], %s,
        now() + interval '5 minutes')""", ("d" * 64, "c" * 64, "A" * 43))
    return db.execute("""insert into oauth_token_families
        (client_id, user_id, resource, scopes, expires_at)
        values ('test-client', 'test-user', 'https://example.com/mcp',
        array['memory:read'], now() + interval '30 days') returning id""").fetchone()[0]


def test_metadata_and_server_only_access(db):
    rows = db.execute("""select relname, relrowsecurity from pg_class
        where relnamespace = current_schema()::regnamespace and relkind = 'r'
        and relname like 'oauth_%'""").fetchall()
    assert {row[0] for row in rows} == TABLES
    assert all(row[1] for row in rows)
    for role in ("anon", "authenticated"):
        if db.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
            for table in TABLES:
                assert not db.execute(
                    "select has_table_privilege(%s, %s, 'SELECT,INSERT,UPDATE,DELETE')",
                    (role, table),
                ).fetchone()[0]


def test_rotation_and_access_binding(db):
    family = seed(db)
    for token, parent in [("e" * 64, None), ("f" * 64, "e" * 64)]:
        db.execute("""insert into oauth_refresh_tokens
            (token_hash, family_id, parent_token_hash, expires_at)
            values (%s, %s, %s, now() + interval '30 days')""", (token, family, parent))
    db.execute("""insert into oauth_access_tokens
        (token_hash, family_id, client_id, user_id, resource, scopes, expires_at)
        values (%s, %s, 'test-client', 'test-user', 'https://example.com/mcp',
        array['memory:read'], now() + interval '1 hour')""", ("1" * 64, family))
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        db.execute("""insert into oauth_refresh_tokens
            (token_hash, family_id, parent_token_hash, expires_at)
            values (%s, %s, %s, now() + interval '1 day')""", ("2" * 64, family, "e" * 64))
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("update oauth_access_tokens set user_id = 'another-user'")
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("update oauth_refresh_tokens set family_id = %s", (uuid4(),))
    db.execute("update oauth_refresh_tokens set consumed_at = now() where token_hash = %s",
               ("e" * 64,))
    db.execute("update oauth_token_families set revoked_at = now() where id = %s", (family,))
    assert db.execute("select revoked_at is not null from oauth_token_families").fetchone()[0]


def test_bad_hash_pkce_expiry_and_duplicate_code(db):
    seed(db)
    for statement in [
        "update oauth_authorization_codes set code_hash = 'raw-secret'",
        "update oauth_authorization_codes set code_challenge_method = 'plain'",
        "update oauth_authorization_requests set code_challenge = 'too-short'",
        "update oauth_login_sessions set expires_at = created_at",
    ]:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(statement)
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        db.execute("""insert into oauth_authorization_codes
            select %s, request_hash, client_id, user_id, redirect_uri, resource, scopes,
            code_challenge, code_challenge_method, created_at, expires_at, consumed_at
            from oauth_authorization_codes""", ("9" * 64,))
