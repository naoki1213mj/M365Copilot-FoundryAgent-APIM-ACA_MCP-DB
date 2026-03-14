<#
.SYNOPSIS
    デプロイ後スモークテスト
.DESCRIPTION
    azd up 後に実行し、主要リソースの正常性を確認する。
    リソースグループ内のリソース存在確認 + API ヘルスチェック + APIM API 存在確認。
.EXAMPLE
    ./scripts/smoke_test.ps1 -ResourceGroup rg-inventory-demo
#>
param(
    [string]$ResourceGroup = $env:AZURE_RESOURCE_GROUP
)

$ErrorActionPreference = "Continue"
$pass = 0; $fail = 0; $warn = 0

function Test-Check {
    param([string]$Name, [scriptblock]$Check)
    try {
        $result = & $Check
        if ($result) {
            Write-Host "  [PASS] $Name" -ForegroundColor Green
            $script:pass++
        } else {
            Write-Host "  [FAIL] $Name" -ForegroundColor Red
            $script:fail++
        }
    } catch {
        Write-Host "  [FAIL] $Name - $($_.Exception.Message)" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "`n=== Smoke Test: $ResourceGroup ===" -ForegroundColor Cyan

# 1. リソースグループ存在確認
Test-Check "Resource Group" {
    $null -ne (az group show -n $ResourceGroup -o json 2>$null | ConvertFrom-Json)
}

# 2. 主要リソース存在確認
$resourceTypes = @(
    @{ Type = "Microsoft.Sql/servers"; Display = "SQL Server" },
    @{ Type = "Microsoft.ContainerRegistry/registries"; Display = "ACR" },
    @{ Type = "Microsoft.App/managedEnvironments"; Display = "CA Environment" },
    @{ Type = "Microsoft.App/containerApps"; Display = "Container App" },
    @{ Type = "Microsoft.ApiManagement/service"; Display = "APIM" },
    @{ Type = "Microsoft.CognitiveServices/accounts"; Display = "AI Foundry" }
)

foreach ($rt in $resourceTypes) {
    Test-Check $rt.Display {
        $resources = az resource list -g $ResourceGroup --resource-type $rt.Type --query "[].name" -o tsv 2>$null
        -not [string]::IsNullOrWhiteSpace($resources)
    }
}

# 3. Container App ヘルスチェック
$caFqdn = az containerapp list -g $ResourceGroup --query "[0].properties.configuration.ingress.fqdn" -o tsv 2>$null
if ($caFqdn) {
    Test-Check "Health Endpoint" {
        try {
            $resp = Invoke-RestMethod -Uri "https://$caFqdn/health" -TimeoutSec 10
            $resp.status -eq "healthy"
        } catch { $false }
    }
} else {
    Write-Host "  [WARN] Container App FQDN not found" -ForegroundColor Yellow
    $warn++
}

# 4. APIM API 存在確認
$apimName = az resource list -g $ResourceGroup --resource-type "Microsoft.ApiManagement/service" --query "[0].name" -o tsv 2>$null
if ($apimName) {
    $sub = az account show --query id -o tsv
    Test-Check "APIM Inventory API" {
        $apiUrl = "https://management.azure.com/subscriptions/$sub/resourceGroups/$ResourceGroup/providers/Microsoft.ApiManagement/service/$apimName/apis/inventory-api?api-version=2024-05-01"
        $null -ne (az rest --method get --url $apiUrl --query name -o tsv 2>$null)
    }
}

# サマリ
Write-Host "`n=== Results ===" -ForegroundColor Cyan
Write-Host "  PASS: $pass  FAIL: $fail  WARN: $warn"
if ($fail -gt 0) {
    Write-Host "  Some checks FAILED." -ForegroundColor Red
    exit 1
} else {
    Write-Host "  All checks passed." -ForegroundColor Green
}
