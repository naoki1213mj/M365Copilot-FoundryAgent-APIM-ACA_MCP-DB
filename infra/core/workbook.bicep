// Azure Workbook（enterprise only）
// インタラクティブな KQL レポート。パラメータで時間範囲・エンドポイント絞り込みが可能。
// Microsoft.Insights/workbooks は Bicep で自動プロビジョニング可能（無料）。

param location string
param tags object
param resourceToken string
param appInsightsId string

var workbookId = guid('workbook-inventory-api', resourceToken)

resource workbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: workbookId
  location: location
  tags: union(tags, {
    'hidden-title': '在庫 API 分析レポート'
  })
  kind: 'shared'
  properties: {
    displayName: '在庫 API 分析レポート'
    category: 'workbook'
    sourceId: appInsightsId
    serializedData: serializedWorkbook
  }
}

// Workbook JSON（パラメータ + 8 ステップ）
var serializedWorkbook = string({
  version: 'Notebook/1.0'
  items: [
    // --- パラメータ: 時間範囲 ---
    {
      type: 9
      content: {
        version: 'KqlParameterItem/1.0'
        parameters: [
          {
            id: guid('param-timerange', resourceToken)
            version: 'KqlParameterItem/1.0'
            name: 'TimeRange'
            type: 4
            isRequired: true
            value: { durationMs: 21600000 } // 6h
            typeSettings: {
              selectableValues: [
                { durationMs: 3600000, displayName: '1 時間' }
                { durationMs: 21600000, displayName: '6 時間' }
                { durationMs: 86400000, displayName: '24 時間' }
                { durationMs: 604800000, displayName: '7 日間' }
              ]
            }
            label: '時間範囲'
          }
        ]
      }
      name: 'parameters'
    }
    // --- 概要メトリクス ---
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'requests | where timestamp {TimeRange} | summarize total=count(), errors=countif(toint(resultCode) >= 500), p50=round(percentile(duration, 50), 0), p95=round(percentile(duration, 95), 0), p99=round(percentile(duration, 99), 0) | extend error_rate=round(todouble(errors)/todouble(total)*100, 2)'
        size: 4
        title: '概要メトリクス'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'tiles'
        tileSettings: {
          titleContent: { columnMatch: 'total', formatter: 12 }
          showBorder: true
        }
      }
      name: 'overview-metrics'
    }
    // --- リクエスト数 (時系列) ---
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'requests | where timestamp {TimeRange} | summarize count() by bin(timestamp, 5m), name | order by timestamp asc'
        size: 0
        title: 'リクエスト数 (5分間隔)'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'timechart'
      }
      name: 'request-count'
    }
    // --- エンドポイント別リクエスト ---
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'requests | where timestamp {TimeRange} | summarize count() by name | order by count_ desc'
        size: 2
        title: 'エンドポイント別リクエスト'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'piechart'
      }
      name: 'endpoint-distribution'
    }
    // --- レイテンシ分布 ---
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'requests | where timestamp {TimeRange} | summarize p50=percentile(duration, 50), p95=percentile(duration, 95), p99=percentile(duration, 99) by bin(timestamp, 5m)'
        size: 0
        title: 'レイテンシ分布 P50/P95/P99 (ms)'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'timechart'
      }
      name: 'latency-distribution'
    }
    // --- ステータスコード分布 ---
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'requests | where timestamp {TimeRange} | summarize count() by bin(timestamp, 5m), resultCode | order by timestamp asc'
        size: 0
        title: 'ステータスコード分布'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'timechart'
      }
      name: 'status-code-distribution'
    }
    // --- 5xx エラー一覧 ---
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'requests | where timestamp {TimeRange} | where toint(resultCode) >= 500 | project timestamp, name, resultCode, duration | order by timestamp desc | take 50'
        size: 0
        title: '5xx エラー一覧'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'table'
        gridSettings: {
          sortBy: [ { itemKey: 'timestamp', sortOrder: 2 } ]
        }
      }
      name: 'error-list'
    }
    // --- 例外発生数 ---
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'exceptions | where timestamp {TimeRange} | summarize count() by bin(timestamp, 5m), type | order by timestamp asc'
        size: 0
        title: '例外発生数'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'timechart'
      }
      name: 'exception-count'
    }
  ]
})

output workbookName string = workbook.properties.displayName
