from typing import Any

from personal_agent_memory.repository.types import Connect


class ClientCapacityError(RuntimeError):
    pass


class OAuthClientsRepository:
    MAX_CLIENTS = 10000

    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def create(self, client: dict[str, Any]) -> dict[str, Any]:
        async with self._connect() as conn, conn.transaction():
            # Serialize admission across workers so concurrent registrations cannot
            # exceed the storage cap. This lock is held only for this transaction.
            await conn.execute("select pg_advisory_xact_lock(736249182)")
            await conn.execute(
                """delete from oauth_authorization_requests r
                where r.expires_at <= clock_timestamp()
                  and not exists (select 1 from oauth_authorization_codes a
                                  where a.request_hash = r.request_hash)"""
            )
            await conn.execute(
                """delete from oauth_clients c
                where c.created_at <= clock_timestamp() - interval '1 day'
                  and not exists (select 1 from oauth_authorization_requests r
                                  where r.client_id = c.client_id)
                  and not exists (select 1 from oauth_authorization_codes a
                                  where a.client_id = c.client_id)
                  and not exists (select 1 from oauth_token_families f
                                  where f.client_id = c.client_id)"""
            )
            cursor = await conn.execute("select count(*) as count from oauth_clients")
            if (await cursor.fetchone())['count'] >= self.MAX_CLIENTS:
                raise ClientCapacityError('OAuth client capacity reached')
            cursor = await conn.execute(
                """insert into oauth_clients
                (client_id, client_name, redirect_uris, grant_types, scopes)
                values (%s, %s, %s, %s, %s)
                returning client_id, created_at""",
                (client['client_id'], client.get('client_name'), client['redirect_uris'],
                 client['grant_types'], client['scope'].split()),
            )
            return dict(await cursor.fetchone())

    async def get(self, client_id: str) -> dict[str, Any] | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """select client_id, client_name, redirect_uris, grant_types, scopes,
                    token_endpoint_auth_method, created_at from oauth_clients c
                    where client_id = %s and revoked_at is null
                      and (created_at > clock_timestamp() - interval '1 day'
                           or exists (select 1 from oauth_authorization_codes a
                                      where a.client_id = c.client_id)
                           or exists (select 1 from oauth_token_families f
                                      where f.client_id = c.client_id))""", (client_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def allows_redirect(self, client_id: str, redirect_uri: str) -> bool:
        client = await self.get(client_id)
        return client is not None and redirect_uri in client['redirect_uris']
