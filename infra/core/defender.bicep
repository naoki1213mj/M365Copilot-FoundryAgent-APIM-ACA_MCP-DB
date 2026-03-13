targetScope = 'subscription'

// Microsoft Defender for Cloud: SQL + Containers
// WAF Security Operations: continuous threat detection

// Defender for SQL
resource defenderSql 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'SqlServers'
  properties: { pricingTier: 'Standard' }
}

// Defender for Containers
resource defenderContainers 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'Containers'
  properties: { pricingTier: 'Standard' }
}

// Defender for Key Vault
resource defenderKv 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'KeyVaults'
  properties: { pricingTier: 'Standard' }
}
