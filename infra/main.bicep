targetScope = 'subscription'

@description('Environment name')
param environmentName string

@description('Primary location')
param location string = 'japaneast'

@description('Current user principal ID')
param principalId string

@description('Enable enterprise security (VNet, PE, KV, Defender, Managed ID)')
param enableEnterpriseSecurity bool = false

var resourceToken = uniqueString(subscription().id, environmentName, location)
var tags = { 'azd-env-name': environmentName, project: 'inventory-api' }

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// --- Network (enterprise only) ---
module network 'core/network.bicep' = if (enableEnterpriseSecurity) {
  scope: rg
  name: 'network'
  params: { location: location, tags: tags, resourceToken: resourceToken }
}

// --- Key Vault (enterprise only) ---
module keyVault 'core/keyvault.bicep' = if (enableEnterpriseSecurity) {
  scope: rg
  name: 'keyvault'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: principalId
    subnetId: network!.outputs.peSubnetId
    privateDnsZoneId: network!.outputs.kvDnsZoneId
  }
}

// --- SQL ---
module sql 'core/sql.bicep' = {
  scope: rg
  name: 'sql'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    entraAdminObjectId: principalId
    entraAdminDisplayName: 'SQL Admin'
    enableEnterpriseSecurity: enableEnterpriseSecurity
    subnetId: enableEnterpriseSecurity ? network!.outputs.sqlSubnetId : ''
    privateDnsZoneId: enableEnterpriseSecurity ? network!.outputs.sqlDnsZoneId : ''
  }
}

// --- ACR ---
module acr 'core/acr.bicep' = {
  scope: rg
  name: 'acr'
  params: { location: location, tags: tags, resourceToken: resourceToken }
}

// --- Container Apps ---
module containerApps 'core/container-apps.bicep' = {
  scope: rg
  name: 'container-apps'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    acrLoginServer: acr.outputs.loginServer
    acrName: acr.outputs.name
    acrResourceId: acr.outputs.id
    enableEnterpriseSecurity: enableEnterpriseSecurity
    caSubnetId: enableEnterpriseSecurity ? network!.outputs.caSubnetId : ''
    sqlServerFqdn: sql.outputs.serverFqdn
    sqlDatabaseName: sql.outputs.databaseName
  }
}

// --- APIM ---
module apim 'core/apim.bicep' = {
  scope: rg
  name: 'apim'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    enableEnterpriseSecurity: enableEnterpriseSecurity
    apimSubnetId: enableEnterpriseSecurity ? network!.outputs.apimSubnetId : ''
  }
}

// --- Defender (enterprise only) ---
module defender 'core/defender.bicep' = if (enableEnterpriseSecurity) {
  name: 'defender'
}

// --- Foundry (AI Services) ---
module foundry 'core/foundry.bicep' = {
  scope: rg
  name: 'foundry'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
  }
}

// --- Outputs ---
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_APPS_FQDN string = containerApps.outputs.fqdn
output AZURE_APIM_GATEWAY_URL string = apim.outputs.gatewayUrl
output AZURE_SQL_SERVER string = sql.outputs.serverFqdn
output AZURE_SQL_DATABASE string = sql.outputs.databaseName
output AZURE_ACR_LOGIN_SERVER string = acr.outputs.loginServer
output AZURE_KEYVAULT_URI string = enableEnterpriseSecurity ? keyVault!.outputs.vaultUri : ''
output ENABLE_ENTERPRISE_SECURITY bool = enableEnterpriseSecurity
output FOUNDRY_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
