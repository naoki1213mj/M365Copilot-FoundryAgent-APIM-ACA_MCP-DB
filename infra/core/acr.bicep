param location string
param tags object
param resourceToken string

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

output loginServer string = acr.properties.loginServer
output name string = acr.name
output id string = acr.id
