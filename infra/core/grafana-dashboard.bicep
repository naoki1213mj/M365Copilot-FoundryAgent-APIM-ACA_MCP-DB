// Azure Monitor dashboards with Grafana (enterprise only)
// ※ Azure Managed Grafana ではない。Azure ポータル組み込みの無料 Grafana ダッシュボード。
// リソースタイプ: Microsoft.Dashboard/dashboards
//
// Bicep で空のダッシュボードリソースを作成し、
// postprovision で Grafana data plane API を使ってパネルを投入する。
// 参考: https://learn.microsoft.com/azure/azure-monitor/visualize/visualize-grafana-overview

param location string
param tags object
param resourceToken string

// --- API 概要ダッシュボード ---
resource apiOverviewDashboard 'Microsoft.Dashboard/dashboards@2025-08-01' = {
  name: 'gd-api-overview-${resourceToken}'
  location: location
  tags: union(tags, {
    GrafanaDashboardResourceType: 'microsoft.insights/components'
    GrafanaDashboardTags: 'inventory-api,monitoring'
  })
  properties: {}
}

// --- 在庫アラート専用ダッシュボード ---
resource alertsDashboard 'Microsoft.Dashboard/dashboards@2025-08-01' = {
  name: 'gd-alerts-${resourceToken}'
  location: location
  tags: union(tags, {
    GrafanaDashboardResourceType: 'microsoft.insights/components'
    GrafanaDashboardTags: 'inventory-api,alerts'
  })
  properties: {}
}

output apiOverviewDashboardName string = apiOverviewDashboard.name
output alertsDashboardName string = alertsDashboard.name
