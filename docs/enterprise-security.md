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
| AI Gateway | なし (デフォルト有効) | APIM AI Gateway 接続 + モデルガバナンス |
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

### AI Gateway（APIM 統合）
- `USE_AI_GATEWAY=true`（デフォルト）で APIM を AI Gateway として Foundry に接続。モデル API 呼び出しも APIM 経由でガバナンス対象にできる。
- Foundry project connection: `category: ApiManagement` + `authType: ProjectManagedIdentity`。ARM REST API (`Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview`) で自動作成。
- AI Gateway 接続 (`inventory-ai-gateway`) とは別に、MCP ツール用の RemoteTool 接続 (`inventory-mcp-connection`) も両経路で作成。
- `USE_AI_GATEWAY=false` にすると RemoteTool 接続のみ作成。MCP ツール呼び出しだけ APIM 経由、モデル呼び出しは Foundry 直接。
- Content Safety ポリシー (`llm-content-safety`) は AI Services リソースの Content Safety エンドポイントを利用。postprovision step8b で自動適用。
- TPM 制御 (`llm-token-limit`, 10K TPM) は AI Gateway API に自動適用。MCP API ではなくモデル API に対する制御。
- APIM ARM API バージョン: MCP Server API は GA バージョン (`2024-05-01`) では見えない。`2024-06-01-preview` を使う必要がある。

### APIM ポリシー適用マトリクス

| API | ポリシー | 内容 | 適用タイミング |
|-----|---------|------|-------------|
| `inventory-mcp` (MCP Server) | `validate-azure-ad-token` | Entra JWT 検証（audience = `api://ENTRA_APP_CLIENT_ID`） | postprovision step8 |
| `inventory-mcp` (MCP Server) | `rate-limit-by-key` | IP ベース 60 req/min | postprovision step8 |
| `inventory-mcp` (MCP Server) | セキュリティヘッダー | `nosniff`, `DENY`, `no-store` | postprovision step8 |
| `foundry-*` (AI Gateway) | `llm-token-limit` | 10,000 TPM、サブスクリプション単位 | postprovision step8b |
| `foundry-*` (AI Gateway) | `llm-content-safety` | Hate/SelfHarm/Sexual/Violence フィルタリング | postprovision step8b |
| `inventory-api` (REST API) | なし（将来: payload limit + retry） | バックエンド REST API はポリシーなし | - |

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
- Azure Portal Dashboard (`Microsoft.Portal/dashboards`): Bicep で自動プロビジョニング。KQL パネル 8 個（リクエスト数、エラー率、P50/P95/P99 レイテンシ、エンドポイント別、5xx エラー一覧、ステータスコード分布、例外発生数）。常時モニタリング向き。
- Azure Workbook (`Microsoft.Insights/workbooks`): Bicep で自動プロビジョニング。時間範囲パラメータ付きインタラクティブレポート。深堀り分析・デモ向き。
- Azure Monitor dashboards with Grafana (無料・ポータル組み込み版): 手動設定。API 自動投入は無料版では非対応。
- SQL + Key Vault の Diagnostic Settings → Log Analytics。

### コンテナ・Docker
- Dockerfile はマルチステージビルド (builder → runtime)。
- runtime イメージで非 root ユーザー (`appuser`) 実行。`gnupg2`, `curl`, `apt-transport-https` を purge して攻撃面を削減。
- runtime に `unixodbc` + `libgssapi-krb5-2` を明示インストール。`--no-install-recommends` だけだと MI トークン認証で SQL 接続が `Can't open lib` エラーになる（Kerberos ライブラリ不足）。
- HEALTHCHECK は python urllib ベース（curl 不要）。
- 初回デプロイ時の ACR イメージ不在対策: Bicep の containerImage パラメータが空の場合は MCR のプレースホルダーを使用。`azd deploy` が実際のイメージで上書きする。

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

