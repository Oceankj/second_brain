import hmac
from typing import Any

from personal_agent_memory.repository.types import Connect


class OAuthTokensRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def authenticate(self, token_hash: str, resource: str) -> dict[str, Any] | None:
        """Validate opaque access tokens against current database state, without caching."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                """select a.user_id, a.client_id, a.resource, a.scopes,
                          least(a.expires_at, f.expires_at) as expires_at
                from oauth_access_tokens a
                join oauth_token_families f on f.id = a.family_id
                join oauth_clients c on c.client_id = a.client_id
                join users u on u.id = a.user_id
                where a.token_hash = %s and a.resource = %s
                  and f.client_id = a.client_id and f.user_id = a.user_id
                  and f.resource = a.resource
                  and a.revoked_at is null and f.revoked_at is null
                  and c.revoked_at is null and u.is_active
                  and a.created_at <= clock_timestamp()
                  and f.created_at <= clock_timestamp()
                  and a.expires_at > clock_timestamp() and f.expires_at > clock_timestamp()
                  and a.scopes <@ f.scopes and a.scopes <@ c.scopes
                  and a.scopes <@ array['memory:read', 'memory:write']::text[]""",
                (token_hash, resource),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def exchange_authorization_code(
        self,
        *,
        code_hash: str,
        client_id: str,
        redirect_uri: str,
        resource: str,
        code_challenge: str,
        access_token_hash: str,
        refresh_token_hash: str,
    ) -> dict[str, Any] | None:
        """Consume one code and create its token family atomically."""
        async with self._connect() as conn, conn.transaction():
            cursor = await conn.execute(
                """select a.*, c.grant_types, c.scopes as client_scopes,
                          c.revoked_at as client_revoked_at, u.is_active
                from oauth_authorization_codes a
                join oauth_clients c on c.client_id = a.client_id
                join users u on u.id = a.user_id
                where a.code_hash = %s
                for update of a, c, u""",
                (code_hash,),
            )
            row = await cursor.fetchone()
            if (
                not row
                or row["consumed_at"] is not None
                or row["expires_at"] <= row["created_at"]
                or row["client_revoked_at"] is not None
                or not row["is_active"]
                or "authorization_code" not in row["grant_types"]
                or row["client_id"] != client_id
                or row["redirect_uri"] != redirect_uri
                or row["resource"] != resource
                or row["code_challenge_method"] != "S256"
                or not hmac.compare_digest(row["code_challenge"], code_challenge)
                or not set(row["scopes"]).issubset(row["client_scopes"])
                or not set(row["scopes"]).issubset({"memory:read", "memory:write"})
            ):
                return None
            # Compare against the database clock while holding the row lock.
            cursor = await conn.execute(
                "select expires_at > clock_timestamp() as valid "
                "from oauth_authorization_codes where code_hash = %s",
                (code_hash,),
            )
            if not (await cursor.fetchone())["valid"]:
                return None
            cursor = await conn.execute(
                """insert into oauth_token_families
                (client_id, user_id, resource, scopes, expires_at)
                values (%s, %s, %s, %s, clock_timestamp() + interval '30 days')
                returning id, expires_at""",
                (client_id, row["user_id"], resource, row["scopes"]),
            )
            family = await cursor.fetchone()
            cursor = await conn.execute(
                """insert into oauth_access_tokens
                (token_hash, family_id, client_id, user_id, resource, scopes, expires_at)
                values (%s, %s, %s, %s, %s, %s,
                        least(clock_timestamp() + interval '1 hour', %s))
                returning expires_at""",
                (
                    access_token_hash,
                    family["id"],
                    client_id,
                    row["user_id"],
                    resource,
                    row["scopes"],
                    family["expires_at"],
                ),
            )
            access = await cursor.fetchone()
            refresh_token_issued = "refresh_token" in row["grant_types"]
            if refresh_token_issued:
                await conn.execute(
                    """insert into oauth_refresh_tokens
                    (token_hash, family_id, expires_at) values (%s, %s, %s)""",
                    (refresh_token_hash, family["id"], family["expires_at"]),
                )
            await conn.execute(
                "update oauth_authorization_codes set consumed_at = clock_timestamp() "
                "where code_hash = %s",
                (code_hash,),
            )
            return {
                "client_id": client_id,
                "user_id": row["user_id"],
                "resource": resource,
                "scopes": row["scopes"],
                "expires_at": access["expires_at"],
                "refresh_token_issued": refresh_token_issued,
            }

    async def rotate_refresh_token(
        self,
        *,
        refresh_token_hash: str,
        client_id: str,
        resource: str,
        scopes: list[str] | None,
        access_token_hash: str,
        next_refresh_token_hash: str,
    ) -> dict[str, Any] | None:
        """Rotate once; replay of a consumed token revokes the entire family."""
        async with self._connect() as conn, conn.transaction():
            cursor = await conn.execute(
                """select r.*, f.client_id, f.user_id, f.resource, f.scopes as family_scopes,
                          f.expires_at as family_expires_at,
                          f.revoked_at as family_revoked_at,
                          c.grant_types, c.scopes as client_scopes,
                          c.revoked_at as client_revoked_at, u.is_active
                from oauth_refresh_tokens r
                join oauth_token_families f on f.id = r.family_id
                join oauth_clients c on c.client_id = f.client_id
                join users u on u.id = f.user_id
                where r.token_hash = %s
                for update of r, f, c, u""",
                (refresh_token_hash,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            if row["consumed_at"] is not None:
                await self._revoke_family(conn, row["family_id"])
                return {"replayed": True}
            selected_scopes = row["family_scopes"] if scopes is None else scopes
            cursor = await conn.execute(
                "select clock_timestamp() < %s and clock_timestamp() < %s as valid",
                (row["expires_at"], row["family_expires_at"]),
            )
            valid_time = (await cursor.fetchone())["valid"]
            if (
                row["revoked_at"] is not None
                or row["family_revoked_at"] is not None
                or row["client_revoked_at"] is not None
                or not row["is_active"]
                or not valid_time
                or "refresh_token" not in row["grant_types"]
                or row["client_id"] != client_id
                or row["resource"] != resource
            ):
                return None
            if (
                not set(selected_scopes).issubset(row["family_scopes"])
                or not set(selected_scopes).issubset(row["client_scopes"])
                or not set(selected_scopes).issubset({"memory:read", "memory:write"})
            ):
                return {"invalid_scope": True}
            await conn.execute(
                "update oauth_refresh_tokens set consumed_at = clock_timestamp() "
                "where token_hash = %s",
                (refresh_token_hash,),
            )
            await conn.execute(
                """insert into oauth_refresh_tokens
                (token_hash, family_id, parent_token_hash, expires_at)
                values (%s, %s, %s, %s)""",
                (
                    next_refresh_token_hash,
                    row["family_id"],
                    refresh_token_hash,
                    row["family_expires_at"],
                ),
            )
            cursor = await conn.execute(
                """insert into oauth_access_tokens
                (token_hash, family_id, client_id, user_id, resource, scopes, expires_at)
                values (%s, %s, %s, %s, %s, %s,
                        least(clock_timestamp() + interval '1 hour', %s))
                returning expires_at""",
                (
                    access_token_hash,
                    row["family_id"],
                    client_id,
                    row["user_id"],
                    resource,
                    selected_scopes,
                    row["family_expires_at"],
                ),
            )
            access = await cursor.fetchone()
            return {
                "client_id": client_id,
                "user_id": row["user_id"],
                "resource": resource,
                "scopes": selected_scopes,
                "expires_at": access["expires_at"],
                "refresh_token_issued": True,
            }

    @staticmethod
    async def _revoke_family(conn: Any, family_id: Any) -> None:
        await conn.execute(
            "update oauth_token_families set revoked_at = coalesce(revoked_at, clock_timestamp()) "
            "where id = %s",
            (family_id,),
        )
        await conn.execute(
            "update oauth_refresh_tokens set revoked_at = coalesce(revoked_at, clock_timestamp()) "
            "where family_id = %s",
            (family_id,),
        )
        await conn.execute(
            "update oauth_access_tokens set revoked_at = coalesce(revoked_at, clock_timestamp()) "
            "where family_id = %s",
            (family_id,),
        )
