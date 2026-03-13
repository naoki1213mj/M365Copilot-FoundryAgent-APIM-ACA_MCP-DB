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
RESOURCE_GROUP=$(az group list --query "[?starts_with(name, 'rg-inventory')].name | [0]" -o tsv 2>/dev/null || echo "rg-inventory-demo")
APIM_NAME=$(az apim list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "YOUR_APIM_NAME")
CALLER_APP_IDS_CSV=${APIM_ALLOWED_CLIENT_APP_IDS:-}

CLIENT_APP_IDS_XML=""
if [[ -n "$CALLER_APP_IDS_CSV" ]]; then
  CLIENT_APP_IDS_XML="      <client-application-ids>\n"
  IFS=',' read -ra CALLER_APP_IDS <<< "$CALLER_APP_IDS_CSV"
  for caller_app_id in "${CALLER_APP_IDS[@]}"; do
    trimmed_app_id=$(echo "$caller_app_id" | xargs)
    CLIENT_APP_IDS_XML+="        <application-id>${trimmed_app_id}</application-id>\n"
  done
  CLIENT_APP_IDS_XML+="      </client-application-ids>"
else
  CLIENT_APP_IDS_XML="      <!-- Foundry / Bot publish 後の caller client app id を APIM_ALLOWED_CLIENT_APP_IDS で渡す -->"
fi

cat << POLICY

📋 APIM (${APIM_NAME}) → MCP Servers → Policies に貼り付け:

<policies>
  <inbound>
    <base />
    <validate-azure-ad-token tenant-id="${TENANT_ID}" header-name="Authorization"
      failed-validation-httpcode="401" failed-validation-error-message="Unauthorized"
      output-token-variable-name="jwt">
${CLIENT_APP_IDS_XML}
      <required-claims>
        <claim name="roles" match="any"><value>MCP.Tools.Read</value></claim>
      </required-claims>
    </validate-azure-ad-token>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>

メモ:
- inventory-api app registration: ${APP_ID}
- caller client app ids は inventory-api の APP_ID ではなく、Foundry / Bot publish 後に得られる client app id を使う
- `rate-limit-by-key` は 2026-03-13 時点で MCP API に適用すると HTTP 500 を再現したため、このポリシーには含めない

次の手順:
- Foundry publish 後: agent identity に MCP.Tools.Read ロール割り当て
- IaC を使う場合: azd env set APIM_ALLOWED_CLIENT_APP_IDS "<Foundry/Bot client app ids>" && azd provision
- 手動適用する場合: 先に APIM_ALLOWED_CLIENT_APP_IDS を export してからこのスクリプトを実行

✅ Inventory API App ID: ${APP_ID} / Tenant: ${TENANT_ID}
POLICY
