# TODO

這裡記錄刻意不放進 P0 的想法。P0 應該專注在核心 memory schema、基本 ingestion、chunking、embedding、links、tags 與 retrieval。

## P1

P1 是 P0 跑通之後要優先處理的項目。它們會直接改善 retrieval 品質、embedding 成本、memory 維護效率，或日常使用體驗。

### Embedding 策略優化

- 加入 content-addressed semantic chunks，讓 note 更新後，沒有改變的 chunks 可以沿用既有 embeddings。參考：[Hash vs Embedding 成本比較](docs/discussions/hash-vs-embedding-cost.md)。
- 在 `memory_chunks` 加上 `content_hash`、`chunker_version`、`embedding_model`、`embedding_version`。
- note 更新時，重新切 chunks，計算每個 chunk 的 hash，只針對 hash 改變的 chunks 重新 embedding。
- 這是 embedding / retrieval 的優化，不是 storage 或 sync 系統。
- 這個優化直接以 semantic chunks 為基礎。除非之後真的需要 nested structural diff，否則不需要完整 hash tree。

### Retrieval 品質

- 結合 pgvector semantic search 與 PostgreSQL full-text search。
- 在 chunk retrieval 後加入 reranking。
- 在 context bundle 中回傳精選 backlinks 與 outgoing links。
- 對 diary entries 加入 recency weighting。
- 對 profile memory 加入 priority weighting。
- 等 ranking data 成熟後，把 `heat_score` 與 `importance_score` 納入 retrieval ranking 參考。

### Memory 維護

- 在 daily tasks 中整理與 normalize tags。
- 合併高度相似的 candidate notes。
- 拆分超過長度或複雜度上限的 notes。
- note merge / split 後修復 links。
- 根據當天 interactions 產生 daily diary。
- consolidation 後將 candidate notes 標記為 `active`。
- 封存過期或被取代的 notes。

### Schema 延伸

- 在 `memory_items` 加上 `summary`，用於快速預覽與 retrieval reranking。
- 等 provenance 或 source-specific 欄位具體化後，在 `memory_items` 加上 `metadata jsonb`。
- 加入 `memory_sources`，記錄 source app、conversation id、turn ids 與 raw evidence。
- 如果相似 tags 開始重複出現，加入獨立的 `tag_aliases` table。
- 如果 tag assignment 需要 ranking 或人工 review，在 `memory_item_tags` 加上 `confidence`。

## P2

P2 是有價值但不用急著做的項目。等 P1 之後真的遇到 scale、note growth、ranking 品質或 maintenance complexity 的壓力，再回來處理。

### 進階 Embedding / Chunking

- 只有在大型 nested notes 或 structural diff 讓單層 `content_hash` 不夠用時，才考慮完整 hash tree 或 Merkle-style 結構。
- notes 被 split、merge 或大幅 rewrite 時，追蹤 chunk lineage。
- 針對 diary、notes、profile memory 嘗試不同 chunking strategies。

### 進階 Links

- 在 `memory_links` 加上 `anchor_text` 與 `context`，支援精準 link preview 與 highlight references。
- 加入更多 `memory_link_type`，例如 `expands`、`contradicts`、`derived_from`、`same_topic`、`supersedes`。
- 把 typed links 用作 retrieval expansion control，而不只是可見 backlinks。

### Hot / Cold Memory Ranking

- 加入 `memory_item_stats` 或 `memory_item_rankings`，作為 hot/cold memory signals 的 derived rollup/cache。
- 保留 `type` 表示 memory kind：`note`、`diary`、`profile_memory`。
- hot/cold 應該是 operational ranking metadata，不是 note type。
- 使用 `memory_item_events` 作為未來 hot/cold scoring 的 source of truth。
- 分開 `heat_score` 與 `importance_score`。
- `heat_score` 表示近期活躍度，並且會隨時間 decay。
- `importance_score` 表示長期重要性、manual pinning 或高信心的系統判斷。
- 避免 rich-get-richer loop：不要讓 notes 只因為被 retrieval 回來就越來越 hot。
- `retrieved` 的權重應該低於更強的 signals，例如 `used_in_answer`、`linked_from_new_note`、`mentioned_in_diary`、`manually_pinned`。

範例：

```sql
create table memory_item_stats (
  memory_item_id uuid primary key references memory_items(id) on delete cascade,
  retrieval_count integer not null default 0,
  used_count integer not null default 0,
  linked_count integer not null default 0,
  last_retrieved_at timestamptz,
  last_used_at timestamptz,
  heat_score numeric not null default 0,
  importance_score numeric not null default 0,
  algorithm_version text not null default 'v0',
  calculated_at timestamptz not null default now(),
  features jsonb,
  updated_at timestamptz not null default now()
);
```

### 進階 Retrieval

- 回傳 memory context 時加入 source / provenance snippets。
- 設計 ranking formula，結合 semantic score、diary context boost、tag match boost、typed link boost、heat boost、importance boost 與 staleness penalty。
- 更新 memory heat：decay 舊的 `heat_score`、加入近期 usage signals、boost 被近期 diary 連到的 notes，並讓近期沒有使用的 notes cooling。

## 待重新討論的問題

- `create notes` 要每個 turn 執行，還是每段 conversation 結束後批次執行？
- note 長度上限要用 token count、character count，還是 semantic section count？
- `profile_memory` 更新前需要幾次重複 evidence？
- 哪些 tag operations 需要使用者確認？
- 是否需要 raw conversation logs，例如 `conversation_events`？
- 哪些 events 算 hot/cold signals？權重怎麼設？
- `importance_score` 可以自動判斷、人工 pin，還是兩者都要支援？
