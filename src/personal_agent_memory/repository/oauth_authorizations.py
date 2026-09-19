from typing import Any

from personal_agent_memory.repository.types import Connect


class OAuthAuthorizationsRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def create(self, pending: dict[str, Any], csrf_hash: str) -> None:
        async with self._connect() as conn, conn.transaction():
            await conn.execute(
                """insert into oauth_login_sessions
                (session_hash, csrf_token_hash, expires_at)
                values (%s, %s, clock_timestamp() + interval '10 minutes')""",
                (pending['session_hash'], csrf_hash),
            )
            await conn.execute(
                """insert into oauth_authorization_requests
                (request_hash, session_hash, client_id, redirect_uri, resource, scopes,
                 state, code_challenge, expires_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s,
                        clock_timestamp() + interval '10 minutes')""",
                tuple(pending[k] for k in (
                    'request_hash', 'session_hash', 'client_id', 'redirect_uri', 'resource',
                    'scopes', 'state', 'code_challenge',
                )),
            )

    async def get_pending(self, request_hash: str, session_hash: str) -> dict[str, Any] | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """select r.*, s.csrf_token_hash, c.client_name
                from oauth_authorization_requests r
                join oauth_login_sessions s on s.session_hash = r.session_hash
                join oauth_clients c on c.client_id = r.client_id
                where r.request_hash = %s and r.session_hash = %s
                  and r.consumed_at is null and r.expires_at > clock_timestamp()
                  and s.revoked_at is null and s.expires_at > clock_timestamp()
                  and c.revoked_at is null""", (request_hash, session_hash),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def finish(
        self, request_hash: str, session_hash: str, csrf_hash: str, *,
        user_id: str | None = None, password_hash: str | None = None,
        code_hash: str | None = None, new_session_hash: str | None = None,
        new_csrf_hash: str | None = None,
    ) -> dict[str, Any] | None:
        """Consume once; approval and code issuance commit together, or neither does."""
        async with self._connect() as conn, conn.transaction():
            cursor = await conn.execute(
                """select r.*, c.redirect_uris, c.scopes as client_scopes, c.grant_types
                from oauth_authorization_requests r
                join oauth_login_sessions s on s.session_hash = r.session_hash
                join oauth_clients c on c.client_id = r.client_id
                where r.request_hash = %s and r.session_hash = %s
                  and s.csrf_token_hash = %s
                  and r.consumed_at is null and r.expires_at > clock_timestamp()
                  and s.revoked_at is null and s.expires_at > clock_timestamp()
                  and c.revoked_at is null
                for update of r, s, c""", (request_hash, session_hash, csrf_hash),
            )
            row = await cursor.fetchone()
            if not row or row['redirect_uri'] not in row['redirect_uris']:
                return None
            if ('authorization_code' not in row['grant_types']
                    or not set(row['scopes']).issubset(row['client_scopes'])):
                return None
            if user_id is not None:
                cursor = await conn.execute(
                    """select id from users where id = %s and is_active
                    and password_hash = %s for share""", (user_id, password_hash),
                )
                if await cursor.fetchone() is None:
                    return None
                await conn.execute(
                    """insert into oauth_login_sessions
                    (session_hash, csrf_token_hash, user_id, expires_at)
                    values (%s, %s, %s, clock_timestamp() + interval '10 minutes')""",
                    (new_session_hash, new_csrf_hash, user_id),
                )
                await conn.execute(
                    """insert into oauth_authorization_codes
                    (code_hash, request_hash, client_id, user_id, redirect_uri, resource,
                     scopes, code_challenge, expires_at)
                    values (%s, %s, %s, %s, %s, %s, %s, %s,
                            clock_timestamp() + interval '5 minutes')""",
                    (code_hash, request_hash, row['client_id'], user_id, row['redirect_uri'],
                     row['resource'], row['scopes'], row['code_challenge']),
                )
            await conn.execute(
                """update oauth_authorization_requests set consumed_at = clock_timestamp(),
                session_hash = coalesce(%s, session_hash) where request_hash = %s""",
                (new_session_hash, request_hash),
            )
            await conn.execute(
                "update oauth_login_sessions set revoked_at = clock_timestamp() "
                "where session_hash = %s", (session_hash,),
            )
            return dict(row)