- `ENTRA_APP_CLIENT_ID`: MCP policy の audience 検証用 Entra App ID。postprovision が権限があれば自動登録する。
- `MCP_PROJECT_CONNECTION_ID`: Foundry の RemoteTool project connection 名。ProjectManagedIdentity 認証で Entra JWT を送る正式経路。
- `ALERT_EMAIL_ADDRESS`: KQL アラート通知先メールアドレス。
- `USE_AI_GATEWAY`: `true`（デフォルト）で APIM を AI Gateway として Foundry に接続。`false` で MCP Only（RemoteTool connection のみ）。

## デモ説明で使うポイント

- 入口の認証は APIM に集約し、バックエンドは private ネットワーク上の REST API のまま。MCP プロトコル変換も APIM が担い、アプリコードは REST のみ。
- AI Gateway 経路ではモデル呼び出しも APIM 経由となり、JWT 検証 / rate-limit / ログ収集がモデル API にも適用される。
- バックエンド接続やイメージ pull でパスワードを使わず、Managed Identity へ寄せている。
- デモ構成と本番構成の差分は `enableEnterpriseSecurity` フラグ 1 つで切り替え。AI Gateway の有無は `USE_AI_GATEWAY` フラグで切り替え。
- 観測性は gateway (APIM App Insights)、実行基盤 (CA App Insights)、アプリ (OTel middleware) の 3 層。Grafana Dashboard で可視化。
- KQL アラート 5 種でセキュリティ (認証失敗スパイク) と運用 (エラー率, レイテンシ, CPU, リスタート) を網羅。
- NSG Flow Logs + Traffic Analytics で全ネットワークトラフィックを記録・分析。

## まだ残る手動工程

- APIM の MCP server 自体の作成（ARM API 未対応、AI Gateway / MCP Only 両方で必要）
- Foundry ポータルからM365 Copilot への publish
- 新しい Foundry publish を追加した場合の client app id 登録
- GitHub Actions deploy ジョブ用の Federated Credentials 設定

以下は postprovision で自動化済み:
- Entra App 登録（権限があれば自動、なければ手順案内）
- APIM → CA ヘルスチェック（VNet integration 検証）
- AI Gateway 接続（USE_AI_GATEWAY=true 時）

## enterprise 設定を戻すときの順序

1. 新しい APIM で REST API の 200 応答を確認する。
1. MCP server を作成し、`tools/list` が空でないことを確認する。
1. diagnostics を追加する場合は Frontend Response payload bytes を 0 に固定する。
1. Foundry project に RemoteTool connection（ProjectManagedIdentity、audience = `api://{{ENTRA_APP_CLIENT_ID}}`）を作成し、agent 側で `project_connection_id` を指定する。APIM MCP API には `validate-azure-ad-token`（audience 検証のみ）を入れる。
1. custom header 認証は fallback としてのみ使う。
1. `validate-azure-ad-token` を APIM service 全体に入れると MCP の内部 tool call が 401 になるため、JWT 検証は MCP API スコープのみにする。
1. `rate-limit-by-key` は counter-key に `context.Request.IpAddress` を使う。Authorization ヘッダー expression を counter-key にすると HTTP 500 になる。

## Azure AI / Cognitive Services RBAC ロール整理

Foundry + APIM 構成で登場するロールが多く混乱しやすいため整理する。

### ロール一覧と権限マトリクス

