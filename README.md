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
本番:  Foundry → APIM (VNet integration) → Container Apps (internal CAE, VNet-scope ingress) → SQL (PE only)
       + VNet + NSG + Key Vault + Defender + Managed Identity
```

Container Apps に MCP 実装なし。APIM が REST → MCP 変換。
internal CAE では ingress.external = true が「VNet scope」を意味する（インターネットには出ない）。

## M365 Publish Note

- M365 Copilot / Teams への公開は Organization scope で正常動作を確認
- `project_connection_id`（ProjectManagedIdentity）+ APIM `validate-azure-ad-token` でキーレス Entra JWT 認証

## Sample Data Note

- `scripts/setup.sql` の商品名は一般名詞ベースのサンプルデータにしており、特定のブランド名や固有商品名は使わない。
- SQL Server に日本語を正しく投入するため、seed データは Unicode リテラル `N'...'` を使う。

## Enterprise Security (WAF/CAF Zero Trust)

`enableEnterpriseSecurity=true` で有効化:

- VNet + 4 サブネット + NSG（VirtualNetwork タグで VNet 内通信許可 + DenyAllInbound）
- Container Apps: internal CAE + external ingress = VNet-scope（インターネット非公開）
- Private Endpoint: SQL, Key Vault（public access disabled）
- Managed Identity: Container Apps → SQL、ACR pull（シークレットレス）
- APIM Standard v2: VNet outbound integration（`virtualNetworkType: External`）
- Key Vault（RBAC, soft delete, PE）
- Defender for Cloud（SQL, Containers, Key Vault）
- MCP API: `validate-azure-ad-token` + `rate-limit-by-key`（IP ベース 60/min）
- Observability: Container Apps → Log Analytics、APIM → Application Insights

enterprise mode の `azd up` 後の手動ステップ:

1. APIM → APIs → OpenAPI import → Container Apps の `/openapi.json`
2. APIM → MCP Servers → Create MCP server
3. `scripts/apply-mcp-policy.sh` で JWT + rate-limit policy を適用
4. Private DNS Zone を CAE default domain で作成（`*` と `@` の A レコード → static IP）
5. Foundry → エージェント作成 → MCP ツール接続
6. Foundry → Publish to M365 Copilot (Organization scope 推奨)

### ハマりポイント

- internal CAE で `ingress.external: false` にすると **CA Environment 内からのみ**到達可能。APIM からは 404 になる
- NSG で APIM subnet (10.0.1.0/24) を source にしても不十分。APIM VNet integration の outbound IP は VirtualNetwork タグで広く許可する
- APIM Standard v2 の Bicep は `virtualNetworkType: 'External'` + `virtualNetworkConfiguration.subnetResourceId`
- Frontend Response payload bytes = 0 を維持（MCP SSE が不安定になる）
- `validate-azure-ad-token` は MCP API スコープのみに入れる（service 全体に入れると MCP 内部 tool call が 401）

## Zenn 記事

```bash
npm install && npx zenn preview
```

## Cleanup

```bash
azd down --purge
```

## 自動化の範囲

`azd up` で以下が自動実行される:

| ステップ | 方法 | 備考 |
|---------|------|------|
| インフラ全体 | Bicep | VNet, SQL, ACR, CA, APIM, KV, Defender, Foundry |
| モデルデプロイ (4種) | Bicep | gpt-4.1-mini, gpt-4.1, gpt-5-mini, gpt-5.2 |
| コンテナビルド＆デプロイ | azd deploy | ACR Tasks リモートビルド |
| Foundry project | postprovision | CLI（Bicep 未対応） |
| Private DNS Zone | postprovision | internal CAE 用 |
| SQL データ投入 + MI 権限 | postprovision | 一時的に public access ON→OFF |
| APIM REST API import | postprovision | OpenAPI spec 自動生成 |
| Foundry connection (PMI) | postprovision | REST API |
| MCP policy (JWT+rate-limit) | postprovision | MCP Server 存在時のみ |
| Agent 作成 | postprovision | SDK スクリプト |

### 手動ステップ（初回のみ）

1. **APIM MCP Server 作成** — ポータル必須（ARM API 未対応）
2. **APIM VNet integration 確認** — ポータルで「有効」確認
3. **Entra App 登録** — `scripts/setup-entra.sh`（初回のみ）

### M365 Copilot への公開

Agent publish と M365 配信は REST API で自動化可能だが、以下は手動:

- **Agent Application 作成** — REST API (`PUT /providers/Microsoft.CognitiveServices/accounts/.../agentApplications/...`) で可能。postprovision.py に追加で実装可能
- **M365 Copilot/Teams への publish** — Foundry ポータルの UI で「Publish to Teams and M365 Copilot」を選択。Bot Service 作成、メタデータ入力が必要
- **Organization scope 承認** — テナント管理者が M365 Admin Center で承認

Agent publish の REST API 化は可能だが、M365 配信パッケージの作成はポータル UI に依存する。
