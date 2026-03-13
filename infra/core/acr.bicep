param location string
param tags object
param resourceToken string

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acrinv${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

output loginServer string = acr.properties.loginServer
output name string = acr.name
output id string = acr.id
