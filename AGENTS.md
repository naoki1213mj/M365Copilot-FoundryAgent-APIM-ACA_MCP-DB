# AGENTS.md

APIM MCP + Foundry + M365 Copilot で在庫参照エージェントを作るデモ。Zenn 記事も同一リポジトリ。

## Setup / Build / Test

**ローカル Docker 不要** — `azd up` は ACR Tasks によるリモートビルドを使う（`docker.remoteBuild: true`）。
Docker Desktop がインストールされていなくても `azd up` でデプロイできる。

```bash
# デモデプロイ（public 構成）
azd auth login
azd up                                # SQL + ACR + Container Apps + APIM

# 本番デプロイ（VNet + PE + KV + Defender）
azd env set ENABLE_ENTERPRISE_SECURITY true
azd up                                # 上記 + VNet, Private Endpoint, Key Vault, Defender

# ローカル開発
cd src && uv pip install -r requirements.txt
uvicorn main:app --reload             # → localhost:8000/docs

# テスト
curl http://localhost:8000/health
curl http://localhost:8000/inventory/INV-004
curl "http://localhost:8000/inventory?low_stock_only=true"
curl http://localhost:8000/openapi.json

# Zenn 記事
npm install
npx zenn new:article --slug apim-mcp-m365
npx zenn preview                      # → localhost:8000

# クリーンアップ
azd down
```

## Foundry セットアップ（azd up 後の手動ステップ）

azd up で Azure リソースをデプロイした後、以下の手順で Foundry → Agent → MCP を構築する。

```bash
# 1. サンプルデータ投入（SQL に接続できる状態で）
export SQL_SERVER_FQDN=sql-<token>.database.windows.net
export SQL_DATABASE_NAME=inventory_db
python scripts/load_data.py

# 2. Container App MI に SQL 権限付与
python scripts/grant_sql_access.py \
  --server sql-<token>.database.windows.net \
  --database inventory_db \
  --principal-name inventory-api-ent

# 3. APIM ポータルで REST API を OpenAPI import + MCP Server 作成
#    → MCP Server URL: https://apim-<token>.azure-api.net/inventory-mcp/mcp

# 4. Foundry account + project 作成（CLI）
az cognitiveservices account create \
    --name foundry-inventory-demo \
    --resource-group rg-inventory-demo \
    --kind AIServices --sku S0 -l japaneast \
    --custom-domain foundry-inventory-demo \
    --allow-project-management

az cognitiveservices account project create \
    --name foundry-inventory-demo \
    --resource-group rg-inventory-demo \
    --project-name inventory-project \
    --location japaneast

# 5. モデルデプロイ
az cognitiveservices account deployment create \
    --name foundry-inventory-demo \
    --resource-group rg-inventory-demo \
    --deployment-name gpt-4o-mini \
    --model-name gpt-4o-mini \
    --model-version "2024-07-18" \
    --model-format OpenAI \
    --sku-capacity 10 --sku-name GlobalStandard

# 6. Agent 作成
export FOUNDRY_PROJECT_ENDPOINT="https://foundry-inventory-demo.services.ai.azure.com/api/projects/inventory-project"
export AGENT_NAME="inventory-ent"
export MCP_SERVER_URL="https://apim-<token>.azure-api.net/inventory-mcp/mcp"
export FOUNDRY_MODEL="gpt-4o-mini"
python scripts/create_agent.py

# 7. テスト
python scripts/test_agent.py

# 8. Enterprise DNS（internal CAE の場合）
#    CAE の defaultDomain と staticIp を取得し Private DNS Zone を作成
az containerapp env show -g rg-inventory-demo -n cae-ent-<token> \
    --query "{domain:properties.defaultDomain,ip:properties.staticIp}" -o json
# → Private DNS Zone: <domain> に * と @ の A レコードを staticIp で作成
```

## Structure

```
src/main.py              ← FastAPI 在庫 REST API (2 endpoints)
infra/                   ← Bicep (azd provision)
scripts/setup.sql        ← サンプルデータ 20 件
scripts/setup-entra.sh   ← Entra ID app registration + APIM policy XML
articles/                ← Zenn 記事
.github/skills/          ← APIM MCP / M365 / Security / Zenn
.github/agents/          ← inventory / zenn-writer / zenn-reviewer / factchecker
.github/prompts/         ← 5 prompts
.github/instructions/    ← 4 path-specific rules
```

## 間違えやすい API / 設定

| ✅ 正しい | ❌ 間違い | 理由 |
|----------|---------|------|
| APIM Standard v2 | Consumption | Consumption は MCP 非対応 |
| `validate-azure-ad-token` | `validate-jwt` | Entra ID には専用ポリシー |
| Frontend Response payload bytes = 0 | デフォルト | MCP プロトコルが不安定になる |
| workload profiles 環境 | consumption-only 環境 | PE/UDR 不可。作成後変更不可 |
| publish 後に agent identity に権限付与 | project identity のまま放置 | 分離後は別 identity |
| Individual scope（デモ） | Organization scope（デモ） | admin 承認不要で即時利用 |
| internal CAE + `external: true` | internal CAE + `external: false` | false だと CA Environment 内のみ。APIM から 404 |
| NSG source: `VirtualNetwork` | NSG source: サブネット CIDR | APIM VNet integration の outbound IP が特定サブネットとは限らない |

## 変更の規律

- 依頼された変更だけ行う。隣接コードを勝手に改善しない
- 既存のスタイルに合わせる
- 記事のコード変更後は `/full-review` で整合性確認
- **一時ファイルやディレクトリ（/tmp 等）を使わない。すべてプロジェクトディレクトリ内で作業する**

## AI 文体禁止

記事・コメント・ドキュメントで以下を使わない:
- 「以下に示すように」「包括的に」「非常に重要」「さまざまな」「～することが可能です」
- 「羅針盤」「設計図」「両輪」「地図」「迷子」
- 「腰落ち」「要するに」「お供にどうぞ」「ぜひご一読ください」
- 体言止め、6 点以上の箇条書き、見出しコロン
