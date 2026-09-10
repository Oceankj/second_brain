import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.server.application import ApplicationContext


class FakeRepository:
    def __init__(self) -> None:
        self.open_calls = []
        self.close_calls = 0

    async def open_pool(
        self,
        *,
        min_size: int,
        max_size: int,
        timeout_seconds: float,
    ) -> None:
        self.open_calls.append(
            {
                "min_size": min_size,
                "max_size": max_size,
                "timeout_seconds": timeout_seconds,
            }
        )

    async def close_pool(self) -> None:
        self.close_calls += 1


@pytest.mark.anyio
async def test_application_context_manages_repository_pool() -> None:
    context = ApplicationContext(
        Settings(
            database_url="postgresql://example",
            database_pool_min_size=2,
            database_pool_max_size=8,
            database_pool_timeout_seconds=12,
        )
    )
    fake_repository = FakeRepository()
    context._repository = fake_repository

    await context.startup()
    await context.startup()
    await context.shutdown()

    assert fake_repository.open_calls == [
        {
            "min_size": 2,
            "max_size": 8,
            "timeout_seconds": 12,
        }
    ]
    assert fake_repository.close_calls == 1
