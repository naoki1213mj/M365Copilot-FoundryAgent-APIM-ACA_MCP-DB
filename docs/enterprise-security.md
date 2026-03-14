# エンタープライズセキュリティ実装メモ

`enableEnterpriseSecurity=true` を前提に、本番説明で使う実装ポイントを整理する。

| 領域 | false（デモ） | true（本番） |
| ---- | ------------- | ------------- |
| ネットワーク | 全リソース public | VNet + PE + NSG + Flow Logs + Traffic Analytics |
| SQL 認証 | Managed Identity | Managed Identity (同一) |
| SQL Collation | Japanese_CI_AS | Japanese_CI_AS (同一) |
| Container Apps | external ingress | internal ingress (VNet scope) |
| SQL public access | Allow Azure Services | Disabled + Private Endpoint |
| Key Vault | なし | PE + RBAC + soft delete + シークレット管理 + Diagnostics |
| Defender | なし | SQL + Containers + KV |
| APIM VNet | なし | outbound VNet integration + Entra token validation |
| APIM ポリシー | 空 | JWT + rate-limit + payload 1MB + retry/timeout + セキュリティヘッダー |
| Azure Bastion | なし | Standard SKU (tunneling + IP connect) |
| 監視 | App Insights (CA) | APIM App Insights + CA App Insights + 構造化ログ + OTel middleware |
| アラート | なし | KQL 5 種 (エラー率, P95 レイテンシ, SQL CPU, CA リスタート, 認証失敗スパイク) |
| ダッシュボード | なし | Azure Monitor dashboards with Grafana (2 ダッシュボード) |
| Diagnostics | なし | SQL + Key Vault → Log Analytics |

## 実装済み

### ネットワーク・認証
- SQL は Entra ID Only。Container Apps は `DefaultAzureCredential` で Managed Identity 認証。
- SQL と Key Vault の Private Endpoint に Private DNS zone group をつけ、VNet 内名前解決を自動化。
- ACR admin user は無効化し、Container Apps は user-assigned managed identity でイメージを pull。
- NSG は `VirtualNetwork` サービスタグで APIM → CA 通信を許可。`DenyAllInbound` で外部通信を遮断。
- NSG Flow Logs (3 NSG 分) + Traffic Analytics で全トラフィックを Log Analytics に記録。
- Azure Bastion (Standard SKU) でトラブルシュート用の安全なアクセスを提供。

