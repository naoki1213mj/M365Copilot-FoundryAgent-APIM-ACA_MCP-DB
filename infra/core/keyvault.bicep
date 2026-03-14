// Key Vault with RBAC authorization, soft delete, Private Endpoint

param location string
param tags object
param resourceToken string
param principalId string
param subnetId string
param privateDnsZoneId string

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: !empty(subnetId) ? 'Disabled' : 'Enabled'
    networkAcls: !empty(subnetId) ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    } : {
      defaultAction: 'Allow'
    }
  }
}

// Grant current user Key Vault Secrets Officer
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, principalId, '4633458b-17de-408a-b874-0445c86b69e6')
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// Private Endpoint (enterprise only)
resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = if (!empty(subnetId)) {
  name: 'pe-kv-${resourceToken}'
  location: location
  tags: tags
  properties: {
    subnet: { id: subnetId }
    privateLinkServiceConnections: [
      {
        name: 'kv-connection'
        properties: {
          privateLinkServiceId: kv.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource peDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (!empty(subnetId) && !empty(privateDnsZoneId)) {
  parent: pe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'kv-zone'
        properties: {
          privateDnsZoneId: privateDnsZoneId
        }
      }
    ]
  }
}

// Secrets
param appInsightsConnectionString string = ''

resource secretAppInsights 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(appInsightsConnectionString)) {
  parent: kv
  name: 'appinsights-connection-string'
  properties: {
    value: appInsightsConnectionString
  }
}

// Diagnostic Settings
param logAnalyticsId string = ''

resource kvDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsId)) {
  scope: kv
  name: 'kv-diagnostics'
  properties: {
    workspaceId: logAnalyticsId
    logs: [
      { categoryGroup: 'audit', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

output vaultUri string = kv.properties.vaultUri
output vaultName string = kv.name
output vaultId string = kv.id
