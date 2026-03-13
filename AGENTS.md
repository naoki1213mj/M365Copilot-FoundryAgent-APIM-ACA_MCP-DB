# AGENTS.md

APIM MCP + Foundry + M365 Copilot で在庫参照エージェントを作るデモ。

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

## Foundry セットアップ（azd up で自動実行）

`azd up` の postprovision hook (`scripts/postprovision.py`) で以下が自動実行される:

1. Foundry project 作成
2. Private DNS Zone 作成（internal CAE 用）
3. SQL サンプルデータ投入 + MI ユーザー権限付与
4. APIM REST API import（OpenAPI spec 自動生成）
5. Foundry project connection 作成（ProjectManagedIdentity）
6. MCP policy 適用（MCP Server 存在時のみ）
7. Foundry agent 作成（MCP ツール + PMI 認証）

### 手動ステップ（初回のみ）

```bash
# APIM ポータルで MCP Server を作成（ARM API 未対応のため手動）
# APIM → MCP Servers → Create MCP server
#   Source API: Inventory API
#   名前: inventory-mcp

# MCP Server 作成後に azd provision を再実行（MCP policy 適用のため）
azd provision

# テスト
export FOUNDRY_PROJECT_ENDPOINT=$(azd env get-values | grep FOUNDRY_PROJECT_ENDPOINT | cut -d= -f2 | tr -d '"')
export AGENT_NAME=inventory-ent-pmi
python scripts/test_agent.py
```

### M365 Copilot への公開

```bash
# Foundry ポータルから Publish to M365 Copilot（Organization scope 推奨）
# publish 後に agent identity の権限付け直しが必要
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
