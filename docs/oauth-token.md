# OAuth Token 兌換與更新

Phase 6 已提供 `POST /oauth/token`，支援 public client 使用 authorization code + PKCE 取得 access token，以及使用 refresh token 更新憑證。這使 Phase 4 至 Phase 7 組成一條完整的 OAuth 連線流程。

依照 [OpenAI 官方 OAuth 文件](https://developers.openai.com/zh-Hant/plugins/build/auth)，ChatGPT 會使用 PKCE S256 兌換 authorization code，並在授權與 Token 請求中原樣傳遞 `resource`。本服務會重新核對這些資料，而不只相信瀏覽器授權階段的結果。

## Authorization code 兌換

```mermaid
sequenceDiagram
    participant Client as ChatGPT
    participant Token as POST /oauth/token
    participant DB as Supabase
    Client->>Token: code、client_id、redirect_uri、resource、code_verifier
    Token->>Token: SHA-256 verifier，再轉為 Base64URL challenge
    Token->>DB: 鎖定 authorization code
    DB->>DB: 核對 code、client、callback、resource、PKCE、期限與帳號狀態
    DB->>DB: 消耗 code，建立 token family 與 token hashes
    DB-->>Token: 使用者、client、scope 與到期時間
    Token-->>Client: access token、選用的 refresh token、scope、expires_in
```

請求使用 `application/x-www-form-urlencoded`：

| 欄位 | 規則 |
| --- | --- |
| `grant_type` | 必須是 `authorization_code` |
| `code` | Phase 5 回傳的一次性 code |
| `client_id` | 必須與授權 code 綁定的 public client 完全一致 |
| `redirect_uri` | 必須與原始授權請求完全一致 |
| `resource` | 可省略，預設為目前 MCP resource；明確提供時必須與原始授權及目前 MCP resource 完全一致 |
| `code_verifier` | 43 至 128 字元，只接受 RFC 7636 的 unreserved characters |

成功後，access token 有效期最長一小時；token family 有效期 30 天。只有 client 註冊了 `refresh_token` grant 時才會回傳 refresh token。原始 code 與 tokens 都不寫入資料庫，只保存 SHA-256 hash。

## Refresh token rotation

```mermaid
flowchart LR
    R1[提交 R1] --> V1{R1 是否首次使用？}
    V1 -->|是| I[將 R1 標記為已使用]
    I --> N[發行 access token 與 R2]
    V1 -->|否，偵測到重放| X[撤銷整個 token family]
    X --> D[同 family 的 access 與 refresh tokens 全部失效]
```

更新請求包含 `grant_type=refresh_token`、`refresh_token` 與 `client_id`；`resource` 可省略，使用目前 MCP resource。可選的 `scope` 只能縮小原始授權範圍，不能增加權限。每次成功更新都會回傳新的 refresh token；舊 token 立即標記為已使用。

若已使用的 refresh token 再次出現，服務會把這次情況視為憑證可能外洩，並在同一筆資料庫交易中撤銷整個 family。即使舊 access token 尚未到期，Phase 7 的每次請求驗證也會因 family 已撤銷而拒絕它。

## 錯誤與安全限制

| 錯誤 | 使用時機 |
| --- | --- |
| `invalid_request` | 缺少欄位、重複欄位或錯誤 Content-Type |
| `invalid_client` | 提交 client secret、client assertion 或 HTTP Authorization |
| `invalid_grant` | Code、PKCE、refresh token、callback、client 或 resource 不符，或憑證已過期／使用／撤銷 |
| `invalid_scope` | Refresh 要求超出原始授權範圍 |
| `unsupported_grant_type` | 不是 authorization code 或 refresh token grant |
| `temporarily_unavailable` | 資料庫暫時無法使用 |

所有回應都帶有 `Cache-Control: no-store` 與 `Pragma: no-cache`。請求 body 上限為 16 KiB；每個服務程序每分鐘最多處理 120 次嘗試。多程序部署仍應由入口服務提供共用流量限制。

目前只支援 public client 的 `token_endpoint_auth_method=none`，不接受 client secret。Token 端點的查詢、一次性消耗與 token 建立會在同一筆 PostgreSQL 交易內完成。

依 OAuth 規格，Token 請求中未識別的擴充參數會被忽略；已知但不支援的 client authentication 欄位仍會被拒絕。伺服器只會在日誌中記錄安全的拒絕原因，不會記錄授權碼、Token、PKCE verifier 或使用者憑證。

Token 端點使用與受保護資源探索文件相同的標準 resource URL；當 resource 是網域根路徑時，會保留結尾的 `/`，以符合 OAuth 的精確字串比對要求。


## Muse 等一般 OAuth client 的相容模式

本服務只有一個 MCP resource，因此 authorize、authorization code 交換及 refresh
請求省略 `resource` 時，都使用設定的標準 MCP resource URL。
這符合 [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707.html#section-2.1)
允許伺服器使用預設 resource 的規則。明確傳入空值、其他 URL 或重複欄位仍會被拒絕。
資料庫仍核對 code／token family 的 resource、client、callback 與 PKCE 綁定；
MCP 存取驗證也仍要求 token 的 resource 完全相符。

依 Muse 使用者提供的流程，自訂 OAuth 連接無法傳遞 `resource`。
部署此變更後，不必再將 `resource` 塞進 authorization URL 的 query string：

- MCP URL：`https://second-brain-x2iu.onrender.com/mcp`
- API hostname：`second-brain-x2iu.onrender.com`
- Authorization URL：`https://second-brain-x2iu.onrender.com/oauth/authorize`
- Token URL：`https://second-brain-x2iu.onrender.com/oauth/token`
- Registration URL：`https://second-brain-x2iu.onrender.com/oauth/register`
- Issuer：`https://second-brain-x2iu.onrender.com/`
- Redirect URI：`https://agent.meta.ai/api/hatch/oauth/callback`（由 client 註冊並精確比對）
- Scope：只記錄對話使用 `memory:write`；需要讀取時才加上 `memory:read`。
- Client authentication：`none`；PKCE：`S256`。

若要更新 token，DCR 必須註冊 `refresh_token` grant。
這是向後相容的伺服器變更，不需資料庫 migration 或轉換既有 token。
部署後從 Muse 重新開始授權，使用新 code；既有明確傳遞正確 resource 的 client 行為不變。
OAuth 成功後，Muse 的 skill 仍須使用 MCP 協定呼叫 `/mcp`；
本變更不會把管理 REST API 改成接受 OAuth token。

### Muse callback 的 CSP 相容設定

Muse 的 `https://agent.meta.ai/api/hatch/oauth/callback` 會再導向
`https://muse.ai/api/hatch/oauth/callback`。部分瀏覽器會將登入表單的
`form-action` 限制套用到後續重新導向，因此登入頁需要允許這個最終 origin。
只有已驗證的註冊 callback 完全等於上述 `agent.meta.ai` URL 時，登入頁
（包含密碼錯誤後重新顯示的頁面）才會額外允許 `https://muse.ai`。
不同路徑、尾端斜線或附加 query 不會啟用此例外；ChatGPT 與其他 client 維持原政策。
這只改變 CSP，不改寫 OAuth callback，也不放寬 redirect URI、PKCE 或 token 驗證。
部署後仍需在 Muse 實測 303 → 302 的跳轉鏈及 token 交換。

平台專屬政策集中在 `server/auth/client_compatibility.py`；`oauth_login` 只負責
套用政策並產生 CSP。新增這類 callback 導向例外時，更新政策表與對應測試即可。
政策函式只接受已通過註冊 callback 比對的 URI，未知 URI 不增加任何 origin。
共用的 OAuth 驗證及省略 `resource` 時的預設行為不屬於平台專屬政策。
