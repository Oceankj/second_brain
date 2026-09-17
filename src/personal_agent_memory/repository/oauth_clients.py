from typing import Any

from personal_agent_memory.repository.types import Connect


class OAuthClientsRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def create(self, client: dict[str, Any]) -> dict[str, Any]:
        async with self._connect() as conn:
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
                    token_endpoint_auth_method, created_at from oauth_clients
                    where client_id = %s and revoked_at is null""", (client_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def allows_redirect(self, client_id: str, redirect_uri: str) -> bool:
        client = await self.get(client_id)
        return client is not None and redirect_uri in client['redirect_uris']
