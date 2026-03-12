---
name: enterprise-security
description: "APIM + Entra ID + Container Apps のエンタープライズセキュリティ設計。Azure WAF Security Pillar / CAF Zero Trust 準拠。Triggers: enterprise security, Entra ID, JWT validation, zero trust, private endpoint, audit logging, セキュリティ, 認証, validate-azure-ad-token, rate limiting, WAF, CAF, 多層防御, defense in depth"
---
# Enterprise Security（WAF/CAF Zero Trust 準拠）

`enableEnterpriseSecurity=true` で本番セキュリティが有効になる。

## Zero Trust 3 原則とこの構成の対応

| 原則 | この構成での実装 |
|------|----------------|
| Verify Explicitly | APIM で Entra ID JWT 検証。Container Apps → SQL は Managed Identity |
| Least Privilege | MCP.Tools.Read ロールのみ。SQL は db_datareader のみ |
| Assume Breach | VNet 分離 + NSG + Private Endpoint。Defender for SQL/Containers |

## ネットワーク（Defense in Depth）

```
VNet (10.0.0.0/16)
├── snet-apim  (10.0.1.0/24)  — APIM outbound VNet integration
│   NSG: inbound 443 from Internet, outbound → snet-ca only
├── snet-ca    (10.0.2.0/23)  — Container Apps (internal ingress)
│   NSG: inbound 8000 from snet-apim only, deny all else
├── snet-sql   (10.0.4.0/24)  — SQL Private Endpoint
│   NSG: inbound 1433 from snet-ca only, deny all else
└── snet-pe    (10.0.5.0/24)  — Key Vault Private Endpoint
```

Bicep: `infra/core/network.bicep`。enableEnterpriseSecurity=true で VNet + NSG + Private DNS Zone が作られる。

## ID・認証

### APIM Inbound (Foundry → APIM)
```xml
<validate-azure-ad-token tenant-id="{{entra-tenant-id}}"
  header-name="Authorization" failed-validation-httpcode="401"
  output-token-variable-name="jwt">
  <client-application-ids>
    <application-id>{{foundry-agent-app-id}}</application-id>
  </client-application-ids>
  <required-claims>
    <claim name="roles" match="any"><value>MCP.Tools.Read</value></claim>
  </required-claims>
</validate-azure-ad-token>
<rate-limit-by-key calls="60" renewal-period="60"
  counter-key="@(context.Request.Headers.GetValueOrDefault(&quot;Authorization&quot;,&quot;&quot;))" />
```

### Container Apps → SQL (Managed Identity)
`USE_MANAGED_IDENTITY=true` で DefaultAzureCredential + Entra トークン認証に切り替わる。SQL 側で:
```sql
CREATE USER [inventory-api] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [inventory-api];
```

### SQL Server
- `publicNetworkAccess: Disabled`（enterprise mode）
- Private Endpoint 経由のみ
- ローカル認証は将来的に `azureADOnlyAuthentication: true` で無効化

## シークレット管理

| 項目 | デモ (false) | 本番 (true) |
|------|------------|------------|
| SQL 認証 | UID/PWD in env var | Managed Identity（シークレットなし） |
| APIM Subscription Key | Portal から手動 | Key Vault Named Values |
| ACR パスワード | Bicep secrets | ACR の Managed Identity pull に移行推奨 |

Key Vault: `infra/core/keyvault.bicep`。RBAC 認可、soft delete、Private Endpoint。

## 監視・脅威検出

enableEnterpriseSecurity=true で有効化:
- Defender for SQL（異常クエリ検出、SQL インジェクション検出）
- Defender for Containers（ACR イメージ脆弱性スキャン）
- Defender for Key Vault（不正アクセス検出）
- Log Analytics にコンテナログ集約
- APIM → App Insights で全 MCP ツール呼び出しの監査ログ

Bicep: `infra/core/defender.bicep`

## チェックリスト

### ネットワーク
- [ ] VNet + 4 サブネット (`enableEnterpriseSecurity=true`)
- [ ] Container Apps: internal ingress + Private Endpoint
- [ ] SQL: Private Endpoint + publicNetworkAccess=Disabled
- [ ] Key Vault: Private Endpoint + defaultAction=Deny
- [ ] NSG: snet-ca は snet-apim からのみ、snet-sql は snet-ca からのみ
- [ ] Private DNS Zone: SQL + Container Apps

### ID・認証
- [ ] APIM: `validate-azure-ad-token` + required roles
- [ ] APIM: `rate-limit-by-key` per session
- [ ] Container Apps → SQL: Managed Identity (`USE_MANAGED_IDENTITY=true`)
- [ ] SQL: Entra AD ユーザー作成 + db_datareader ロール
- [ ] Foundry publish 後: agent identity に MCP.Tools.Read 割り当て

### シークレット
- [ ] Key Vault に残りのシークレット
- [ ] Container Apps env var からパスワード削除（MI 移行後）

### 監視
- [ ] Defender for SQL / Containers / Key Vault
- [ ] APIM diagnostics: Frontend Response payload bytes = 0
- [ ] APIM audit trace: caller identity + tool name
- [ ] Log Analytics に全ログ集約

### ガバナンス（大規模展開時）
- [ ] Azure Policy（public endpoint 禁止）
- [ ] RBAC 最小権限設計
- [ ] リソースロック（CanNotDelete）
- [ ] タグ戦略（environment, owner, cost-center）

## 切り替え方法

```bash
# デモモード（デフォルト）
azd env set ENABLE_ENTERPRISE_SECURITY false
azd up

# 本番モード
azd env set ENABLE_ENTERPRISE_SECURITY true
azd up
# → VNet, PE, KV, Defender が追加作成される
# → Container Apps が internal ingress に変わる
# → SQL が public access disabled に変わる
```

## 参考
- https://learn.microsoft.com/en-us/azure/well-architected/security/checklist
- https://learn.microsoft.com/en-us/azure/well-architected/security/networking
- https://learn.microsoft.com/en-us/azure/well-architected/security/principles
- https://learn.microsoft.com/en-us/azure/api-management/secure-mcp-servers
- https://learn.microsoft.com/en-us/azure/api-management/validate-azure-ad-token-policy
- https://learn.microsoft.com/en-us/azure/container-apps/how-to-use-private-endpoint
- https://devblogs.microsoft.com/ise/aca-secure-mcp-server-oauth21-azure-ad/
