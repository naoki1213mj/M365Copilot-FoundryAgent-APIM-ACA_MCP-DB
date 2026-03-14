// Foundry (AI Services) account + project + model deployments
// azd up で Foundry リソースも一括デプロイ

param location string
param tags object
param resourceToken string

var accountName = 'foundry-${resourceToken}'

// --- Foundry Account ---
resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: accountName
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
  }
}

// --- Foundry Project ---
// Bicep の projects リソースタイプがエラーになるため、azd postprovision hook で CLI 作成
// az cognitiveservices account project create --name <account> --resource-group <rg> --project-name inventory-project --location japaneast

// --- Model Deployments ---
resource deployGpt41Mini 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: 'gpt-4.1-mini'
  sku: { name: 'GlobalStandard', capacity: 10 }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1-mini'
      version: '2025-04-14'
    }
  }
}

resource deployGpt41 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: 'gpt-4.1'
  sku: { name: 'GlobalStandard', capacity: 10 }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1'
      version: '2025-04-14'
    }
  }
  dependsOn: [deployGpt41Mini]
}

resource deployGpt5Mini 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: 'gpt-5-mini'
  sku: { name: 'GlobalStandard', capacity: 10 }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5-mini'
      version: '2025-08-07'
    }
  }
  dependsOn: [deployGpt41]
}

resource deployGpt52 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: 'gpt-5.2'
  sku: { name: 'GlobalStandard', capacity: 10 }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.2'
      version: '2025-12-11'
    }
  }
  dependsOn: [deployGpt5Mini]
}

output accountName string = foundryAccount.name
output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/inventory-project'
