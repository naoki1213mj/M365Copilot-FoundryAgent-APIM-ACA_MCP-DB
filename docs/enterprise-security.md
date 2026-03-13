# エンタープライズセキュリティ実装メモ

`enableEnterpriseSecurity=true` を前提に、本番説明で使う実装ポイントを整理する。

| 領域 | false（デモ） | true（本番） |
| ---- | ------------- | ------------- |
| ネットワーク | 全リソース public | VNet + PE + NSG |
| SQL 認証 | UID/PWD | Managed Identity |
| Container Apps | external ingress | internal ingress |
| SQL public access | Allow Azure Services | Disabled |
| Key Vault | なし | PE + RBAC + soft delete + public access disabled |
| Defender | なし | SQL + Containers + KV |
| APIM VNet | なし | outbound VNet integration + Entra token validation |
| 観測性 | 最低限 | APIM/Application Insights + Container Apps/Log Analytics + API/OpenTelemetry |

## 実装済み

- SQL は Entra ID Only。Container Apps は `USE_MANAGED_IDENTITY=true` で `DefaultAzureCredential` を使う。
- SQL と Key Vault の Private Endpoint に Private DNS zone group をつけ、VNet 内名前解決を自動化した。
- ACR admin user は無効化し、Container Apps は user-assigned managed identity でイメージを pull する。
- APIM には enterprise mode で Application Insights diagnostics を入れる。`rate-limit-by-key` は counter-key に `context.Request.IpAddress` を使うことで MCP API でも正常動作する（Authorization ヘッダー expression を counter-key にすると HTTP 500 になる）。MCP API スコープの `validate-azure-ad-token`（audience 検証のみ、client-application-ids なし）は、Foundry 側で `project_connection_id`（ProjectManagedIdentity）を使う構成で `inventory-v6-pmi` の end-to-end 成功を確認した。ヘッダーなし direct access は `401` で拒否される。APIM service 全体に入れると MCP の内部 tool call が 401 になる問題は残るため、JWT 検証は MCP API スコープのみに入れる。custom header 認証は fallback として残す。
- API アプリ側にも Application Insights を追加し、FastAPI から `azure-monitor-opentelemetry` で trace と log を送る。
- brownfield 移行では `inventory-api-ent` を新設し、`scripts/grant_sql_access.py` で SQL contained user と `db_datareader` を付与する。
- 2026-03-13 の切り分けでは、旧 APIM サービスで MCP ランタイム不整合が起き、`type: mcp` と `mcpTools` が ARM 上に見えていても `/mcp` が空応答になる事象を確認した。新しい APIM `apim-pklmdvehtuiv2` では同じ REST API / MCP 定義で正常動作した。
- 同日、`inventory-v6-pmi`（project_connection_id + ProjectManagedIdentity）を M365 Copilot に Organization scope で publish し、Teams 経由の end-to-end テストに成功した。publish 後も PMI（Foundry account MI）のトークンが使われるため、APIM 側の JWT policy 変更は不要だった。

## 運用で入れる値

- `APIM_ALLOWED_CLIENT_APP_IDS`: Foundry または Bot Service publish 後に分かる client app id の一覧。将来 MCP caller が Authorization ヘッダーを送るようになったら更新して使う。
- `MCP_PROJECT_CONNECTION_ID`: Foundry の RemoteTool project connection 名。ProjectManagedIdentity 認証で Entra JWT を送る正式経路。
- `APIM_SUBSCRIPTION_KEY` または同等の custom header 値: fallback 手段。agent 作成時に `MCPTool.headers` へ渡せるが、常設運用の既定値にはしない。
- `MCP.Tools.Read`: Entra app role。将来 JWT を再検証するときに使う。

## 顧客説明で使うポイント

- 入口の認証は APIM に集約し、バックエンドは private ネットワーク上の REST API のままにしている。
- バックエンド接続やイメージ pull でパスワードを使わず、Managed Identity へ寄せている。
- デモ構成と本番構成の差分は `enableEnterpriseSecurity` と運用時の app id 登録に閉じている。
- 観測性は gateway、実行基盤、アプリの 3 層に分け、APIM と API を別の Application Insights で追えるようにした。

## まだ残る手動工程

- APIM の MCP server 自体の作成と OpenAPI import
- 新しい Foundry publish を追加した場合の client app id 登録
- 新しい agent identity を追加した場合の `MCP.Tools.Read` 割り当て

## enterprise 設定を戻すときの順序

1. 新しい APIM で REST API の 200 応答を確認する。
1. MCP server を作成し、`tools/list` が空でないことを確認する。
1. diagnostics を追加する場合は Frontend Response payload bytes を 0 に固定する。
1. Foundry project に RemoteTool connection（ProjectManagedIdentity、audience = `api://{{ENTRA_APP_CLIENT_ID}}`）を作成し、agent 側で `project_connection_id` を指定する。APIM MCP API には `validate-azure-ad-token`（audience 検証のみ）を入れる。
1. custom header 認証は fallback としてのみ使う。
1. `validate-azure-ad-token` を APIM service 全体に入れると MCP の内部 tool call が 401 になるため、JWT 検証は MCP API スコープのみにする。
1. `rate-limit-by-key` は counter-key に `context.Request.IpAddress` を使う。Authorization ヘッダー expression を counter-key にすると HTTP 500 になる。
