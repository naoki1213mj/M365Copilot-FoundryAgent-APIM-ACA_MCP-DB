// APIM Standard v2 - MCP server capable
// Enterprise: outbound VNet integration to reach private Container Apps

param location string
param tags object
param resourceToken string
param enableEnterpriseSecurity bool
param apimSubnetId string
// サービスレベルの JWT / rate-limit は空にする。
// 理由: service scope に validate-azure-ad-token を入れると MCP 内部 tool call が 401 になるため。
// セキュリティポリシー（validate-azure-ad-token + rate-limit-by-key IP 60/min）は
// MCP API スコープに限定して scripts/apply-mcp-policy.sh で適用する。
var authPolicyXml = ''
var rateLimitPolicyXml = ''
var apimPolicy = '<policies><inbound>${authPolicyXml}${rateLimitPolicyXml}</inbound><backend><forward-request /></backend><outbound></outbound><on-error></on-error></policies>'

resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = {
  name: 'apim-${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'StandardV2', capacity: 1 }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherName: 'Inventory Demo'
    publisherEmail: 'demo@example.com'
    virtualNetworkType: enableEnterpriseSecurity && !empty(apimSubnetId) ? 'External' : 'None'
    virtualNetworkConfiguration: enableEnterpriseSecurity && !empty(apimSubnetId) ? {
      subnetResourceId: apimSubnetId
    } : null
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = if (enableEnterpriseSecurity) {
  name: 'appi-apim-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}

resource apimLogger 'Microsoft.ApiManagement/service/loggers@2022-08-01' = if (enableEnterpriseSecurity) {
  parent: apim
  name: 'applicationinsights'
  properties: {
    loggerType: 'applicationInsights'
    description: 'Application Insights logger for APIM gateway diagnostics'
    resourceId: appInsights!.id
    credentials: {
      connectionString: appInsights!.properties.ConnectionString
    }
  }
}

resource apimDiagnostic 'Microsoft.ApiManagement/service/diagnostics@2022-08-01' = if (enableEnterpriseSecurity) {
  parent: apim
  name: 'applicationinsights'
  properties: {
    loggerId: apimLogger.id
    alwaysLog: 'allErrors'
    httpCorrelationProtocol: 'W3C'
    logClientIp: true
    operationNameFormat: 'Url'
    verbosity: 'information'
    sampling: {
      samplingType: 'fixed'
      percentage: 100
    }
    frontend: {
      request: {
        headers: [
          'User-Agent'
          'x-request-id'
        ]
      }
      response: {
        headers: [
          'Content-Type'
        ]
        body: {
          bytes: 0
        }
      }
    }
    backend: {
      request: {
        headers: [
          'User-Agent'
        ]
      }
      response: {
        headers: [
          'Content-Type'
        ]
        body: {
          bytes: 0
        }
      }
    }
    metrics: true
  }
}

resource apimPolicyResource 'Microsoft.ApiManagement/service/policies@2022-08-01' = {
  parent: apim
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: apimPolicy
  }
}

output gatewayUrl string = apim.properties.gatewayUrl
output name string = apim.name
output id string = apim.id
