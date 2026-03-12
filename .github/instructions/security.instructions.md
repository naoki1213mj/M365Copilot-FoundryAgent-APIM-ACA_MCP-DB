---
name: エンタープライズセキュリティ規約
description: APIM + Entra ID + Container Apps のゼロトラスト設計ルール。JWT 検証、rate limiting、audit logging、private endpoint を強制。
applyTo: "scripts/setup-entra.sh,docs/**,**/*policy*"
---
# Enterprise Security Rules
- Auth: Microsoft Entra ID only. No API keys in production.
- APIM inbound: validate-azure-ad-token with explicit tenant-id, client-application-ids, required roles (MCP.Tools.Read).
- Rate limiting: per-session (counter-key from Authorization header), not global.
- Audit: every MCP tool call to App Insights with caller identity + tool name.
- Network: APIM public + outbound VNet integration → Container Apps private endpoint. No public ingress in production.
- DB auth: Managed Identity (DefaultAzureCredential). No connection string secrets.
- Secrets: Azure Key Vault. APIM named values reference KV.
- Never log JWT tokens, connection strings, or PII.
