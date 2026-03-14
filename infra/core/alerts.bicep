// KQL アラートルール (enterprise only)
// 1. API エラー率 > 5%
// 2. APIM P95 レイテンシ > 5秒
// 3. SQL CPU > 80%
// 4. Container App リスタート検知
// 5. APIM 認証失敗 (401) スパイク

param location string
param tags object
param resourceToken string
param logAnalyticsId string
param appInsightsId string
param sqlDatabaseId string
param alertEmailAddress string = ''

// --- Action Group ---
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (!empty(alertEmailAddress)) {
  name: 'ag-ops-${resourceToken}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'OpsAlert'
    enabled: true
    emailReceivers: [
      {
        name: 'ops-email'
        emailAddress: alertEmailAddress
        useCommonAlertSchema: true
      }
    ]
  }
}

// --- Alert 1: API エラー率 > 5% ---
resource errorRateAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-api-error-rate-${resourceToken}'
  location: location
  tags: tags
  properties: {
    displayName: 'API エラー率 > 5%'
    description: 'Container Apps API の 5xx エラー率が 5% を超えた場合に発報'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [appInsightsId]
    criteria: {
      allOf: [
        {
          query: '''
            requests
            | where timestamp > ago(15m)
            | summarize total = count(), errors = countif(resultCode startswith "5")
            | extend error_rate = todouble(errors) / todouble(total) * 100
            | where error_rate > 5
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: {
      actionGroups: !empty(alertEmailAddress) ? [actionGroup.id] : []
    }
  }
}

// --- Alert 2: APIM レイテンシ P95 > 5秒 ---
resource latencyAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-apim-latency-${resourceToken}'
  location: location
  tags: tags
  properties: {
    displayName: 'APIM P95 レイテンシ > 5秒'
    description: 'APIM ゲートウェイの P95 レイテンシが 5 秒を超えた場合に発報'
    severity: 3
    enabled: true
    skipQueryValidation: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [logAnalyticsId]
    criteria: {
      allOf: [
        {
          query: '''
            AzureDiagnostics
            | where Category == "GatewayLogs"
            | where TimeGenerated > ago(15m)
            | summarize p95 = percentile(todouble(totalTime_d), 95)
            | where p95 > 5000
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: {
      actionGroups: !empty(alertEmailAddress) ? [actionGroup.id] : []
    }
  }
}

// --- Alert 3: SQL CPU > 80% ---
resource sqlCpuAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-sql-cpu-${resourceToken}'
  location: 'global'
  tags: tags
  properties: {
    description: 'SQL Database の CPU 使用率が 80% を超えた場合に発報'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [sqlDatabaseId]
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighCPU'
          metricName: 'cpu_percent'
          operator: 'GreaterThan'
          threshold: 80
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: !empty(alertEmailAddress) ? [{ actionGroupId: actionGroup.id }] : []
  }
}

// --- Alert 4: Container App リスタート検知 ---
resource restartAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-ca-restart-${resourceToken}'
  location: location
  tags: tags
  properties: {
    displayName: 'Container App リスタート検知'
    description: 'Container App のレプリカが 15 分間に 3 回以上リスタートした場合に発報'
    severity: 2
    enabled: true
    skipQueryValidation: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [logAnalyticsId]
    criteria: {
      allOf: [
        {
          query: '''
            ContainerAppSystemLogs_CL
            | where TimeGenerated > ago(15m)
            | where Reason_s == "BackOff" or Reason_s == "CrashLoopBackOff" or Reason_s == "Unhealthy"
            | summarize restart_count = count()
            | where restart_count >= 3
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: {
      actionGroups: !empty(alertEmailAddress) ? [actionGroup.id] : []
    }
  }
}

// --- Alert 5: APIM 認証失敗 (401) スパイク ---
resource authFailureAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-apim-auth-failure-${resourceToken}'
  location: location
  tags: tags
  properties: {
    displayName: 'APIM 認証失敗スパイク'
    description: '15 分間に認証失敗 (401) が 20 件を超えた場合に発報。ブルートフォース攻撃の兆候。'
    severity: 2
    enabled: true
    skipQueryValidation: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [logAnalyticsId]
    criteria: {
      allOf: [
        {
          query: '''
            AzureDiagnostics
            | where Category == "GatewayLogs"
            | where TimeGenerated > ago(15m)
            | where responseCode_d == 401
            | summarize auth_failures = count()
            | where auth_failures > 20
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: {
      actionGroups: !empty(alertEmailAddress) ? [actionGroup.id] : []
    }
  }
}
