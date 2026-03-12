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

```
デモ:  Foundry → APIM (public) → Container Apps (public) → SQL (public)
本番:  Foundry → APIM (VNet out) → Container Apps (internal/PE) → SQL (PE) + KV + Defender
```

Container Apps に MCP 実装なし。APIM が REST → MCP 変換。

## Enterprise Security (WAF/CAF Zero Trust)

`enableEnterpriseSecurity=true` で有効化:

- VNet + 4 サブネット + NSG（snet-apim → snet-ca → snet-sql の一方通行）
- Private Endpoint（SQL, Key Vault, Container Apps）
- Managed Identity（Container Apps → SQL。シークレットレス）
- Key Vault（RBAC, soft delete, PE）
- Defender for Cloud（SQL, Containers, Key Vault）
- APIM: Entra ID JWT + per-session rate limit + audit trace

## Zenn 記事

```bash
npm install && npx zenn preview
```

## Cleanup

```bash
azd down
```
