# 帳號管理 CLI

先執行 `uv sync` 安裝 `memory-admin`，並確保目標資料庫已套用 `002_user_login.sql`。
CLI 讀取目前目錄的 `.env` 中的 `DATABASE_URL`；已存在的環境變數優先。
可用 `uv run memory-admin --env-file /path/to/.env list-users` 指定檔案。
CLI 直接以資料庫連線權限管理帳號，不需要啟動 MCP、Ollama 或 HTTP admin API。

```bash
# 先設定既有 default user（id = 0）的密碼
uv run memory-admin set-password admin

# 互動詢問 username 與密碼
uv run memory-admin create-user

# 指定 username 與顯示名稱，密碼仍以隱藏輸入詢問兩次
uv run memory-admin create-user Alice --display-name Alice

uv run memory-admin set-password alice
uv run memory-admin disable-user alice
uv run memory-admin enable-user alice
uv run memory-admin list-users
```

- Username 統一轉小寫：`Alice` 和 `ALICE` 都代表 `alice`，不能重複建立。
- 新帳號使用新的 UUID 作為 user ID，預設啟用；不會覆寫既有帳號。
- 密碼要求 15–1024 字元且至少 4 種不同字元；建議使用隨機密碼或長 passphrase。
- 密碼大小寫與空白均保留，只接受終端機隱藏輸入，不支援密碼參數或可見輸入 fallback。
- 密碼保存為 Argon2id hash；輸出不包含密碼、hash 或資料庫連線字串。
- `list-users` 輸出 JSON，包含 id、username、display_name、is_active、password_configured；尚未配置登入名稱的舊帳號也會列出。
- 停用保留所有資料，既有 token 驗證會失敗。啟用會恢復帳號；修改密碼不會自動啟用帳號，也不會撤銷現有 API token。
- 成功 exit code 為 0，驗證／資料庫錯誤為 1，參數錯誤為 2，取消輸入為 130。

此階段完成帳號管理，OAuth 登入頁與 token endpoint 仍屬後續階段。
