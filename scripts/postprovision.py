"""azd postprovision: 全セットアップの自動化スクリプト

azd up 後に実行され、以下を自動化する:
1. Foundry project 作成（Bicep で未対応のため CLI）
2. Private DNS Zone 作成（internal CAE 用）
3. SQL データ投入 + MI ユーザー権限付与
4. APIM REST API import
5. Foundry project connection 作成（PMI 認証）
6. MCP policy 適用（MCP Server 存在時のみ）
7. Foundry agent 作成
8. Agent Application publish
9. Grafana Dashboard パネル投入 (enterprise only)
"""

import json
import os
import subprocess
import sys


def run(cmd: str, check: bool = True) -> str:
    """コマンドを実行して stdout を返す。"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  WARN: {cmd[:80]}... -> exit {result.returncode}")
        if result.stderr:
            print(f"  {result.stderr[:200]}")
        return ""
    return result.stdout.strip()


def run_ok(cmd: str) -> bool:
    """コマンドが成功したか。"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0


def _build_api_overview_dashboard(app_insights_id: str) -> dict:
    """API 概要 Grafana ダッシュボード JSON を構築する。"""
    return {
        "title": "在庫 API 概要",
        "uid": "inventory-api-overview",
        "timezone": "browser",
        "refresh": "30s",
        "panels": [
            {
                "id": 1,
                "type": "timeseries",
                "title": "リクエスト数 (5分間隔)",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                "datasource": {"type": "grafana-azure-monitor-datasource", "uid": "azure-monitor"},
                "targets": [
                    {
                        "queryType": "Azure Log Analytics",
                        "azureLogAnalytics": {
                            "query": "requests | where timestamp > ago(6h) | summarize count() by bin(timestamp, 5m), name | order by timestamp asc",
                            "resources": [app_insights_id],
                        },
                    }
                ],
            },
            {
                "id": 2,
                "type": "gauge",
                "title": "エラー率 (%)",
                "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0},
                "datasource": {"type": "grafana-azure-monitor-datasource", "uid": "azure-monitor"},
                "targets": [
                    {
                        "queryType": "Azure Log Analytics",
                        "azureLogAnalytics": {
                            "query": "requests | where timestamp > ago(1h) | summarize total=count(), errors=countif(resultCode startswith '5') | extend error_rate=todouble(errors)/todouble(total)*100 | project error_rate",
                            "resources": [app_insights_id],
                        },
                    }
                ],
            },
            {
                "id": 3,
                "type": "stat",
                "title": "P95 レイテンシ (ms)",
                "gridPos": {"h": 8, "w": 6, "x": 18, "y": 0},
                "datasource": {"type": "grafana-azure-monitor-datasource", "uid": "azure-monitor"},
                "targets": [
                    {
                        "queryType": "Azure Log Analytics",
                        "azureLogAnalytics": {
                            "query": "requests | where timestamp > ago(1h) | summarize p95=percentile(duration, 95)",
                            "resources": [app_insights_id],
                        },
                    }
                ],
            },
            {
                "id": 4,
                "type": "timeseries",
                "title": "レイテンシ分布 P50/P95/P99",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
                "datasource": {"type": "grafana-azure-monitor-datasource", "uid": "azure-monitor"},
                "targets": [
                    {
                        "queryType": "Azure Log Analytics",
                        "azureLogAnalytics": {
                            "query": "requests | where timestamp > ago(6h) | summarize p50=percentile(duration,50), p95=percentile(duration,95), p99=percentile(duration,99) by bin(timestamp, 5m)",
                            "resources": [app_insights_id],
                        },
                    }
                ],
            },
            {
                "id": 5,
                "type": "piechart",
                "title": "エンドポイント別リクエスト",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
                "datasource": {"type": "grafana-azure-monitor-datasource", "uid": "azure-monitor"},
                "targets": [
                    {
                        "queryType": "Azure Log Analytics",
                        "azureLogAnalytics": {
                            "query": "requests | where timestamp > ago(6h) | summarize count() by name | order by count_ desc",
                            "resources": [app_insights_id],
                        },
                    }
                ],
            },
        ],
    }


