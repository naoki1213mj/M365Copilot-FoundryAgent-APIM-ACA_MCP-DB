// Container Apps - workload profiles, System Managed Identity
// Enterprise: internal CAE (VNet-scope ingress) + MI for SQL
// internal CAE + external ingress = VNet 内からのみアクセス可能（インターネット非公開）

param location string
param tags object
param resourceToken string
param acrLoginServer string
param acrName string
param acrResourceId string
param enableEnterpriseSecurity bool
param caSubnetId string
param sqlServerFqdn string
param sqlDatabaseName string

var acrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var managedEnvironmentName = enableEnterpriseSecurity ? 'cae-ent-${resourceToken}' : 'cae-${resourceToken}'
var containerAppName = enableEnterpriseSecurity ? 'inventory-api-ent' : 'inventory-api'

// --- Log Analytics ---
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-api-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource acrPullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-acr-pull-${resourceToken}'
  location: location
  tags: tags
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrResourceId, acrPullIdentity.id, 'acr-pull')
  scope: acr
  properties: {
    principalId: acrPullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleDefinitionId
  }
}

// --- Container Apps Environment ---
resource caEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: managedEnvironmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
    vnetConfiguration: !empty(caSubnetId) ? {
      infrastructureSubnetId: caSubnetId
      internal: enableEnterpriseSecurity
    } : null
  }
}

// --- Container App ---
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'inventory-api' })
  identity: {
    type: 'SystemAssigned,UserAssigned'
    userAssignedIdentities: {
      '${acrPullIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: caEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // internal CAE では external: true = VNet scope（インターネット非公開）
        // external: false にすると CA Environment 内からのみとなり APIM から到達不可
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          identity: acrPullIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'inventory-api'
          image: '${acrLoginServer}/inventory-api:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'USE_MANAGED_IDENTITY', value: 'true' }
            { name: 'SQL_SERVER_FQDN', value: sqlServerFqdn }
            { name: 'SQL_DATABASE_NAME', value: sqlDatabaseName }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'OTEL_SERVICE_NAME', value: containerAppName }
            { name: 'LOG_LEVEL', value: 'INFO' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// Reference ACR for credentials
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output principalId string = containerApp.identity.principalId
output envId string = caEnv.id
output name string = containerApp.name
