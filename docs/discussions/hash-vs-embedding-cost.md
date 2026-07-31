# Hash vs Embedding 成本比較

這篇筆記記錄為什麼 chunk-level content hash 對 personal agent memory system 有價值。

## 核心想法

Hashing 和 embedding 回答的是不同問題。

```text
content hash:
  這個 chunk 的文字是否完全沒變？

embedding:
  這個 chunk 表達的是什麼語意？
```

不應該用 embedding 來判斷內容有沒有改變。因為如果要比較 embedding，系統必須先替新的內容產生新的 embedding；這代表在決定是否需要重算之前，就已經付出最貴的成本了。

## 成本差異

Hashing 很便宜：

```text
chunk text -> local hash function -> content_hash
```

它在本機執行，不需要 model call，沒有 API 成本。對許多 chunks 來說，通常是毫秒到幾十毫秒等級。

Embedding 貴很多：

```text
chunk text -> embedding model -> vector
```

它需要模型推論，通常需要 API call 或 GPU compute，會有 latency，而且如果使用 hosted API，通常會依 token 計費。

假設有一批 notes 被切成：

```text
1,000 個 chunks
每個 chunk 約 500 tokens
總共 500,000 tokens
```

如果全部重新 embedding，粗估成本是：

```text
text-embedding-3-small: 500,000 tokens * $0.02 / 1M tokens = 約 $0.01
text-embedding-3-large: 500,000 tokens * $0.13 / 1M tokens = 約 $0.065
hashing: $0
```

目前參考價格：

- [text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small)
- [text-embedding-3-large](https://developers.openai.com/api/docs/models/text-embedding-3-large)

單次更新看起來金額不大，但如果 notes 會不斷更新，累積起來就有差。更大的價值是減少不必要的 latency 與 model calls。

## 更新流程

有 chunk-level content hash 之後：

```text
new note body
  -> semantic chunking
  -> compute content_hash for each chunk
  -> compare against existing chunk hashes
  -> reuse embedding for unchanged chunks
  -> generate embeddings only for changed chunks
```

如果一次更新只有 5% 的 chunks 改變：

```text
without hashes:
  re-embed 100% of chunks

with content_hash:
  hash 100% of chunks
  re-embed only 5% of chunks
```

套到 500,000 tokens 的例子：

```text
without hashes:
  embed 500,000 tokens

with content_hash and 5% changed chunks:
  hash all chunks locally
  embed 25,000 tokens
  save about 95% of embedding cost and latency
```

## 設計決策

第一版不需要完整 block server 或 Merkle tree。

P1 應該直接重用 `memory_chunks`：

```sql
memory_chunks
  content_hash
  chunker_version
  embedding_model
  embedding_version
```

未來如果大型 nested notes、structural diffs、local-first sync 或 version history 真的帶來壓力，再考慮完整 hash tree。