def _build_alerts_dashboard(app_insights_id: str) -> dict:
    """在庫アラート Grafana ダッシュボード JSON を構築する。"""
    return {
        "title": "在庫 API アラート",
        "uid": "inventory-api-alerts",
        "timezone": "browser",
        "refresh": "1m",
        "panels": [
            {
                "id": 1,
                "type": "table",
                "title": "直近の 5xx エラー",
                "gridPos": {"h": 10, "w": 24, "x": 0, "y": 0},
                "datasource": {"type": "grafana-azure-monitor-datasource", "uid": "azure-monitor"},
                "targets": [
                    {
                        "queryType": "Azure Log Analytics",
                        "azureLogAnalytics": {
                            "query": "requests | where timestamp > ago(24h) | where toint(resultCode) >= 500 | project timestamp, name, resultCode, duration, client_IP | order by timestamp desc | take 50",
                            "resources": [app_insights_id],
                        },
                    }
                ],
            },
            {
                "id": 2,
                "type": "timeseries",
                "title": "ステータスコード分布 (1時間)",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 10},
                "datasource": {"type": "grafana-azure-monitor-datasource", "uid": "azure-monitor"},
                "targets": [
                    {
                        "queryType": "Azure Log Analytics",
                        "azureLogAnalytics": {
                            "query": "requests | where timestamp > ago(6h) | summarize count() by bin(timestamp, 5m), resultCode | order by timestamp asc",
                            "resources": [app_insights_id],
                        },
                    }
                ],
            },
            {
                "id": 3,
                "type": "timeseries",
                "title": "例外発生数",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 10},
                "datasource": {"type": "grafana-azure-monitor-datasource", "uid": "azure-monitor"},
                "targets": [
                    {
                        "queryType": "Azure Log Analytics",
                        "azureLogAnalytics": {
                            "query": "exceptions | where timestamp > ago(6h) | summarize count() by bin(timestamp, 5m), type | order by timestamp asc",
                            "resources": [app_insights_id],
                        },
                    }
                ],
            },
        ],
    }


