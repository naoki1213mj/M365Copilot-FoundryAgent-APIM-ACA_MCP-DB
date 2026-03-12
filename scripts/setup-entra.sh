#!/bin/bash
set -euo pipefail
echo "🔒 Entra ID セットアップ..."

APP_ID=$(az ad app create --display-name "inventory-api" --sign-in-audience AzureADMyOrg --query appId -o tsv)
az ad app update --id $APP_ID --identifier-uris "api://${APP_ID}"
ROLE_ID=$(uuidgen)
az ad app update --id $APP_ID --app-roles "[{
  \"allowedMemberTypes\":[\"Application\"],\"displayName\":\"MCP.Tools.Read\",
  \"value\":\"MCP.Tools.Read\",\"description\":\"Read-only inventory MCP tools\",
  \"isEnabled\":true,\"id\":\"${ROLE_ID}\"}]"
az ad sp create --id $APP_ID -o none 2>/dev/null || true
TENANT_ID=$(az account show --query tenantId -o tsv)
APIM_NAME=$(az apim list -g inventory-demo-rg --query "[0].name" -o tsv 2>/dev/null || echo "YOUR_APIM_NAME")

cat << POLICY

📋 APIM → MCP Servers → Policies に貼り付け:

<policies>
  <inbound>
    <base />
    <validate-azure-ad-token tenant-id="${TENANT_ID}" header-name="Authorization"
      failed-validation-httpcode="401" failed-validation-error-message="Unauthorized"
      output-token-variable-name="jwt">
      <client-application-ids>
        <application-id>${APP_ID}</application-id>
      </client-application-ids>
    </validate-azure-ad-token>
    <rate-limit-by-key calls="60" renewal-period="60"
      counter-key="@(context.Request.Headers.GetValueOrDefault(\"Authorization\",\"\"))" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>

🔑 Foundry publish 後: agent identity に MCP.Tools.Read ロール割り当て
✅ App ID: ${APP_ID} / Tenant: ${TENANT_ID}
POLICY
