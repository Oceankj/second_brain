#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from psycopg.rows import dict_row

from personal_agent_memory.config import load_dotenv
from personal_agent_memory.providers.embeddings import OllamaEmbeddingProvider

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_LINK_TYPES = {"references"}
REQUIRED_TOOLS = {"ingest_turn", "get_context"}


async def main() -> int:
    load_dotenv(ROOT / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("FAIL: DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        return 2

    embedding_dimension = int(os.environ.get("MEMORY_EMBEDDING_DIMENSION", "1024"))
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
    ollama_timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "30"))

    try:
        await check_database(database_url, expected_embedding_dimension=embedding_dimension)
        await check_ollama_embedding(
            base_url=ollama_base_url,
            model=ollama_model,
            dimension=embedding_dimension,
            timeout_seconds=ollama_timeout,
        )
        await check_mcp_tool_calls()
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("OK: smoke test passed")
    return 0


async def check_ollama_embedding(
    *,
    base_url: str,
    model: str,
    dimension: int,
    timeout_seconds: float,
) -> None:
    provider = OllamaEmbeddingProvider(
        base_url=base_url,
        model=model,
        dimension=dimension,
        timeout_seconds=timeout_seconds,
    )
    await provider.embed_text("personal memory smoke test")
    print(f"OK: Ollama embedding model is ready: {model} ({dimension} dimensions)")


async def check_database(database_url: str, *, expected_embedding_dimension: int) -> None:
    async with await psycopg.AsyncConnection.connect(database_url, row_factory=dict_row) as conn:
        tables = await fetch_values(
            conn,
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public'
              and table_name in (
                'memory_items',
                'memory_chunks',
                'memory_links',
                'tags',
                'memory_item_tags',
                'memory_item_events'
              )
            """,
        )
        missing_tables = {
            "memory_items",
            "memory_chunks",
            "memory_links",
            "tags",
            "memory_item_tags",
            "memory_item_events",
        } - set(tables)
        if missing_tables:
            raise RuntimeError(f"Missing database tables: {sorted(missing_tables)}")

        link_types = set(
            await fetch_values(
                conn,
                """
                select enumlabel
                from pg_enum
                where enumtypid = 'memory_link_type'::regtype
                """,
            )
        )
        missing_link_types = REQUIRED_LINK_TYPES - link_types
        if missing_link_types:
            raise RuntimeError(f"Missing memory_link_type values: {sorted(missing_link_types)}")

        cursor = await conn.execute(
            """
            select format_type(a.atttypid, a.atttypmod) as embedding_type
            from pg_attribute a
            where a.attrelid = 'memory_chunks'::regclass
              and a.attname = 'embedding'
              and not a.attisdropped
            """
        )
        row = await cursor.fetchone()
        expected_embedding_type = f"vector({expected_embedding_dimension})"
        actual_embedding_type = row["embedding_type"] if row else None
        if actual_embedding_type != expected_embedding_type:
            raise RuntimeError(
                "memory_chunks.embedding dimension mismatch: "
                f"expected {expected_embedding_type}, got {actual_embedding_type}. "
                "Use a fresh database or add a migration before running the smoke test."
            )

    print("OK: database schema is ready")


async def fetch_values(conn: psycopg.AsyncConnection, query: str) -> list[str]:
    cursor = await conn.execute(query)
    rows = await cursor.fetchall()
    return [next(iter(row.values())) for row in rows]


async def check_mcp_tool_calls() -> None:
    env = os.environ.copy()
    python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") if not python_path else f"{ROOT / 'src'}:{python_path}"
    warning_filter = "ignore:Field 'lifespan' has an incomplete definition"
    existing_warnings = env.get("PYTHONWARNINGS")
    env["PYTHONWARNINGS"] = (
        warning_filter if not existing_warnings else f"{existing_warnings},{warning_filter}"
    )

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "personal_agent_memory.server"],
        env=env,
        cwd=str(ROOT),
    )

    error: RuntimeError | None = None
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            try:
                await session.initialize()

                tools_result = await session.list_tools()
                tool_names = {tool.name for tool in tools_result.tools}
                missing_tools = REQUIRED_TOOLS - tool_names
                if missing_tools:
                    raise RuntimeError(f"Missing MCP tools: {sorted(missing_tools)}")
                print(f"OK: MCP tools listed: {', '.join(sorted(REQUIRED_TOOLS))}")

                run_id = uuid4().hex[:12]
                ingest_result = await session.call_tool(
                    "ingest_turn",
                    arguments={
                        "user_input": f"Smoke test memory source {run_id}",
                        "assistant_output": (
                            "Smoke test assistant output for Personal Agent Memory MCP."
                        ),
                        "metadata": {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "source": "smoke_test",
                            "app": "scripts/smoke_test.py",
                            "user_id": "smoke-user",
                            "session_id": f"smoke-{run_id}",
                            "tags": ["smoke-test", "mcp"],
                        },
                    },
                )
                ingest_payload = parse_tool_payload(ingest_result)
                if ingest_payload.get("status") != "accepted":
                    raise RuntimeError(f"ingest_turn returned unexpected payload: {ingest_payload}")
                print("OK: MCP ingest_turn call accepted")

                context_result = await session.call_tool(
                    "get_context",
                    arguments={
                        "input": f"Find the smoke test memory source {run_id}",
                        "user_id": "smoke-user",
                        "session_id": f"smoke-{run_id}",
                        "limit": 5,
                        "include_links": True,
                        "include_chunks": True,
                    },
                )
                context_payload = parse_tool_payload(context_result)
                if not context_payload.get("items"):
                    raise RuntimeError(f"get_context returned no items: {context_payload}")
                print(f"OK: MCP get_context returned {len(context_payload['items'])} item(s)")
            except RuntimeError as exc:
                error = exc

    if error:
        raise error


def parse_tool_payload(result: object) -> dict[str, object]:
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool returned an error: {extract_tool_text(result)}")

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"MCP tool returned non-JSON text: {text}") from exc
        if isinstance(payload, dict):
            return payload

    raise RuntimeError(f"Could not parse MCP tool result payload: {result!r}")


def extract_tool_text(result: object) -> str:
    texts = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts) if texts else repr(result)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
