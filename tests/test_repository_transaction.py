from contextlib import asynccontextmanager

import pytest

from personal_agent_memory.repository import PostgresMemoryRepository


class Connection:
    def __init__(self):
        self.rows = []

    @asynccontextmanager
    async def transaction(self):
        before = list(self.rows)
        try:
            yield
        except Exception:
            self.rows[:] = before
            raise


class Pool:
    def __init__(self):
        self.connections = []

    @asynccontextmanager
    async def connection(self):
        conn = Connection()
        self.connections.append(conn)
        yield conn


@pytest.mark.anyio
async def test_repository_transaction_shares_connection_and_resets_after_rollback():
    repository = PostgresMemoryRepository("unused")
    pool = Pool()
    repository._pool = pool
    with pytest.raises(RuntimeError, match="write failed"):
        async with repository.transaction() as transaction:
            async with repository.memory_items._connect() as items_connection:
                items_connection.rows.append("diary")
            async with repository.memory_chunks._connect() as chunks_connection:
                assert chunks_connection is transaction is items_connection
                raise RuntimeError("write failed")
    assert len(pool.connections) == 1
    assert transaction.rows == []
    async with repository._connect() as next_connection:
        assert next_connection is not transaction


@pytest.mark.anyio
async def test_independent_tasks_do_not_share_transactions():
    import asyncio

    repository = PostgresMemoryRepository("unused")
    pool = Pool()
    repository._pool = pool
    ready = asyncio.Event()
    count = 0

    async def writer():
        nonlocal count
        async with repository.transaction() as connection:
            count += 1
            if count == 2:
                ready.set()
            await ready.wait()
            async with repository.memory_items._connect() as nested:
                assert nested is connection
            return connection

    first, second = await asyncio.gather(writer(), writer())
    assert first is not second
