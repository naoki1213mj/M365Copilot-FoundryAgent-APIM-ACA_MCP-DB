// Azure SQL Database - Basic with Entra ID Only auth + optional Private Endpoint

param location string
param tags object
param resourceToken string
param entraAdminObjectId string
param entraAdminDisplayName string = 'SQL Admin'
param enableEnterpriseSecurity bool
param subnetId string
param privateDnsZoneId string

var serverName = 'sql-${resourceToken}'

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: serverName
  location: location
  tags: tags
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: enableEnterpriseSecurity ? 'Disabled' : 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      login: entraAdminDisplayName
      sid: entraAdminObjectId
      tenantId: subscription().tenantId
      azureADOnlyAuthentication: true
      principalType: 'User'
    }
  }
}

// Allow Azure services (demo only, disabled in enterprise mode)
resource firewallRule 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (!enableEnterpriseSecurity) {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource database 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'inventory_db'
  location: location
  tags: tags
  sku: { name: 'Basic', tier: 'Basic' }
}

// Private Endpoint (enterprise only)
resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = if (enableEnterpriseSecurity && !empty(subnetId)) {
  name: 'pe-sql-${resourceToken}'
  location: location
  tags: tags
  properties: {
    subnet: { id: subnetId }
    privateLinkServiceConnections: [
      {
        name: 'sql-connection'
        properties: {
          privateLinkServiceId: sqlServer.id
          groupIds: ['sqlServer']
        }
      }
    ]
  }
}

resource peDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (enableEnterpriseSecurity && !empty(subnetId) && !empty(privateDnsZoneId)) {
  parent: pe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'sql-zone'
        properties: {
          privateDnsZoneId: privateDnsZoneId
        }
      }
    ]
  }
}

output serverFqdn string = sqlServer.properties.fullyQualifiedDomainName
output databaseName string = database.name
output serverId string = sqlServer.id
