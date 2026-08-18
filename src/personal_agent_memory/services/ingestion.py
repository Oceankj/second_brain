from __future__ import annotations

from typing import Any

from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.chunking import chunk_text
from personal_agent_memory.tool_schemas import IngestTurnInput
from personal_agent_memory.utils.serialization import (
    serialize_event,
    serialize_item,
    serialize_link,
    serialize_tag,
)
from personal_agent_memory.utils.text_processing import (
    build_turn_body,
    detect_wikilinks,
    make_title,
    normalize_tags,
)


class IngestionService:
    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        max_chunk_chars: int,
        chunk_overlap_chars: int,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.max_chunk_chars = max_chunk_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    async def ingest_turn(self, payload: IngestTurnInput) -> dict[str, Any]:
        body = build_turn_body(payload.user_input, payload.assistant_output)
        item = await self.repository.memory_items.create(
            item_type="note",
            title=make_title(payload.user_input),
            body=body,
            status="candidate",
        )

        await self._create_chunks(item["id"], body)
        tags = await self._attach_tags(item["id"], payload.metadata.tags)
        links = await self._create_wikilinks(item["id"], body)
        created_event = await self.repository.memory_item_events.create(
            memory_item_id=item["id"],
            event_type="created",
            source=payload.metadata.source,
            session_id=payload.metadata.session_id,
            metadata=payload.metadata.model_dump(mode="json"),
        )

        return {
            "status": "accepted",
            "candidate_items": [serialize_item(item, tags=tags)],
            "profile_memory_updates": [],
            "diary_material_enqueued": False,
            "tags": tags,
            "links": links,
            "events": [serialize_event(created_event)],
        }

    async def _create_chunks(self, memory_item_id: str, body: str) -> None:
        for chunk in chunk_text(body, self.max_chunk_chars, self.chunk_overlap_chars):
            embedding = await self.embedding_provider.embed_text(chunk.content)
            await self.repository.memory_chunks.create(
                memory_item_id=memory_item_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=embedding,
                token_count=chunk.token_count,
            )

    async def _attach_tags(self, memory_item_id: str, raw_tags: list[str]) -> list[dict[str, Any]]:
        tags = []
        for tag_name in normalize_tags(raw_tags):
            tag = await self.repository.tags.upsert(tag_name)
            await self.repository.memory_item_tags.attach(memory_item_id, tag["id"])
            tags.append(serialize_tag(tag))
        return tags

    async def _create_wikilinks(self, memory_item_id: str, body: str) -> list[dict[str, Any]]:
        links = []
        for target_title in detect_wikilinks(body):
            target = await self.repository.memory_items.find_by_title(target_title)
            if target and target["id"] != memory_item_id:
                link = await self.repository.memory_links.create(
                    source_id=memory_item_id,
                    target_id=target["id"],
                    link_type="references",
                )
                if link:
                    links.append(serialize_link(link))
        return links
