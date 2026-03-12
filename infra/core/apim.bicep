// APIM Standard v2 - MCP server capable
// Enterprise: outbound VNet integration to reach private Container Apps

param location string
param tags object
param resourceToken string
param enableEnterpriseSecurity bool
param apimSubnetId string

resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = {
  name: 'apim-${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'StandardV2', capacity: 1 }
  properties: {
    publisherName: 'Inventory Demo'
    publisherEmail: 'demo@example.com'
    virtualNetworkType: enableEnterpriseSecurity && !empty(apimSubnetId) ? 'External' : 'None'
    virtualNetworkConfiguration: enableEnterpriseSecurity && !empty(apimSubnetId) ? {
      subnetResourceId: apimSubnetId
    } : null
  }
}

output gatewayUrl string = apim.properties.gatewayUrl
output name string = apim.name
output id string = apim.id
