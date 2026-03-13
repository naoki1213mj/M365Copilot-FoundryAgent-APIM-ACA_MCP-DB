# Inventory Agent

## What This Is

Foundry エージェントが APIM (MCP) → Container Apps (REST) → Azure SQL で在庫を参照するデモ。
M365 Copilot 公開、Entra ID JWT セキュリティまで含む。

## Tech Stack

- Python 3.12 / FastAPI / uvicorn / pyodbc
- Azure SQL → Container Apps (workload profiles) → APIM Standard v2 → Foundry → M365 Copilot
- Entra ID JWT (`validate-azure-ad-token`) / Managed Identity
- azd + Bicep / uv（pip は使わない）

## Coding Guidelines

- 型ヒント必須。SQL パラメータ化のみ。DB は contextmanager
- FastAPI: summary / description を丁寧に書く（APIM が MCP tool メタデータに使う）
- 認証: DefaultAzureCredential。API キー直書き NG
- コメント/docstring は日本語、変数名は英語

## Project Structure

```
src/           → FastAPI 在庫 API
infra/         → Bicep (azd)
scripts/       → setup.sql, setup-entra.sh, postprovision.py
.github/
  instructions/  → path-specific ルール
  agents/        → inventory
  skills/        → apim-mcp / m365-publish / enterprise-security
  prompts/       → add-endpoint / security-review
```

## Key Decisions

1. MCP は APIM 側。Container Apps は REST のみ
2. 第 1 弾は read-only（M365 の required_approval=false 制約）
3. セキュリティは APIM に集約（JWT + rate limit + audit）
4. M365 は Individual scope → Organization scope の段階展開
5. publish 後 agent identity 分離 → 権限付け直し必須
6. `enableEnterpriseSecurity` フラグでデモ/本番を切り替え（VNet, PE, KV, Defender, MI）
7. Managed Identity で SQL 認証（`USE_MANAGED_IDENTITY=true`）。シークレットレス

## Resources

- `.github/skills/apim-mcp-setup/SKILL.md` — APIM MCP 設定手順
- `.github/skills/m365-publish/SKILL.md` — M365 Copilot 公開手順
- `.github/skills/enterprise-security/SKILL.md` — セキュリティ設計 + チェックリスト

## Quick Commands

```bash
azd auth login && azd up                              # デモデプロイ
azd env set ENABLE_ENTERPRISE_SECURITY true && azd up  # 本番デプロイ
azd down                                               # クリーンアップ
cd src && uvicorn main:app --reload                    # ローカル
```
