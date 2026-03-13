# inventory-api

Foundry エージェントが APIM (MCP) 経由で在庫を参照し、M365 Copilot で動くデモ。
`enableEnterpriseSecurity=true` でエンプラ本番構成（VNet, PE, KV, Defender, MI）に切り替え可能。

## Quick Start

```bash
# デモ（public 構成）
azd auth login && azd up

# 本番（VNet + Private Endpoint + Key Vault + Defender + Managed Identity）
azd env set ENABLE_ENTERPRISE_SECURITY true
azd up
```

## Architecture

```text
デモ:  Foundry → APIM (public) → Container Apps (public) → SQL (public)
本番:  Foundry → APIM (VNet out) → Container Apps (internal/PE) → SQL (PE) + KV + Defender
```

Container Apps に MCP 実装なし。APIM が REST → MCP 変換。

## M365 Publish Note

- 2026-03 時点の検証では、M365 Copilot / Teams への公開は Organization scope で正常動作を確認。
- Individual scope は Foundry 側の publish 挙動が不安定で、Channels application は作成されても deployment が正しく切り替わらず応答できないケースがあった。
- MCP ツール付き agent も、MCP なし agent も同じ傾向だったため、M365 配布デモは Organization scope 前提で扱う。
- 2026-03-13 の切り分けでは、旧 APIM `apim-pklmdvehtuixu` の MCP ランタイムが壊れ、`/mcp` が空応答になる事象を確認。新しい APIM `apim-pklmdvehtuiv2` へ REST API と MCP server を再作成し、`inventory-v4` の Foundry / M365 Copilot 動作を確認した。
- 同日、`project_connection_id`（ProjectManagedIdentity）+ APIM `validate-azure-ad-token`（audience 検証）の構成で `inventory-v6-pmi` を作成し、Foundry playground → M365 Copilot publish（Organization scope）→ Teams テストまで、キーレス Entra JWT で end-to-end 成功を確認した。

## Sample Data Note

- `scripts/setup.sql` の商品名は一般名詞ベースのサンプルデータにしており、特定のブランド名や固有商品名は使わない。
- SQL Server に日本語を正しく投入するため、seed データは Unicode リテラル `N'...'` を使う。

## Enterprise Security (WAF/CAF Zero Trust)

`enableEnterpriseSecurity=true` で有効化:

- VNet + 4 サブネット + NSG（snet-apim → snet-ca → snet-sql の一方通行）
- Private Endpoint（SQL, Key Vault）+ Private DNS zone group
- Managed Identity（Container Apps → SQL、ACR pull。シークレットレス）
- Key Vault（RBAC, soft delete, PE）
- Defender for Cloud（SQL, Containers, Key Vault）
- APIM: diagnostics は維持する。MCP API には `validate-azure-ad-token`（audience 検証）を適用し、Foundry 側は `project_connection_id`（ProjectManagedIdentity）経由で Entra JWT を送る構成が正式パス。custom header 認証は fallback として残す
- Observability: Container Apps → Log Analytics、APIM → Application Insights、API アプリ → Application Insights(OpenTelemetry)

Enterprise mode の追加手順:

- Foundry / Bot の client app id を `APIM_ALLOWED_CLIENT_APP_IDS` に設定して `azd provision`
- M365 公開後に agent identity へ `MCP.Tools.Read` を割り当てる
- enterprise 設定を戻すときは、先に REST API と MCP server の疎通を確認し、その後で diagnostics と policy を段階適用する。MCP では Frontend Response payload bytes を 0 のまま維持し、`context.Response.Body` を読む policy は入れない。2026-03-13 に `project_connection_id`（ProjectManagedIdentity）+ APIM MCP API の `validate-azure-ad-token`（audience 検証のみ）で `inventory-v6-pmi` の end-to-end 成功を確認した。ヘッダーなし direct access は `401` で拒否される。`rate-limit-by-key` は引き続き HTTP 500 を再現するため保留、`validate-azure-ad-token` を APIM service 全体に入れると MCP の内部 tool call が 401 になる問題も残る。

## Zenn 記事

```bash
npm install && npx zenn preview
```

## Cleanup

```bash
azd down
```

## Foundry Agent の作成メモ

`scripts/create_agent.py` は `MCP_PROJECT_CONNECTION_ID` を渡すと、Foundry の project connection 経由で Entra JWT を送る構成になります（キーレス）。fallback として `APIM_SUBSCRIPTION_KEY` / `MCP_HEADERS_JSON` も使えます。

```bash
# 推奨: project_connection_id（キーレス Entra JWT）
$env:FOUNDRY_PROJECT_ENDPOINT="https://foundry-inventory-demo.services.ai.azure.com/api/projects/inventory-project"
$env:AGENT_NAME="inventory-v6-pmi"
$env:MCP_SERVER_URL="https://apim-<name>.azure-api.net/inventory-mcp/mcp"
$env:MCP_PROJECT_CONNECTION_ID="inventory-mcp-connection"
python scripts/create_agent.py
```
