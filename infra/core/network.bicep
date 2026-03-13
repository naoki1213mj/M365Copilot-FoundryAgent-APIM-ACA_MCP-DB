// Network module: VNet, 4 subnets, NSGs, Private DNS zones
// WAF Zero Trust: segment, filter, encrypt at every boundary

param location string
param tags object
param resourceToken string

var vnetName = 'vnet-${resourceToken}'

// --- VNet ---
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.0.0.0/16'] }
    subnets: [
      {
        name: 'snet-apim'
        properties: {
          addressPrefix: '10.0.1.0/24'
          networkSecurityGroup: { id: nsgApim.id }
            delegations: [
              {
                name: 'apim-outbound'
                properties: {
                  serviceName: 'Microsoft.Web/serverFarms'
                }
              }
            ]
        }
      }
      {
        name: 'snet-ca'
        properties: {
          addressPrefix: '10.0.2.0/23'
          networkSecurityGroup: { id: nsgCa.id }
            delegations: [
              {
                name: 'container-apps-environment'
                properties: {
                  serviceName: 'Microsoft.App/environments'
                }
              }
            ]
        }
      }
      {
        name: 'snet-sql'
        properties: {
          addressPrefix: '10.0.4.0/24'
          networkSecurityGroup: { id: nsgSql.id }
        }
      }
      {
        name: 'snet-pe'
        properties: {
          addressPrefix: '10.0.5.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// --- NSG: APIM subnet ---
resource nsgApim 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-apim-${resourceToken}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAPIMManagement'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'ApiManagement'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '3443'
        }
      }
      {
        name: 'AllowHTTPS'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

// --- NSG: Container Apps subnet ---
// APIM VNet integration からの HTTPS + CA internal 通信 + LB ヘルスプローブを許可
resource nsgCa 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-ca-${resourceToken}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowFromApimSubnet'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.0.1.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.0.2.0/23'
          destinationPortRanges: ['443', '80']
        }
      }
      {
        name: 'AllowAzureLoadBalancer'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'AzureLoadBalancer'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.0.2.0/23'
          destinationPortRange: '30000-32767'
        }
      }
      {
        name: 'AllowCaSubnetInternal'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: '10.0.2.0/23'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.0.2.0/23'
          destinationPortRange: '*'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

// --- NSG: SQL subnet ---
resource nsgSql 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-sql-${resourceToken}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowSqlFromCa'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.0.2.0/23'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.0.4.0/24'
          destinationPortRange: '1433'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

// --- Private DNS Zones ---
resource sqlDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink${environment().suffixes.sqlServerHostname}'
  location: 'global'
  tags: tags

  resource vnetLink 'virtualNetworkLinks' = {
    name: 'sql-vnet-link'
    location: 'global'
    properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
  }
}

resource caDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.${location}.azurecontainerapps.io'
  location: 'global'
  tags: tags

  resource vnetLink 'virtualNetworkLinks' = {
    name: 'ca-vnet-link'
    location: 'global'
    properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
  }
}

resource kvDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags

  resource vnetLink 'virtualNetworkLinks' = {
    name: 'kv-vnet-link'
    location: 'global'
    properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
  }
}

output vnetId string = vnet.id
output apimSubnetId string = vnet.properties.subnets[0].id
output caSubnetId string = vnet.properties.subnets[1].id
output sqlSubnetId string = vnet.properties.subnets[2].id
output peSubnetId string = vnet.properties.subnets[3].id
output sqlDnsZoneId string = sqlDnsZone.id
output caDnsZoneId string = caDnsZone.id
output kvDnsZoneId string = kvDnsZone.id
