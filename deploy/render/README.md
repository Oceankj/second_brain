# Render Docker Deployment

這份手冊描述第一版低成本部署方式：

```text
Render Free Web Service
+ Supabase Postgres
+ Cloudflare Workers AI / Cloudflare API
+ GitHub Actions scheduled call
```

## 1. 前置確認

確認 Supabase Postgres schema 健康：

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/db/doctor_url.py
```

如果還沒有套 migration，先跑：

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/db/migrate_url.py
```

確認 repo root 的 private `.env` 已經有 `MEMORY_DEFAULT_USER_TOKEN`：

```dotenv
MEMORY_DEFAULT_USER_TOKEN=replace-with-a-random-token-at-least-32-chars
```

如果 `.env` 還沒有 token，才產生一組新的：

```bash
openssl rand -hex 32
```

Render 和 GitHub Actions 要使用同一組 token；不要把 token 放進
`memory.json` 或 `deploy/render/memory.json`。

## 2. 確認 Render preset

Render 這個 deployment target 已經有一份 committed preset：
[memory.json](memory.json)。一般情況下你不需要另外建立 config 檔；Docker
build 會自動把這份檔案放到 container 內的 `/app/config/memory.json`。

這份檔案會進 image，但不放 secrets；secrets 仍然透過 Render environment
variables 提供。它也不是 repo root 的 private `/memory.json`。

唯一通常需要改的是 `YOUR_RENDER_SERVICE`。如果你已經決定 Render service
name，可以先把 [memory.json](memory.json) 裡的 hostname 換掉，例如：

```json
{
  "mcp_http": {
    "public_url": "https://personal-agent-memory.onrender.com",
    "allowed_hosts": ["personal-agent-memory.onrender.com"],
    "allowed_origins": ["https://personal-agent-memory.onrender.com"]
  }
}
```

Render 會用 `$PORT` 指定實際 listen port；runtime 會用 `$PORT` 覆蓋
`mcp_http.port`。`mcp_http.host` 在 container 裡要保持 `0.0.0.0`。

目前 config 分工是：

```text
memory.example.json          # general/local example
/memory.json                 # local private runtime config, gitignored
deploy/render/memory.json    # committed Render deployment preset
Render env vars              # DATABASE_URL, tokens, Cloudflare credentials
```

## 3. 本機 Docker 驗證

Build image：

```bash
docker build -t personal-agent-memory .
```

用本機 `.env` 和 repo root 的 private `/memory.json` 啟動：

```bash
docker run --rm \
  -p 8001:8001 \
  --env-file .env \
  -e PORT=8001 \
  -e MEMORY_REST_API_ENABLED=true \
  -e MEMORY_CONFIG_PATH=/app/config/memory.json \
  -v "$PWD/memory.json:/app/config/memory.json:ro" \
  personal-agent-memory
```

本機測試用的 `memory.json` 需要：

```json
{
  "mcp_http": {
    "host": "0.0.0.0",
    "port": 8001,
    "path": "/mcp",
    "public_url": "http://localhost:8001",
    "allowed_hosts": ["localhost:*", "127.0.0.1:*"],
    "allowed_origins": ["http://localhost:*", "http://127.0.0.1:*"]
  }
}
```

Health check：

```bash
curl http://localhost:8001/health
```

預期回傳：

```json
{"status":"ok"}
```

## 4. 建立 Render Web Service

在 Render 建立服務：

1. 選 `New` -> `Web Service`。
2. 連到 GitHub repository。
3. Render 偵測到 repo root 的 `Dockerfile` 後，使用 Docker deploy。
4. Plan 選 `Free`。
5. 設定環境變數。

必要環境變數：

```dotenv
DATABASE_URL=postgresql://...
MEMORY_DEFAULT_USER_TOKEN=<same-value-as-local-.env>
MEMORY_REST_API_ENABLED=true
MEMORY_CONFIG_PATH=/app/config/memory.json
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...
```

Render 會自動提供 `PORT`，不需要手動設定。

## 5. 部署後驗證

Health check：

```bash
curl https://YOUR_RENDER_SERVICE.onrender.com/health
```

Daily diary dry run：

```bash
curl -X POST https://YOUR_RENDER_SERVICE.onrender.com/maintenance/daily-diary \
  -H "Authorization: Bearer $MEMORY_DEFAULT_USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-09-09","dry_run":true}'
```

Remote MCP endpoint：

```text
https://YOUR_RENDER_SERVICE.onrender.com/mcp
```

Remote MCP 使用 `Authorization: Bearer <token>` transport auth，不需要把 token
放進 MCP tool arguments。

## 6. GitHub Actions 排程範例

在 GitHub repository secrets 設定：

```text
MEMORY_SERVER_URL=https://YOUR_RENDER_SERVICE.onrender.com
MEMORY_DEFAULT_USER_TOKEN=<same-token-as-render>
```

Workflow 範例：

```yaml
name: Daily Diary

on:
  schedule:
    - cron: "30 9 * * *"
  workflow_dispatch:

jobs:
  create-diary:
    runs-on: ubuntu-latest
    steps:
      - name: Warm up memory server
        run: |
          curl --fail-with-body "$MEMORY_SERVER_URL/health"
        env:
          MEMORY_SERVER_URL: ${{ secrets.MEMORY_SERVER_URL }}

      - name: Create daily diary
        run: |
          DATE="$(date -u -d 'yesterday' +%F)"
          curl --fail-with-body -X POST "$MEMORY_SERVER_URL/maintenance/daily-diary" \
            -H "Authorization: Bearer $MEMORY_DEFAULT_USER_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"date\":\"$DATE\",\"dry_run\":false}"
        env:
          MEMORY_SERVER_URL: ${{ secrets.MEMORY_SERVER_URL }}
          MEMORY_DEFAULT_USER_TOKEN: ${{ secrets.MEMORY_DEFAULT_USER_TOKEN }}
```

注意：`date -u -d 'yesterday'` 是 UTC 昨天；如果你要照
`daily_diary.timezone` 的本地日期切日界，之後可以新增一個 server-side
`date=auto` 模式，讓 server 自己依 timezone 決定要產生哪一天。

## 7. Render Free 限制

Render Free Web Service 沒流量一段時間會 spin down，所以：

- 第一次 request 會有 cold start。
- GitHub Actions 打 daily diary 時要接受啟動延遲。
- Remote MCP 若需要長時間穩定連線，Free plan 可能不夠。
- Supabase connection pool 要保守，Render 範例先用 `pool_max_size=3`。

目前不建議把 migration 放進 container startup。Production schema 變更應該先
手動跑 migration，確認 doctor healthy，再部署新版 server。
