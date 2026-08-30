from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.chunking import chunk_text
from personal_agent_memory.services.ingest_policy import evaluate_ingest_policy
from personal_agent_memory.tool_schemas import IngestReason, IngestTurnInput, MemoryItemType
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


@dataclass(frozen=True)
class ExtractedMemoryCandidate:
    item_type: MemoryItemType
    title: str
    body: str
    tags: list[str]
    reason: IngestReason
    evidence_source: str


@dataclass(frozen=True)
class LinkCreationResult:
    links: list[dict[str, Any]]
    events: list[dict[str, Any]]


EVIDENCE_SOURCE_BY_REASON: dict[IngestReason, str] = {
    "task_completed": "both",
    "explicit_memory_request": "both",
    "user_preference": "user_input",
    "stable_fact": "user_input",
    "personal_insight": "user_input",
    "decision": "both",
    "stable_artifact": "assistant_output",
    "manual_import": "metadata",
}


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
        policy_decision = evaluate_ingest_policy(payload.metadata)
        if not policy_decision.should_ingest:
            return {
                "status": "skipped",
                "skip_reason": policy_decision.reason,
                "candidate_items": [],
                "tags": [],
                "links": [],
                "events": [],
            }

        candidate_items = []
        all_tags = []
        all_links = []
        all_events = []

        for candidate in extract_memory_candidates(payload):
            item = await self.repository.memory_items.create(
                item_type=candidate.item_type,
                ingest_reason=candidate.reason,
                title=candidate.title,
                body=candidate.body,
                status="candidate",
            )

            await self._create_chunks(item["id"], candidate.body)
            tags = await self._attach_tags(item["id"], candidate.tags)
            created_event = await self.repository.memory_item_events.create(
                memory_item_id=item["id"],
                event_type="created",
                source=payload.metadata.source,
                session_id=payload.metadata.session_id,
                metadata=created_event_metadata(payload, candidate),
            )
            link_result = await self._create_wikilinks(
                source_item_id=item["id"],
                body=candidate.body,
                payload=payload,
            )

            candidate_items.append(serialize_item(item, tags=tags))
            all_tags.extend(tags)
            all_links.extend(link_result.links)
            all_events.append(serialize_event(created_event))
            all_events.extend(link_result.events)

        return {
            "status": "accepted",
            "candidate_items": candidate_items,
            "tags": dedupe_serialized_by_id(all_tags),
            "links": all_links,
            "events": all_events,
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

    async def _create_wikilinks(
        self,
        *,
        source_item_id: str,
        body: str,
        payload: IngestTurnInput,
    ) -> LinkCreationResult:
        links = []
        events = []
        for target_title in detect_wikilinks(body):
            target = await self.repository.memory_items.find_by_title(target_title)
            if target and target["id"] != source_item_id:
                link = await self.repository.memory_links.create(
                    source_id=source_item_id,
                    target_id=target["id"],
                    link_type="references",
                )
                if link:
                    linked_event = await self.repository.memory_item_events.create(
                        memory_item_id=target["id"],
                        event_type="linked_from_new_note",
                        source=payload.metadata.source,
                        session_id=payload.metadata.session_id,
                        metadata=linked_event_metadata(
                            payload=payload,
                            link=link,
                            target_title=target_title,
                        ),
                    )
                    links.append(serialize_link(link))
                    events.append(serialize_event(linked_event))
        return LinkCreationResult(links=links, events=events)


def extract_memory_candidates(payload: IngestTurnInput) -> list[ExtractedMemoryCandidate]:
    reason = payload.metadata.ingest_reason
    if reason is None:
        return []

    return [
        ExtractedMemoryCandidate(
            item_type=memory_type_for_reason(reason),
            title=make_title(payload.user_input),
            body=build_turn_body(payload.user_input, payload.assistant_output),
            tags=normalize_tags(payload.metadata.tags),
            reason=reason,
            evidence_source=EVIDENCE_SOURCE_BY_REASON[reason],
        )
    ]


def memory_type_for_reason(reason: IngestReason) -> MemoryItemType:
    return "note"


def created_event_metadata(
    payload: IngestTurnInput,
    candidate: ExtractedMemoryCandidate,
) -> dict[str, Any]:
    metadata = payload.metadata.model_dump(mode="json")
    metadata["candidate"] = {
        "type": candidate.item_type,
        "reason": candidate.reason,
        "evidence_source": candidate.evidence_source,
    }
    return metadata


def linked_event_metadata(
    *,
    payload: IngestTurnInput,
    link: dict[str, Any],
    target_title: str,
) -> dict[str, Any]:
    metadata = payload.metadata.model_dump(mode="json")
    metadata["link"] = {
        "id": link["id"],
        "source_id": link["source_id"],
        "target_id": link["target_id"],
        "link_type": link["link_type"],
        "target_title": target_title,
    }
    return metadata


def dedupe_serialized_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for item in items:
        item_id = item["id"]
        if item_id not in seen:
            seen.add(item_id)
            deduped.append(item)
    return deduped
