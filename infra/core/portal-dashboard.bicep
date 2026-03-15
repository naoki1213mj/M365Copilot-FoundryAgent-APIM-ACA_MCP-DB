// Azure Portal ダッシュボード（enterprise only）
// KQL クエリを埋め込んだ可視化パネルを Bicep で自動プロビジョニング。
// Microsoft.Portal/dashboards は ARM API で完全自動化可能（無料）。
// メタデータの型が Bicep 型定義と一致しないため any() でラップ。

param tags object
param appInsightsId string

var dashboardName = 'dash-inventory-api'

// KQL パネルの共通メタデータを生成する関数的な変数
var logsPart = 'Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart'

resource dashboard 'Microsoft.Portal/dashboards@2020-09-01-preview' = {
  name: dashboardName
  location: 'global'
  tags: union(tags, {
    'hidden-title': '在庫 API モニタリング'
  })
  properties: {
    lenses: any([
      {
        order: 0
        parts: [
          {
            position: { x: 0, y: 0, colSpan: 6, rowSpan: 4 }
            metadata: {
              type: logsPart
              inputs: [
                { name: 'resourceTypeMode', value: 'components' }
                { name: 'ComponentId', value: appInsightsId }
              ]
              settings: {
                content: {
                  Query: 'requests | where timestamp > ago(6h) | summarize count() by bin(timestamp, 5m), name | order by timestamp asc'
                  PartTitle: 'リクエスト数 (5分間隔)'
                  VisualizationType: 'linechart'
                }
              }
            }
          }
          {
            position: { x: 6, y: 0, colSpan: 3, rowSpan: 4 }
            metadata: {
              type: logsPart
              inputs: [
                { name: 'resourceTypeMode', value: 'components' }
                { name: 'ComponentId', value: appInsightsId }
              ]
              settings: {
                content: {
                  Query: 'requests | where timestamp > ago(1h) | summarize total=count(), errors=countif(toint(resultCode) >= 500) | extend error_rate=round(todouble(errors)/todouble(total)*100, 2) | project error_rate'
                  PartTitle: 'エラー率 (%)'
                  VisualizationType: 'table'
                }
              }
            }
          }
          {
            position: { x: 9, y: 0, colSpan: 3, rowSpan: 4 }
            metadata: {
              type: logsPart
              inputs: [
                { name: 'resourceTypeMode', value: 'components' }
                { name: 'ComponentId', value: appInsightsId }
              ]
              settings: {
                content: {
                  Query: 'requests | where timestamp > ago(1h) | summarize p50=round(percentile(duration, 50), 0), p95=round(percentile(duration, 95), 0), p99=round(percentile(duration, 99), 0)'
                  PartTitle: 'レイテンシ P50/P95/P99 (ms)'
                  VisualizationType: 'table'
                }
              }
            }
          }
          {
            position: { x: 0, y: 4, colSpan: 6, rowSpan: 4 }
            metadata: {
              type: logsPart
              inputs: [
                { name: 'resourceTypeMode', value: 'components' }
                { name: 'ComponentId', value: appInsightsId }
              ]
              settings: {
                content: {
                  Query: 'requests | where timestamp > ago(6h) | summarize count() by name | order by count_ desc'
                  PartTitle: 'エンドポイント別リクエスト'
                  VisualizationType: 'piechart'
                }
              }
            }
          }
          {
            position: { x: 6, y: 4, colSpan: 6, rowSpan: 4 }
            metadata: {
              type: logsPart
              inputs: [
                { name: 'resourceTypeMode', value: 'components' }
                { name: 'ComponentId', value: appInsightsId }
              ]
              settings: {
                content: {
                  Query: 'requests | where timestamp > ago(6h) | summarize p50=percentile(duration,50), p95=percentile(duration,95), p99=percentile(duration,99) by bin(timestamp, 5m)'
                  PartTitle: 'レイテンシ分布 P50/P95/P99'
                  VisualizationType: 'linechart'
                }
              }
            }
          }
          {
            position: { x: 0, y: 8, colSpan: 12, rowSpan: 4 }
            metadata: {
              type: logsPart
              inputs: [
                { name: 'resourceTypeMode', value: 'components' }
                { name: 'ComponentId', value: appInsightsId }
              ]
              settings: {
                content: {
                  Query: 'requests | where timestamp > ago(24h) | where toint(resultCode) >= 500 | project timestamp, name, resultCode, duration | order by timestamp desc | take 20'
                  PartTitle: '直近の 5xx エラー (24h)'
                  VisualizationType: 'table'
                }
              }
            }
          }
          {
            position: { x: 0, y: 12, colSpan: 6, rowSpan: 4 }
            metadata: {
              type: logsPart
              inputs: [
                { name: 'resourceTypeMode', value: 'components' }
                { name: 'ComponentId', value: appInsightsId }
              ]
              settings: {
                content: {
                  Query: 'requests | where timestamp > ago(6h) | summarize count() by bin(timestamp, 5m), resultCode | order by timestamp asc'
                  PartTitle: 'ステータスコード分布'
                  VisualizationType: 'linechart'
                }
              }
            }
          }
          {
            position: { x: 6, y: 12, colSpan: 6, rowSpan: 4 }
            metadata: {
              type: logsPart
              inputs: [
                { name: 'resourceTypeMode', value: 'components' }
                { name: 'ComponentId', value: appInsightsId }
              ]
              settings: {
                content: {
                  Query: 'exceptions | where timestamp > ago(6h) | summarize count() by bin(timestamp, 5m), type | order by timestamp asc'
                  PartTitle: '例外発生数'
                  VisualizationType: 'linechart'
                }
              }
            }
          }
        ]
      }
    ])
  }
}

output dashboardName string = dashboard.name
