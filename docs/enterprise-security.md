# セキュリティギャップ分析（WAF/CAF Zero Trust 準拠）

## enableEnterpriseSecurity パラメータ

Bicep に `enableEnterpriseSecurity` フラグを導入。デモと本番でインフラを切り替える。

| 領域 | false（デモ） | true（本番） |
|------|-------------|-------------|
| ネットワーク | 全リソース public | VNet + PE + NSG |
| SQL 認証 | UID/PWD | Managed Identity |
| Container Apps | external ingress | internal ingress |
| SQL public access | Allow Azure Services | Disabled |
| Key Vault | なし | PE + RBAC + soft delete |
| Defender | なし | SQL + Containers + KV |
| APIM VNet | なし | outbound VNet integration |

## アプリコードの変更

`USE_MANAGED_IDENTITY` 環境変数で切り替え。main.py の `get_db()` が DefaultAzureCredential + Entra トークンを使う。

## 顧客への説明

「`enableEnterpriseSecurity=true` に切り替えるだけで、ネットワーク分離・Managed Identity・Key Vault・Defender が全部入ります。アプリコードは同じです。」
