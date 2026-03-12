// Container Apps - workload profiles, System Managed Identity
// Enterprise: internal ingress + VNet integration + MI for SQL

param location string
param tags object
param resourceToken string
param acrLoginServer string
param acrName string
param enableEnterpriseSecurity bool
param caSubnetId string
param sqlServerFqdn string
param sqlDatabaseName string

// --- Log Analytics ---
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

// --- Container Apps Environment ---
resource caEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${resourceToken}'
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
  name: 'inventory-api'
  location: location
  tags: union(tags, { 'azd-service-name': 'inventory-api' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: caEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: !enableEnterpriseSecurity
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          username: acrName
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
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