### APIM セキュリティ
- APIM には enterprise mode で Application Insights diagnostics を入れる。
- `rate-limit-by-key` は counter-key に `context.Request.IpAddress` を使用（Authorization ヘッダー expression を counter-key にすると HTTP 500 になる）。
- MCP API スコープの `validate-azure-ad-token`（audience 検証のみ、client-application-ids なし）は、Foundry 側で `project_connection_id`（ProjectManagedIdentity）を使う構成で end-to-end 成功を確認。ヘッダーなし direct access は `401` で拒否。
- APIM service 全体に JWT を入れると MCP の内部 tool call が 401 になる問題は残るため、JWT 検証は MCP API スコープのみに入れる。
- セキュリティヘッダー: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Cache-Control: no-store`。
- MCP API では `<forward-request>` に `timeout`/`retry-count` 属性を使えない（APIM が内部で処理するため ValidationError になる）。`<base />` を使用。
- リクエストサイズ上限（payload limit）と `forward-request` のリトライは REST API (inventory-api) にのみ適用可能。MCP API には適用不可。

### 可観測性
- API アプリ側にも Application Insights を追加し、FastAPI から `azure-monitor-opentelemetry` で trace と log を送る。`enable_live_metrics=False` で PII 保護。
- 構造化 JSON ログ (`{"time":"...","level":"...","logger":"...","message":"..."}`) で KQL クエリの利便性向上。
- OTel リクエスト計測ミドルウェアで各エンドポイントの処理時間を自動計測してレスポンスヘッダー `X-Duration-Ms` に付与。
- KQL アラート 5 種:
  1. API エラー率 > 5% (App Insights / 15分窓)
  2. APIM P95 レイテンシ > 5秒 (AzureDiagnostics GatewayLogs)
  3. SQL CPU > 80% (メトリクスアラート)
  4. Container App リスタート検知 (ContainerAppSystemLogs)
  5. APIM 認証失敗 (401) スパイク > 20件/15分 (ブルートフォース検知)
- Azure Monitor dashboards with Grafana (無料・ポータル組み込み版): 2 ダッシュボード
  - 在庫 API 概要: リクエスト数、エラー率、P95 レイテンシ、レイテンシ分布、エンドポイント別
  - 在庫 API アラート: 5xx エラー一覧、ステータスコード分布、例外発生数
- SQL + Key Vault の Diagnostic Settings → Log Analytics。

### コンテナ・Docker
- Dockerfile はマルチステージビルド (builder → runtime)。
- runtime イメージで非 root ユーザー (`appuser`) 実行。`gnupg2`, `curl`, `apt-transport-https` を purge して攻撃面を削減。
- HEALTHCHECK は python urllib ベース（curl 不要）。

### CI/CD
- GitHub Actions 4 ジョブ: lint-and-test, security-scan (pip-audit + bandit), bicep-validate, deploy (federated credentials)。
- deploy ジョブは main push のみ、`environment: production` で保護。
- デプロイ後に `smoke_test.ps1` で自動検証。

### データベース
- 3 テーブル正規化: products (20品), warehouses (3拠点), inventory (31行, 発注点割れ 8件)。
- SQL Collation: `Japanese_CI_AS` で日本語ソート・比較を保証。
- `mcp_readonly_role` + `db_datareader` の二重権限付与で read-only アクセスを保証。
- `available` は計算列 (`quantity - reserved`) で定義、PERSISTED。

## 運用で入れる値

- `ENTRA_APP_CLIENT_ID`: MCP policy の audience 検証用 Entra App ID。
- `MCP_PROJECT_CONNECTION_ID`: Foundry の RemoteTool project connection 名。ProjectManagedIdentity 認証で Entra JWT を送る正式経路。
- `ALERT_EMAIL_ADDRESS`: KQL アラート通知先メールアドレス。

## 顧客説明で使うポイント

- 入口の認証は APIM に集約し、バックエンドは private ネットワーク上の REST API のまま。MCP プロトコル変換も APIM が担い、アプリコードは REST のみ。
- バックエンド接続やイメージ pull でパスワードを使わず、Managed Identity へ寄せている。
- デモ構成と本番構成の差分は `enableEnterpriseSecurity` フラグ 1 つで切り替え。
- 観測性は gateway (APIM App Insights)、実行基盤 (CA App Insights)、アプリ (OTel middleware) の 3 層。Grafana Dashboard で可視化。
- KQL アラート 5 種でセキュリティ (認証失敗スパイク) と運用 (エラー率, レイテンシ, CPU, リスタート) を網羅。
- NSG Flow Logs + Traffic Analytics で全ネットワークトラフィックを記録・分析。

## まだ残る手動工程

- APIM の MCP server 自体の作成（ARM API 未対応）
- Foundry ポータルから M365 Copilot への publish
- 新しい Foundry publish を追加した場合の client app id 登録
- GitHub Actions deploy ジョブ用の Federated Credentials 設定

## enterprise 設定を戻すときの順序

1. 新しい APIM で REST API の 200 応答を確認する。
1. MCP server を作成し、`tools/list` が空でないことを確認する。
1. diagnostics を追加する場合は Frontend Response payload bytes を 0 に固定する。
1. Foundry project に RemoteTool connection（ProjectManagedIdentity、audience = `api://{{ENTRA_APP_CLIENT_ID}}`）を作成し、agent 側で `project_connection_id` を指定する。APIM MCP API には `validate-azure-ad-token`（audience 検証のみ）を入れる。
1. custom header 認証は fallback としてのみ使う。
1. `validate-azure-ad-token` を APIM service 全体に入れると MCP の内部 tool call が 401 になるため、JWT 検証は MCP API スコープのみにする。
1. `rate-limit-by-key` は counter-key に `context.Request.IpAddress` を使う。Authorization ヘッダー expression を counter-key にすると HTTP 500 になる。
