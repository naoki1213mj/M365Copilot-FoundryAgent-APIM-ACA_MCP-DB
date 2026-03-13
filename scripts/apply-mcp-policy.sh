#!/bin/bash
# MCP API にセキュリティポリシー（JWT 検証 + IP レート制限）を適用する
# MCP API は ARM で作成できないため、azd postprovision hook で実行する
#
# 前提: MCP API (inventory-mcp) が APIM ポータルで手動作成済みであること
# 使い方: ./scripts/apply-mcp-policy.sh <resource-group> <apim-name>

set -euo pipefail

RG="${1:-${AZURE_RESOURCE_GROUP:-}}"
APIM_NAME="${2:-}"

if [ -z "$RG" ] || [ -z "$APIM_NAME" ]; then
  echo "Usage: $0 <resource-group> <apim-name>"
  echo "  or set AZURE_RESOURCE_GROUP env var and pass apim-name"
  exit 1
fi

SUBSCRIPTION=$(az account show --query id -o tsv)
MCP_API_ID="inventory-mcp"
POLICY_FILE="$(dirname "$0")/mcp-policy.json"

API_URL="https://management.azure.com/subscriptions/${SUBSCRIPTION}/resourceGroups/${RG}/providers/Microsoft.ApiManagement/service/${APIM_NAME}/apis/${MCP_API_ID}/policies/policy?api-version=2024-05-01"

# MCP API が存在するか確認
CHECK_URL="https://management.azure.com/subscriptions/${SUBSCRIPTION}/resourceGroups/${RG}/providers/Microsoft.ApiManagement/service/${APIM_NAME}/apis/${MCP_API_ID}?api-version=2024-05-01"

if az rest --method get --url "$CHECK_URL" > /dev/null 2>&1; then
  echo "MCP API '${MCP_API_ID}' が見つかりました。ポリシーを適用します..."
  az rest --method put --url "$API_URL" --headers "Content-Type=application/json" --body "@${POLICY_FILE}"
  echo "ポリシー適用完了: validate-azure-ad-token + rate-limit-by-key (IP, 60/min)"
else
  echo "MCP API '${MCP_API_ID}' が見つかりません。スキップします。"
  echo "  → APIM ポータルで MCP Server を作成後、再実行してください。"
fi