| ロール | 管理操作 (Actions) | データ操作 (DataActions) |
|--------|-------------------|------------------------|
| **Azure AI Administrator** | CognitiveServices/*, ML workspaces/*, KV, ACR, Storage, CosmosDB, Search, DataFactory 全部入り | なし |
| **Azure AI Developer** | ML workspaces/* (read/write/action/delete) ※workspace 自体の作成削除は NotActions で除外 | `OpenAI/*`, `SpeechServices/*`, `ContentSafety/*`, `MaaS/*` |
| **Azure AI Inference Deployment Operator** | deployments/*, AutoscaleSettings/write | なし |
| **Azure AI Enterprise Network Connection Approver** | 各種リソースの PE 承認操作 (APIM, ACR, KV, SQL, CosmosDB, Storage, Search 等) | なし |
| **Cognitive Services Contributor** | `Microsoft.CognitiveServices/*` (リソース CRUD、キー管理) ※RAI ポリシーの write/delete は NotActions で除外 | なし |
| **Cognitive Services User** | CognitiveServices の read + listkeys | **`Microsoft.CognitiveServices/*`** (ワイルドカード) |
| **Cognitive Services Data Reader** | なし | `Microsoft.CognitiveServices/*/read` (読み取りのみ) |
| **Cognitive Services OpenAI User** | CognitiveServices の read | `OpenAI/*/read`, completions, chat, embeddings, images, **assistants/\***, **responses/\*** ※stored-completions/read は NotDataActions で除外 |
| **Cognitive Services OpenAI Contributor** | CognitiveServices の read + deployments write/delete + RAI ポリシー管理 | `OpenAI/*` (全データ操作) |
| **Cognitive Services Usages Reader** | usages/read のみ | なし |

### 本プロジェクトで必要な操作と対応ロール

| 操作 | 必要な権限種別 | 最小ロール |
|------|--------------|-----------|
| Foundry account/project の作成・管理 | Actions: `Microsoft.CognitiveServices/*` | Cognitive Services Contributor |
| APIM から Foundry への MI 接続 | Actions: `Microsoft.CognitiveServices/*` | Cognitive Services Contributor |
| OpenAI モデル呼び出し (Chat/Completions) | DataActions: `OpenAI/*` | Cognitive Services OpenAI User |
| Agent SDK 2.x: エージェント作成・一覧 | DataActions: `AIServices/agents/*` | **Cognitive Services User** |
| Agent SDK 2.x: エージェント実行 | DataActions: `AIServices/agents/*` | **Cognitive Services User** |
| MCP ツール呼び出し (Agent 経由) | DataActions: `AIServices/agents/*` | **Cognitive Services User** |
| PE 承認 (Enterprise 構成) | Actions: PE 関連 | Azure AI Enterprise Network Connection Approver |

### ハマりポイント: `AIServices/agents/*` をカバーするロール

Agent SDK 2.x（`azure-ai-projects` 2.0+）は以下のデータアクションを要求する:

- `Microsoft.CognitiveServices/accounts/AIServices/agents/read`
- `Microsoft.CognitiveServices/accounts/AIServices/agents/write`

各ロールの DataActions を展開すると:

| ロール | `AIServices/agents/*` カバー | 理由 |
|--------|:--:|------|
| Azure AI Developer | ❌ | `OpenAI/*`, `SpeechServices/*`, `ContentSafety/*`, `MaaS/*` の 4 種だけ |
| Cognitive Services OpenAI User | ❌ | `OpenAI/*` スコープに限定 |
| Cognitive Services OpenAI Contributor | ❌ | `OpenAI/*` スコープに限定 |
| Cognitive Services Data Reader | ❌ | read のみ、かつ `agents` は新しいプロバイダー |
| **Cognitive Services User** | ✅ | **`Microsoft.CognitiveServices/*`** ワイルドカードで全カバー |

`AIServices` 名前空間は後発のため、個別スコープのロール（AI Developer, OpenAI User/Contributor）の定義に入っていない。ワイルドカードを持つ **Cognitive Services User** のみがカバーする。

### 本プロジェクトの推奨構成

**postprovision step1 で自動付与するロール:**

```
Azure AI Developer        → account + project レベル
Cognitive Services User   → account + project レベル
```

| 付与先 | ロール | 目的 |
|--------|-------|------|
| 実行ユーザー (postprovision 実行者) | Azure AI Developer + Cognitive Services User | Agent 作成・テストに必要 |
| APIM Managed Identity | Cognitive Services Contributor | Foundry リソースへの管理アクセス |
| Container App Managed Identity | (SQL 側で MI ユーザー作成) | SQL データアクセス |
| Agent Identity (publish 後) | Cognitive Services User | M365 Copilot 経由の Agent 実行に必要 |

### Owner/Contributor ロールとの関係

サブスクリプション/RG レベルの Owner や Contributor は**管理操作 (Actions)**のみを付与する。**データ操作 (DataActions)**は含まれないため、Owner であっても Cognitive Services User を別途付与しないと Agent SDK は使えない。
