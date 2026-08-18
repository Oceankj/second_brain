import asyncio
import math

from personal_agent_memory.providers.embeddings import HashEmbeddingProvider, to_pgvector


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(dimension=16)

    first = asyncio.run(provider.embed_text("personal memory mcp"))
    second = asyncio.run(provider.embed_text("personal memory mcp"))

    assert first == second
    assert len(first) == 16
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_to_pgvector_formats_vector_literal() -> None:
    assert to_pgvector([0.1, -0.2]) == "[0.10000000,-0.20000000]"
