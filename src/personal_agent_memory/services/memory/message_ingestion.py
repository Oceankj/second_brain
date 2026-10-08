from __future__ import annotations

import hashlib
import json
from datetime import UTC

from personal_agent_memory.contracts.memory import IngestMessagesData
from personal_agent_memory.services.memory.chunking import chunk_text
from personal_agent_memory.utils.serialization import serialize_item, serialize_link
from personal_agent_memory.utils.text_processing import make_title, normalize_tags


class MessageConflict(ValueError):
    pass


class InvalidMessageBatch(ValueError):
    pass


def fingerprint(message) -> str:
    data = message.model_dump(mode="json")
    data["timestamp"] = message.timestamp.astimezone(UTC).isoformat()
    data["tags"] = sorted(normalize_tags(message.tags))
    data["content_kinds"] = sorted(set(message.content_kinds))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


async def ingest_messages(service, payload: IngestMessagesData, *, user_id: str) -> dict:
    repo = service.repository
    # Provider work is prepared before the write transaction. Replays reuse stored rows.
    prepared = {}
    tag_vectors = {}
    for message in payload.messages:
        existing = await repo.memory_items.find_source(
            user_id=user_id,
            source=payload.source,
            session_id=payload.session_id,
            message_id=message.source_message_id,
        )
        if existing:
            if existing["ingest_fingerprint"] != fingerprint(message):
                raise MessageConflict("Source message already exists with different content")
            continue
        prepared[message.source_message_id] = [
            (chunk, await service.embedding_provider.embed_text(chunk.content))
            for chunk in chunk_text(
                message.body, service.max_chunk_chars, service.chunk_overlap_chars
            )
        ]
        for tag in normalize_tags(message.tags):
            if tag not in tag_vectors:
                tag_vectors[tag] = await service.embedding_provider.embed_text(tag)

    async with repo.transaction() as conn:
        # Serialize a conversation's imports and reply creation, including overlapping batches.
        await conn.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (json.dumps(["message_ingest", user_id, payload.source, payload.session_id]),),
        )
        items = {}
        new_ids = set()
        pending = {m.source_message_id: m for m in payload.messages}
        links = []
        # Topological import accepts either order in a batch; references outside it must exist.
        while pending:
            progressed = False
            for key, message in list(pending.items()):
                parent_key = message.reply_to_message_id
                if parent_key in pending:
                    continue
                parent = items.get(parent_key)
                if parent_key and parent is None:
                    parent = await repo.memory_items.find_source(
                        user_id=user_id,
                        source=payload.source,
                        session_id=payload.session_id,
                        message_id=parent_key,
                    )
                    if parent is None:
                        raise InvalidMessageBatch("Reply target is missing from this conversation")
                if (
                    parent
                    and parent.get("sequence") is not None
                    and message.sequence is not None
                    and message.sequence <= parent["sequence"]
                ):
                    raise InvalidMessageBatch("Reply sequence must follow its target")
                item = await repo.memory_items.find_source(
                    user_id=user_id,
                    source=payload.source,
                    session_id=payload.session_id,
                    message_id=key,
                )
                if item:
                    if item["ingest_fingerprint"] != fingerprint(message):
                        raise MessageConflict(
                            "Source message already exists with different content"
                        )
                else:
                    item = await repo.memory_items.create(
                        user_id=user_id,
                        item_type="note",
                        title=make_title(message.body),
                        body=message.body,
                        status="candidate",
                        ingest_reason=message.ingest_reason,
                        record_kind="source",
                        role=message.role,
                        source=payload.source,
                        session_id=payload.session_id,
                        source_message_id=key,
                        sequence=message.sequence,
                        source_timestamp=message.timestamp,
                        content_kinds=sorted(set(message.content_kinds)),
                        ingest_fingerprint=fingerprint(message),
                    )
                    new_ids.add(item["id"])
                    for chunk, embedding in prepared[key]:
                        await repo.memory_chunks.create(
                            memory_item_id=item["id"],
                            chunk_index=chunk.chunk_index,
                            content=chunk.content,
                            embedding=embedding,
                            token_count=chunk.token_count,
                        )
                    for name in normalize_tags(message.tags):
                        tag = await repo.tags.upsert(name, embedding=tag_vectors[name])
                        await repo.memory_item_tags.attach(item["id"], tag["id"])
                    await repo.memory_item_events.create(
                        memory_item_id=item["id"],
                        event_type="created",
                        source=payload.source,
                        session_id=payload.session_id,
                        metadata={
                            "timestamp": message.timestamp.isoformat(),
                            "source_message_id": key,
                            "role": message.role,
                        },
                    )
                if parent:
                    link = await repo.memory_links.create(
                        source_id=item["id"],
                        target_id=parent["id"],
                        link_type="replies_to",
                    )
                    if link:
                        links.append(serialize_link(link))
                items[key] = item
                del pending[key]
                progressed = True
            if not progressed:
                raise InvalidMessageBatch("Reply cycle in message batch")
        return {
            "status": "accepted",
            "created_count": len(new_ids),
            "candidate_items": [
                serialize_item(items[m.source_message_id]) for m in payload.messages
            ],
            "links": links,
        }