def main() -> None:
    rg = os.environ.get("AZURE_RESOURCE_GROUP", "rg-inventory-demo")
    location = os.environ.get("AZURE_LOCATION", "japaneast")
    sub = run("az account show --query id -o tsv")
    enable_ent = os.environ.get("ENABLE_ENTERPRISE_SECURITY", "false").lower() == "true"

    print("=" * 50)
    print("  postprovision セットアップ開始")
    print("=" * 50)

    # --- 1. Foundry project ---
    print("\n[1/9] Foundry project")
    foundry_name = run(
        f"az resource list -g {rg} --resource-type Microsoft.CognitiveServices/accounts "
        f"--query \"[?kind=='AIServices'].name | [0]\" -o tsv"
    )
    if foundry_name:
        if not run_ok(
            f"az cognitiveservices account project show --name {foundry_name} "
            f"--resource-group {rg} --project-name inventory-project"
        ):
            run(
                f"az cognitiveservices account project create --name {foundry_name} "
                f"--resource-group {rg} --project-name inventory-project "
                f"--location {location} -o none"
            )
            print(f"  作成完了: {foundry_name}/inventory-project")
        else:
            print(f"  既存: {foundry_name}/inventory-project")

    # --- 2. Private DNS Zone (internal CAE) ---
    print("\n[2/9] Private DNS Zone")
    if enable_ent:
        cae_name = run(
            f'az resource list -g {rg} --resource-type Microsoft.App/managedEnvironments --query "[0].name" -o tsv'
        )
        if cae_name:
            cae_json = run(
                f"az containerapp env show -g {rg} -n {cae_name} "
                f'--query "{{domain:properties.defaultDomain,ip:properties.staticIp}}" -o json'
            )
            if cae_json:
                cae_info = json.loads(cae_json)
                domain = cae_info["domain"]
                static_ip = cae_info["ip"]
                vnet_id = run(f'az network vnet list -g {rg} --query "[0].id" -o tsv')
                if not run_ok(f"az network private-dns zone show -g {rg} -n {domain}"):
                    run(f"az network private-dns zone create -g {rg} -n {domain} -o none")
                    run(
                        f"az network private-dns link vnet create -g {rg} -z {domain} "
                        f"-n cae-dns-link --virtual-network {vnet_id} "
                        f"--registration-enabled false -o none"
                    )
                    run(
                        f"az network private-dns record-set a add-record "
                        f"-g {rg} -z {domain} -n '*' -a {static_ip} -o none"
                    )
                    run(
                        f"az network private-dns record-set a add-record "
                        f"-g {rg} -z {domain} -n '@' -a {static_ip} -o none"
                    )
                    print(f"  作成完了: {domain} -> {static_ip}")
                else:
                    print(f"  既存: {domain}")
    else:
        print("  スキップ（enterprise モードではない）")

    # --- 2.5 NSG Flow Logs (enterprise only) ---
    if enable_ent:
        storage_name = run(
            f"az resource list -g {rg} --resource-type Microsoft.Storage/storageAccounts "
            f"--query \"[?starts_with(name, 'stflow')].name | [0]\" -o tsv"
        )
        log_ws_id = run(
            f'az resource list -g {rg} --resource-type Microsoft.OperationalInsights/workspaces --query "[0].id" -o tsv'
        )
        if storage_name and log_ws_id:
            nsg_names = run(
                f"az resource list -g {rg} --resource-type Microsoft.Network/networkSecurityGroups "
                f'--query "[].name" -o tsv'
            )
            for nsg_name in (nsg_names or "").split("\n"):
                nsg_name = nsg_name.strip()
                if not nsg_name:
                    continue
                fl_name = f"flowlog-{nsg_name}"
                if not run_ok(f"az network watcher flow-log show --location {location} --name {fl_name}"):
                    nsg_id = run(f"az network nsg show -g {rg} -n {nsg_name} --query id -o tsv")
                    storage_id = run(f"az storage account show -g {rg} -n {storage_name} --query id -o tsv")
                    if nsg_id and storage_id:
                        run(
                            f"az network watcher flow-log create --location {location} "
                            f"--name {fl_name} --nsg {nsg_id} "
                            f"--storage-account {storage_id} "
                            f"--workspace {log_ws_id} "
                            f"--enabled true --retention 7 "
                            f"--traffic-analytics true --interval 10 "
                            f"--format JSON --log-version 2 -o none",
                            check=False,
                        )
                        print(f"  Flow Log 作成: {fl_name}")
                else:
                    print(f"  Flow Log 既存: {fl_name}")

    # --- 3. SQL データ投入 + MI 権限 ---
    print("\n[3/9] SQL セットアップ")
    sql_server = os.environ.get("AZURE_SQL_SERVER", "")
    sql_db = os.environ.get("AZURE_SQL_DATABASE", "inventory_db")
    if sql_server:
        # MI ユーザー名を取得
        ca_name = run(f'az resource list -g {rg} --resource-type Microsoft.App/containerApps --query "[0].name" -o tsv')
        if ca_name:
            # SQL public access を一時有効化
            run(
                f"az sql server update -g {rg} -n {sql_server.split('.')[0]} --enable-public-network true -o none",
                check=False,
            )
            # FW ルール作成
            run(
                f"az sql server firewall-rule create -g {rg} "
                f"-s {sql_server.split('.')[0]} -n AllowAzureServices "
                f"--start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none",
                check=False,
            )
            # データ投入
            os.environ["SQL_SERVER_FQDN"] = sql_server
            os.environ["SQL_DATABASE_NAME"] = sql_db
            result = subprocess.run(
                [sys.executable, "scripts/load_data.py"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"  データ投入: {result.stdout.strip()}")
            else:
                print(f"  データ投入スキップ: {result.stderr[:100]}")

            # MI 権限付与
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/grant_sql_access.py",
                    "--server",
                    sql_server,
                    "--database",
                    sql_db,
                    "--principal-name",
                    ca_name,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"  MI 権限付与: {ca_name}")
            else:
                print(f"  MI 権限スキップ: {result.stderr[:100]}")

            # SQL public access を無効に戻す（enterprise）
            if enable_ent:
                run(
                    f"az sql server firewall-rule delete -g {rg} "
                    f"-s {sql_server.split('.')[0]} -n AllowAzureServices -o none",
                    check=False,
                )
                run(
                    f"az sql server update -g {rg} -n {sql_server.split('.')[0]} --enable-public-network false -o none",
                    check=False,
                )
                print("  SQL public access 無効化")
    else:
        print("  スキップ（AZURE_SQL_SERVER 未設定）")

    # --- 4. APIM REST API import ---
    print("\n[4/9] APIM REST API import")
    apim_name = run(
        f'az resource list -g {rg} --resource-type Microsoft.ApiManagement/service --query "[0].name" -o tsv'
    )
    if apim_name:
        # 既存 API 確認
        api_check = run(
            f'az rest --method get --url "https://management.azure.com/subscriptions/{sub}'
            f"/resourceGroups/{rg}/providers/Microsoft.ApiManagement/service/{apim_name}"
            f'/apis/inventory-api?api-version=2024-05-01" --query name -o tsv',
            check=False,
        )
        if not api_check:
            # OpenAPI spec 生成
            sys.path.insert(0, "src")
            from main import app

            spec = app.openapi()
            spec_json = json.dumps(spec, ensure_ascii=False)

            # CA の FQDN を取得
            ca_fqdn = os.environ.get("AZURE_CONTAINER_APPS_FQDN", "")

            import_body = {
                "properties": {
                    "format": "openapi+json",
                    "value": spec_json,
                    "path": "",
                    "displayName": "Inventory API",
                    "serviceUrl": f"https://{ca_fqdn}" if ca_fqdn else None,
                    "protocols": ["https"],
                    "subscriptionRequired": False,
                }
            }
            import_file = "apim-import-body.json"
            with open(import_file, "w", encoding="utf-8") as f:
                json.dump(import_body, f, ensure_ascii=False)

            api_url = (
                f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
                f"/providers/Microsoft.ApiManagement/service/{apim_name}/apis/inventory-api"
                f"?api-version=2024-05-01"
            )
            run(
                f'az rest --method put --url "{api_url}" '
                f'--headers "Content-Type=application/json" '
                f'--body "@{import_file}" -o none'
            )
            os.remove(import_file)

            # serviceUrl を PATCH（import で null になる場合がある）
            if ca_fqdn:
                patch_body = json.dumps(
                    {
                        "properties": {
                            "serviceUrl": f"https://{ca_fqdn}",
                            "subscriptionRequired": False,
                        }
                    }
                )
                patch_file = "apim-patch.json"
                with open(patch_file, "w") as f:
                    f.write(patch_body)
                run(
                    f'az rest --method patch --url "{api_url}" '
                    f'--headers "Content-Type=application/json" '
                    f'--body "@{patch_file}" -o none'
                )
                os.remove(patch_file)
            print(f"  API import 完了: {apim_name}/inventory-api")
        else:
            print(f"  既存: {apim_name}/inventory-api")
    else:
        print("  スキップ（APIM 未検出）")

    # --- 5. Foundry project connection ---
    print("\n[5/9] Foundry connection")
    entra_app_id = os.environ.get("ENTRA_APP_CLIENT_ID", "")
    if foundry_name and apim_name:
        conn_url = (
            f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.CognitiveServices/accounts/{foundry_name}"
            f"/projects/inventory-project/connections/inventory-mcp-connection"
            f"?api-version=2025-04-01-preview"
        )
        conn_body = {
            "properties": {
                "authType": "ProjectManagedIdentity",
                "category": "RemoteTool",
                "target": f"https://{apim_name}.azure-api.net/inventory-mcp/mcp",
                "isSharedToAll": True,
                "audience": f"api://{entra_app_id}",
                "metadata": {"ApiType": "Azure"},
            }
        }
        conn_file = "connection-body.json"
        with open(conn_file, "w") as f:
            json.dump(conn_body, f)
        run(
            f'az rest --method put --url "{conn_url}" '
            f'--headers "Content-Type=application/json" '
            f'--body "@{conn_file}" -o none'
        )
        os.remove(conn_file)
        print("  作成完了: inventory-mcp-connection (PMI)")
    else:
        print("  スキップ（Foundry or APIM 未検出）")

    # --- 6. MCP policy ---
    print("\n[6/9] MCP policy")
    if apim_name:
        mcp_check_url = (
            f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.ApiManagement/service/{apim_name}"
            f"/apis/inventory-mcp?api-version=2024-05-01"
        )
        if run_ok(f'az rest --method get --url "{mcp_check_url}"'):
            policy_url = (
                f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
                f"/providers/Microsoft.ApiManagement/service/{apim_name}"
                f"/apis/inventory-mcp/policies/policy?api-version=2024-05-01"
            )
            # テンプレートを実際の値に置換
            policy_template = os.path.join(os.path.dirname(__file__), "mcp-policy.json")
            tenant_id = run("az account show --query tenantId -o tsv")
            with open(policy_template, encoding="utf-8") as f:
                policy_content = f.read()
            policy_content = policy_content.replace("{{AZURE_TENANT_ID}}", tenant_id)
            policy_content = policy_content.replace("{{ENTRA_APP_CLIENT_ID}}", entra_app_id)
            policy_resolved = "mcp-policy-resolved.json"
            with open(policy_resolved, "w", encoding="utf-8") as f:
                f.write(policy_content)
            run(
                f'az rest --method put --url "{policy_url}" '
                f'--headers "Content-Type=application/json" '
                f'--body "@{policy_resolved}" -o none'
            )
            if os.path.exists(policy_resolved):
                os.remove(policy_resolved)
            print("  適用完了: validate-azure-ad-token + rate-limit-by-key")
        else:
            print("  MCP API 未検出。APIM ポータルで MCP Server を作成してください。")
    else:
        print("  スキップ")

    # --- 7. Agent 作成 ---
    print("\n[7/9] Foundry agent")
    if foundry_name:
        project_endpoint = f"https://{foundry_name}.services.ai.azure.com/api/projects/inventory-project"
        os.environ["FOUNDRY_PROJECT_ENDPOINT"] = project_endpoint
        os.environ["AGENT_NAME"] = "inventory-ent-pmi"
        os.environ["MCP_SERVER_URL"] = f"https://{apim_name}.azure-api.net/inventory-mcp/mcp"
        os.environ["MCP_SERVER_LABEL"] = "inventory-mcp"
        os.environ["MCP_PROJECT_CONNECTION_ID"] = "inventory-mcp-connection"
        os.environ.setdefault("FOUNDRY_MODEL", "gpt-5-mini")

        result = subprocess.run(
            [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "create_agent.py"),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  {result.stdout.strip()}")
        else:
            print(f"  スキップ: {result.stderr[:200]}")
    else:
        print("  スキップ")

    # --- 8. Agent Application publish ---
    print("\n[8/9] Agent Application publish")
    agent_name = "inventory-ent-pmi"
    if foundry_name:
        app_url = (
            f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.CognitiveServices/accounts/{foundry_name}"
            f"/projects/inventory-project/applications/{agent_name}"
            f"?api-version=2025-10-01-preview"
        )
        app_body = {
            "properties": {
                "agents": [{"agentName": agent_name}],
            }
        }
        app_file = "app-publish.json"
        with open(app_file, "w") as f:
            json.dump(app_body, f)
        result_text = run(
            f'az rest --method put --url "{app_url}" '
            f'--headers "Content-Type=application/json" '
            f'--body "@{app_file}" --query name -o tsv',
            check=False,
        )
        if os.path.exists(app_file):
            os.remove(app_file)
        if result_text:
            print(f"  Agent Application 公開完了: {result_text}")
            # Deployment 作成
            deploy_url = (
                f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
                f"/providers/Microsoft.CognitiveServices/accounts/{foundry_name}"
                f"/projects/inventory-project/applications/{agent_name}"
                f"/agentdeployments/default?api-version=2025-10-01-preview"
            )
            deploy_body = {
                "properties": {
                    "deploymentType": "Managed",
                    "agents": [{"agentName": agent_name}],
                }
            }
            deploy_file = "deploy-publish.json"
            with open(deploy_file, "w") as f:
                json.dump(deploy_body, f)
            run(
                f'az rest --method put --url "{deploy_url}" '
                f'--headers "Content-Type=application/json" '
                f'--body "@{deploy_file}" -o none',
                check=False,
            )
            if os.path.exists(deploy_file):
                os.remove(deploy_file)
            print("  Deployment 作成完了")
        else:
            print("  Agent Application の自動 publish はスキップ（REST API SystemError）")
            print("  → Foundry ポータルで手動 publish してください")
    else:
        print("  スキップ")

    # --- 完了 ---
    # --- 9. Grafana Dashboard パネル投入 (enterprise only) ---
    print("\n[9/9] Grafana Dashboard")
    if enable_ent:
        dashboard_names = run(
            f'az resource list -g {rg} --resource-type Microsoft.Dashboard/dashboards --query "[].name" -o tsv'
        )
        if dashboard_names:
            for db_name in dashboard_names.split("\n"):
                db_name = db_name.strip()
                if not db_name:
                    continue
                # Grafana endpoint を取得
                grafana_endpoint = run(
                    f'az rest --method get --url "https://management.azure.com/subscriptions/{sub}'
                    f"/resourceGroups/{rg}/providers/Microsoft.Dashboard/dashboards/{db_name}"
                    f'?api-version=2025-08-01" --query properties.grafanaEndpoint -o tsv',
                    check=False,
                )
                if grafana_endpoint:
                    # App Insights リソース ID を取得してダッシュボードパネルを構成
                    appi_id = run(
                        f"az resource list -g {rg} --resource-type Microsoft.Insights/components "
                        f'--query "[0].id" -o tsv'
                    )
                    if "api-overview" in db_name:
                        dashboard_json = _build_api_overview_dashboard(appi_id)
                    else:
                        dashboard_json = _build_alerts_dashboard(appi_id)

                    body_file = f"grafana-{db_name}.json"
                    with open(body_file, "w", encoding="utf-8") as f:
                        json.dump({"dashboard": dashboard_json, "overwrite": True}, f, ensure_ascii=False)

                    token = run("az account get-access-token --query accessToken -o tsv")
                    result = subprocess.run(
                        [
                            "curl",
                            "-s",
                            "-X",
                            "POST",
                            f"{grafana_endpoint}/api/dashboards/db",
                            "-H",
                            f"Authorization: Bearer {token}",
                            "-H",
                            "Content-Type: application/json",
                            "-d",
                            f"@{body_file}",
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if os.path.exists(body_file):
                        os.remove(body_file)
                    if result.returncode == 0 and "uid" in result.stdout:
                        print(f"  パネル投入完了: {db_name}")
                    else:
                        print(f"  パネル投入スキップ: {db_name} (endpoint 未取得 or API エラー)")
                        print("  → Azure ポータル > Azure Monitor > Dashboards with Grafana で手動設定可能")
                else:
                    print(f"  Grafana endpoint 未取得: {db_name}")
                    print("  → Azure ポータル > Azure Monitor > Dashboards with Grafana で手動設定可能")
        else:
            print("  Grafana Dashboard リソース未検出")
    else:
        print("  スキップ（enterprise モードではない）")

    print("\n" + "=" * 50)
    print("  セットアップ完了")
    print("=" * 50)
    print("残りの手動ステップ:")
    print("  1. APIM -> MCP Servers -> Create MCP server（初回のみ）")
    print("  2. APIM ポータル -> Network -> 送信 -> VNet integration 有効化確認")
    print("  3. Foundry ポータルで Publish to Teams & M365 Copilot")
    print("  4. M365 Admin Center で Organization scope 承認（オプション）")
    print("=" * 50)


if __name__ == "__main__":
    main()
