---
name: インフラ・デプロイ規約
description: azd + Bicep デプロイ、Dockerfile、APIM ポリシー、エンタープライズセキュリティのルール。enableEnterpriseSecurity フラグでデモ/本番を切り替え。
applyTo: "infra/**,azure.yaml,**/Dockerfile,scripts/**"
---
# Infrastructure Rules

- Deployment: azd + Bicep. Region: japaneast.
- `enableEnterpriseSecurity` フラグで 2 モード: false=デモ(public), true=本番(VNet+PE+KV+Defender+MI)
- APIM: Standard v2 minimum. Consumption cannot do MCP or VNet integration.
- Container Apps: workload profiles environment. consumption-only is immutable and has no PE/UDR.
- APIM MCP: diagnostics Frontend Response payload bytes = 0. Never read context.Response.Body.
- Entra ID: validate-azure-ad-token in APIM policy. Not validate-jwt.
- Bicep modules in infra/core/: network, keyvault, sql, acr, container-apps, apim, defender.
- Network (enterprise): VNet 10.0.0.0/16, 4 subnets with NSGs, Private DNS zones.
- SQL (enterprise): Private Endpoint, publicNetworkAccess=Disabled.
- Container Apps (enterprise): internal ingress, VNet integration, Managed Identity for SQL.
- Key Vault (enterprise): RBAC authorization, soft delete, Private Endpoint.
- Defender (enterprise): SQL + Containers + Key Vault.
