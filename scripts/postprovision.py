"""azd postprovision: 全セットアップの自動化スクリプト (AI Gateway 対応版)

azd up 後に実行され、以下を自動化する:
1. Foundry project 作成
2. Private DNS Zone + NSG Flow Logs (enterprise)
3. SQL データ投入 + MI ユーザー権限付与
4. APIM REST API import
5. Entra App 登録（権限チェック → 自動 or スキップ+手順案内）
6. APIM → CA ヘルスチェック（VNet integration 検証）
7. Foundry connections（AI Gateway or RemoteTool）
8. MCP policy 適用
9. Foundry agent 作成
10. Agent Application publish
11. Grafana Dashboard パネル投入 (enterprise)

USE_AI_GATEWAY=true (デフォルト): APIM を AI Gateway として Foundry に接続
USE_AI_GATEWAY=false: 従来の RemoteTool connection のみ
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


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


def _write_json(data: dict, filename: str) -> str:
    """一時 JSON ファイルを書き出してパスを返す。"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return filename


def _cleanup(path: str) -> None:
    """ファイルが存在すれば削除。"""
    if os.path.exists(path):
        os.remove(path)


# ============================================================
# 各ステップ
# ============================================================


def step1_foundry_project(rg: str, location: str) -> str:
    """[1/11] Foundry project の作成/確認。"""
    print("\n[1/11] Foundry project")
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

        # RBAC 付与（Agent 操作に必要）
        # Azure AI Developer: OpenAI/SpeechServices 等の data actions
        # Cognitive Services User: AIServices/agents/* の data actions（SDK 2.x で必須）
        principal_id = run("az ad signed-in-user show --query id -o tsv", check=False)
        if principal_id:
            foundry_id = run(
                f'az resource list -g {rg} --resource-type Microsoft.CognitiveServices/accounts --query "[0].id" -o tsv'
            )
            if foundry_id:
                for role in ["Azure AI Developer", "Cognitive Services User"]:
                    # account レベル
                    run(
                        f"az role assignment create --assignee-object-id {principal_id} "
                        f"--assignee-principal-type User "
                        f'--role "{role}" --scope {foundry_id} -o none',
                        check=False,
                    )
                # project レベル（強制付与）
                project_id = run(
                    f"az cognitiveservices account project show --name {foundry_name} "
                    f"--resource-group {rg} --project-name inventory-project --query id -o tsv",
                    check=False,
                )
                if project_id:
                    for role in ["Azure AI Developer", "Cognitive Services User"]:
                        run(
                            f"az role assignment create --assignee-object-id {principal_id} "
                            f"--assignee-principal-type User "
                            f'--role "{role}" --scope {project_id} -o none',
                            check=False,
                        )
                print("  RBAC 付与: Azure AI Developer + Cognitive Services User（伝播に数分かかる場合があります）")
    return foundry_name


def step2_dns_and_flow_logs(rg: str, location: str, enable_ent: bool) -> None:
    """[2/11] Private DNS Zone + NSG Flow Logs (enterprise)。"""
    print("\n[2/11] Private DNS Zone + NSG Flow Logs")
    if not enable_ent:
        print("  スキップ（enterprise モードではない）")
        return

    # --- Private DNS Zone ---
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
                    f"az network private-dns record-set a create -g {rg} -z {domain} -n * -o none",
                    check=False,
                )
                run(f"az network private-dns record-set a add-record -g {rg} -z {domain} -n * -a {static_ip} -o none")
                run(f"az network private-dns record-set a add-record -g {rg} -z {domain} -n @ -a {static_ip} -o none")
                print(f"  DNS 作成完了: {domain} -> {static_ip}")
            else:
                print(f"  DNS 既存: {domain}")

    # --- NSG Flow Logs ---
    storage_name = run(
        f"az resource list -g {rg} --resource-type Microsoft.Storage/storageAccounts "
        f"--query \"[?starts_with(name, 'stflow')].name | [0]\" -o tsv"
    )
    log_ws_id = run(
        f'az resource list -g {rg} --resource-type Microsoft.OperationalInsights/workspaces --query "[0].id" -o tsv'
    )
    if storage_name and log_ws_id:
        nsg_names = run(
            f'az resource list -g {rg} --resource-type Microsoft.Network/networkSecurityGroups --query "[].name" -o tsv'
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


def step3_sql_setup(rg: str, enable_ent: bool) -> None:
    """[3/11] SQL データ投入 + MI 権限付与。"""
    print("\n[3/11] SQL セットアップ")
    sql_server = os.environ.get("AZURE_SQL_SERVER", "")
    sql_db = os.environ.get("AZURE_SQL_DATABASE", "inventory_db")
    if not sql_server:
        print("  スキップ（AZURE_SQL_SERVER 未設定）")
        return

    ca_name = run(f'az resource list -g {rg} --resource-type Microsoft.App/containerApps --query "[0].name" -o tsv')
    if not ca_name:
        print("  スキップ（Container App 未検出）")
        return

    server_short = sql_server.split(".")[0]

    # SQL public access を一時有効化
    run(f"az sql server update -g {rg} -n {server_short} --enable-public-network true -o none", check=False)
    run(
        f"az sql server firewall-rule create -g {rg} -s {server_short} -n AllowAzureServices "
        f"--start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none",
        check=False,
    )

    # データ投入
    os.environ["SQL_SERVER_FQDN"] = sql_server
    os.environ["SQL_DATABASE_NAME"] = sql_db
    result = subprocess.run([sys.executable, "scripts/load_data.py"], capture_output=True, text=True)
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
        run(f"az sql server firewall-rule delete -g {rg} -s {server_short} -n AllowAzureServices -o none", check=False)
        run(f"az sql server update -g {rg} -n {server_short} --enable-public-network false -o none", check=False)
        print("  SQL public access 無効化")


def step4_apim_import(rg: str, sub: str) -> str:
    """[4/11] APIM REST API import。"""
    print("\n[4/11] APIM REST API import")
    apim_name = run(
        f'az resource list -g {rg} --resource-type Microsoft.ApiManagement/service --query "[0].name" -o tsv'
    )
    if not apim_name:
        print("  スキップ（APIM 未検出）")
        return ""

    api_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.ApiManagement/service/{apim_name}/apis/inventory-api"
        f"?api-version=2024-05-01"
    )
    api_check = run(
        f'az rest --method get --url "{api_url}" --query name -o tsv',
        check=False,
    )
    if api_check:
        print(f"  既存: {apim_name}/inventory-api")
        return apim_name

    # OpenAPI spec 生成
    sys.path.insert(0, "src")
    from main import app

    spec = app.openapi()
    spec_json = json.dumps(spec, ensure_ascii=False)
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
    import_file = _write_json(import_body, "apim-import-body.json")
    run(
        f'az rest --method put --url "{api_url}" '
        f'--headers "Content-Type=application/json" '
        f'--body "@{import_file}" -o none'
    )
    _cleanup(import_file)

    # serviceUrl を PATCH（import で null になる場合がある）
    if ca_fqdn:
        patch_body = {"properties": {"serviceUrl": f"https://{ca_fqdn}", "subscriptionRequired": False}}
        patch_file = _write_json(patch_body, "apim-patch.json")
        run(
            f'az rest --method patch --url "{api_url}" '
            f'--headers "Content-Type=application/json" '
            f'--body "@{patch_file}" -o none'
        )
        _cleanup(patch_file)

    print(f"  API import 完了: {apim_name}/inventory-api")
    return apim_name


def step5_entra_app() -> str:
    """[5/11] Entra App 登録（権限チェック → 自動 or スキップ+手順案内）。"""
    print("\n[5/11] Entra App 登録")

    # 既存の ENTRA_APP_CLIENT_ID を確認
    existing_id = os.environ.get("ENTRA_APP_CLIENT_ID", "")
    if existing_id:
        if run_ok(f"az ad app show --id {existing_id} --query appId -o tsv"):
            print(f"  既存: {existing_id}")
            return existing_id
        print(f"  WARN: ENTRA_APP_CLIENT_ID={existing_id} が見つかりません。再作成を試みます。")

    # 既存の inventory-api アプリを検索
    existing_app = run('az ad app list --display-name "inventory-api" --query "[0].appId" -o tsv')
    if existing_app:
        print(f"  既存アプリ検出: {existing_app}")
        run(f"azd env set ENTRA_APP_CLIENT_ID {existing_app}", check=False)
        return existing_app

    # 権限チェック（Graph API で allowedToCreateApps を確認）
    allowed = run(
        'az rest --url "https://graph.microsoft.com/v1.0/policies/authorizationPolicy" '
        '--query "defaultUserRolePermissions.allowedToCreateApps" -o tsv',
        check=False,
    )
    if allowed.lower() != "true":
        print("  ⚠ Entra App 登録権限がありません（allowedToCreateApps=false）")
        print("  → Application Developer ロールを付与してもらうか、手動で実行:")
        print("    bash scripts/setup-entra.sh")
        print("    azd env set ENTRA_APP_CLIENT_ID <出力された Client ID>")
        return ""

    # 自動登録
    app_id = run('az ad app create --display-name "inventory-api" --sign-in-audience AzureADMyOrg --query appId -o tsv')
    if not app_id:
        print("  ⚠ Entra App 作成に失敗しました")
        return ""

    run(f'az ad app update --id {app_id} --identifier-uris "api://{app_id}"')
    run(f"az ad sp create --id {app_id} -o none", check=False)
    run(f"azd env set ENTRA_APP_CLIENT_ID {app_id}", check=False)
    print(f"  自動登録完了: {app_id}")
    return app_id


def step6_health_check(apim_name: str) -> None:
    """[6/11] APIM → Container Apps の疎通確認。"""
    print("\n[6/11] APIM → CA ヘルスチェック")
    if not apim_name:
        print("  スキップ（APIM 未検出）")
        return

    gateway_url = f"https://{apim_name}.azure-api.net/health"
    try:
        req = urllib.request.Request(gateway_url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                print(f"  疎通確認OK: {gateway_url} -> {resp.status}")
            else:
                print(f"  ⚠ ステータス {resp.status}: {gateway_url}")
    except urllib.error.HTTPError as e:
        # 404 = APIM に到達しているが /health が REST API 側にしかない → 疎通自体はOK
        if e.code == 404:
            print(f"  疎通確認OK（APIM 到達、/health 未定義）: {gateway_url} -> 404")
        else:
            print(f"  ⚠ HTTP {e.code}: {gateway_url}")
            print("  → API import が完了しているか、VNet integration が正しいか確認")
    except Exception as e:
        print(f"  ⚠ 疎通確認失敗: {e}")
        print("  → APIM VNet integration / NSG / DNS 設定を確認")


def step7_connections(
    foundry_name: str,
    apim_name: str,
    rg: str,
    sub: str,
    entra_app_id: str,
    use_ai_gateway: bool,
) -> None:
    """[7/11] Foundry project connections（AI Gateway + RemoteTool or RemoteTool のみ）。"""
    print(f"\n[7/11] Foundry connections (AI Gateway: {use_ai_gateway})")
    if not foundry_name or not apim_name:
        print("  スキップ（Foundry or APIM 未検出）")
        return

    base_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.CognitiveServices/accounts/{foundry_name}"
        f"/projects/inventory-project/connections"
    )
    api_version = "2025-04-01-preview"

    # --- AI Gateway 接続（USE_AI_GATEWAY=true のみ） ---
    if use_ai_gateway:
        apim_resource_id = (
            f"/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.ApiManagement/service/{apim_name}"
        )
        gw_body = {
            "properties": {
                "authType": "ProjectManagedIdentity",
                "category": "ApiManagement",
                "target": f"https://{apim_name}.azure-api.net",
                "isSharedToAll": True,
                "metadata": {"ResourceId": apim_resource_id},
            }
        }
        gw_file = _write_json(gw_body, "ai-gateway-conn.json")
        gw_url = f"{base_url}/inventory-ai-gateway?api-version={api_version}"
        run(
            f'az rest --method put --url "{gw_url}" '
            f'--headers "Content-Type=application/json" '
            f'--body "@{gw_file}" -o none'
        )
        _cleanup(gw_file)
        print("  AI Gateway 接続作成: inventory-ai-gateway (ApiManagement)")

        # APIM MI に Foundry への Cognitive Services Contributor ロールを付与
        apim_mi = run(f"az apim show -g {rg} -n {apim_name} --query identity.principalId -o tsv", check=False)
        foundry_id = run(
            f'az resource list -g {rg} --resource-type Microsoft.CognitiveServices/accounts --query "[0].id" -o tsv'
        )
        if apim_mi and foundry_id:
            run(
                f"az role assignment create --assignee-object-id {apim_mi} "
                f"--assignee-principal-type ServicePrincipal "
                f'--role "Cognitive Services Contributor" --scope {foundry_id} -o none',
                check=False,
            )
            print("  APIM MI → Foundry: Cognitive Services Contributor 付与")

    # --- RemoteTool 接続（MCP ツール認証用、両経路共通） ---
    mcp_body: dict = {
        "properties": {
            "authType": "ProjectManagedIdentity",
            "category": "RemoteTool",
            "target": f"https://{apim_name}.azure-api.net/inventory-mcp/mcp",
            "isSharedToAll": True,
            "metadata": {"ApiType": "Azure"},
        }
    }
    if entra_app_id:
        mcp_body["properties"]["audience"] = f"api://{entra_app_id}"

    mcp_file = _write_json(mcp_body, "mcp-conn.json")
    mcp_url = f"{base_url}/inventory-mcp-connection?api-version={api_version}"
    run(
        f'az rest --method put --url "{mcp_url}" --headers "Content-Type=application/json" --body "@{mcp_file}" -o none'
    )
    _cleanup(mcp_file)
    print("  RemoteTool 接続作成: inventory-mcp-connection (PMI)")


def step8_mcp_policy(apim_name: str, rg: str, sub: str, entra_app_id: str) -> None:
    """[8/11] MCP policy 適用（MCP Server 存在時のみ）。"""
    print("\n[8/11] MCP policy")
    if not apim_name:
        print("  スキップ")
        return

    mcp_check_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.ApiManagement/service/{apim_name}"
        f"/apis/inventory-mcp?api-version=2024-06-01-preview"
    )
    if not run_ok(f'az rest --method get --url "{mcp_check_url}"'):
        print("  MCP API 未検出。APIM ポータルで MCP Server を作成してください。")
        print("  作成後に postprovision を再実行すると Step 8-10 が自動完了します。")
        return

    policy_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.ApiManagement/service/{apim_name}"
        f"/apis/inventory-mcp/policies/policy?api-version=2024-06-01-preview"
    )
    tenant_id = run("az account show --query tenantId -o tsv")
    policy_template = os.path.join(os.path.dirname(__file__), "mcp-policy.json")
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
    _cleanup(policy_resolved)
    print("  適用完了: validate-azure-ad-token + rate-limit-by-key")


def step8b_ai_gateway_policy(apim_name: str, foundry_name: str, rg: str, sub: str) -> None:
    """[8b] AI Gateway API に TPM 制御 + Content Safety ポリシーを適用。"""
    print("\n[8b] AI Gateway policy (TPM + Content Safety)")
    if not apim_name or not foundry_name:
        print("  スキップ（APIM or Foundry 未検出）")
        return

    api_version = "2024-06-01-preview"

    # AI Gateway API を検索（foundry-* の名前で自動作成される）
    gw_api_name = run(
        f'az rest --method get --url "https://management.azure.com/subscriptions/{sub}'
        f"/resourceGroups/{rg}/providers/Microsoft.ApiManagement/service/{apim_name}"
        f'/apis?api-version={api_version}" '
        f"--query \"value[?starts_with(name, 'foundry-')].name | [0]\" -o tsv",
        check=False,
    )
    if not gw_api_name:
        print("  AI Gateway API 未検出。AI Gateway 接続後に APIM に自動作成されます。")
        return

    # --- Content Safety バックエンド登録 ---
    cs_endpoint = f"https://{foundry_name}.cognitiveservices.azure.com"
    backend_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.ApiManagement/service/{apim_name}"
        f"/backends/content-safety-backend?api-version={api_version}"
    )
    backend_body = {
        "properties": {
            "url": cs_endpoint,
            "protocol": "http",
            "type": "Single",
        }
    }
    backend_file = _write_json(backend_body, "cs-backend.json")
    run(
        f'az rest --method put --url "{backend_url}" '
        f'--headers "Content-Type=application/json" '
        f'--body "@{backend_file}" -o none'
    )
    _cleanup(backend_file)

    # --- AI Gateway API にポリシー適用 ---
    policy_xml = (
        "<policies>"
        "<inbound>"
        "<base />"
        '<llm-token-limit tokens-per-minute="10000" '
        'counter-key="@(context.Subscription.Id)" '
        'estimate-prompt-tokens="true" '
        'tokens-consumed-header-name="x-tokens-consumed" '
        'remaining-tokens-header-name="x-tokens-remaining" />'
        '<llm-content-safety backend-id="content-safety-backend">'
        '<text-shield categories="Hate,SelfHarm,Sexual,Violence" '
        'blocked-status-code="400" />'
        "</llm-content-safety>"
        "</inbound>"
        "<backend><base /></backend>"
        "<outbound><base /></outbound>"
        "<on-error><base /></on-error>"
        "</policies>"
    )
    policy_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.ApiManagement/service/{apim_name}"
        f"/apis/{gw_api_name}/policies/policy?api-version={api_version}"
    )
    policy_body = {"properties": {"format": "rawxml", "value": policy_xml}}
    policy_file = _write_json(policy_body, "gw-policy.json")
    run(
        f'az rest --method put --url "{policy_url}" '
        f'--headers "Content-Type=application/json" '
        f'--body "@{policy_file}" -o none',
        check=False,
    )
    _cleanup(policy_file)
    print(f"  適用完了: llm-token-limit (10K TPM) + llm-content-safety ({gw_api_name})")


def step9_create_agent(foundry_name: str, apim_name: str) -> str:
    """[9/11] Foundry agent 作成（RBAC 伝播待ちリトライ付き）。"""
    print("\n[9/11] Foundry agent")
    agent_name = "inventory-ent-pmi"
    if not foundry_name:
        print("  スキップ")
        return agent_name

    project_endpoint = f"https://{foundry_name}.services.ai.azure.com/api/projects/inventory-project"
    os.environ["FOUNDRY_PROJECT_ENDPOINT"] = project_endpoint
    os.environ["AGENT_NAME"] = agent_name
    os.environ["MCP_SERVER_URL"] = f"https://{apim_name}.azure-api.net/inventory-mcp/mcp"
    os.environ["MCP_SERVER_LABEL"] = "inventory-mcp"
    os.environ["MCP_PROJECT_CONNECTION_ID"] = "inventory-mcp-connection"
    os.environ.setdefault("FOUNDRY_MODEL", "gpt-5-mini")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "create_agent.py")],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  {result.stdout.strip()}")
            return agent_name

        stderr = result.stderr[:200]
        if "PermissionDenied" in stderr and attempt < max_retries:
            wait = 60 * attempt
            print(f"  RBAC 伝播待ち ({attempt}/{max_retries}): {wait}秒後にリトライ...")
            time.sleep(wait)
        else:
            print(f"  スキップ: {stderr}")
            break
    return agent_name


def step10_publish_agent(foundry_name: str, agent_name: str, rg: str, sub: str) -> None:
    """[10/11] Agent Application publish。"""
    print("\n[10/11] Agent Application publish")
    if not foundry_name:
        print("  スキップ")
        return

    app_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.CognitiveServices/accounts/{foundry_name}"
        f"/projects/inventory-project/applications/{agent_name}"
        f"?api-version=2025-10-01-preview"
    )
    app_body = {"properties": {"agents": [{"agentName": agent_name}]}}
    app_file = _write_json(app_body, "app-publish.json")
    result_text = run(
        f'az rest --method put --url "{app_url}" '
        f'--headers "Content-Type=application/json" '
        f'--body "@{app_file}" --query name -o tsv',
        check=False,
    )
    _cleanup(app_file)

    if result_text:
        print(f"  Agent Application 公開完了: {result_text}")
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
        deploy_file = _write_json(deploy_body, "deploy-publish.json")
        run(
            f'az rest --method put --url "{deploy_url}" '
            f'--headers "Content-Type=application/json" '
            f'--body "@{deploy_file}" -o none',
            check=False,
        )
        _cleanup(deploy_file)
        print("  Deployment 作成完了")
    else:
        print("  Agent Application の自動 publish はスキップ（REST API SystemError）")
        print("  → Foundry ポータルで手動 publish してください")


def step11_dashboards(rg: str, enable_ent: bool) -> None:
    """[11/11] ダッシュボード確認 (enterprise)。"""
    print("\n[11/11] ダッシュボード")
    if not enable_ent:
        print("  スキップ（enterprise モードではない）")
        return

    # Azure Portal Dashboard は Bicep で自動プロビジョニング済み（KQL パネル 8 個）
    print("  Azure Portal Dashboard: Bicep で自動作成済み（dash-inventory-api）")
    print("  → Azure ポータル > ダッシュボード で確認可能")

    # Grafana（無料版）は手動設定が必要
    print("  Grafana Dashboard: 無料版は API 自動投入非対応のため手動設定")
    print("  → Azure ポータル > Azure Monitor > Dashboards with Grafana で設定可能")


# ============================================================
# メインフロー
# ============================================================


def main() -> None:
    rg = os.environ.get("AZURE_RESOURCE_GROUP", "rg-inventory-demo")
    location = os.environ.get("AZURE_LOCATION", "japaneast")
    sub = run("az account show --query id -o tsv")
    enable_ent = os.environ.get("ENABLE_ENTERPRISE_SECURITY", "false").lower() == "true"
    use_ai_gateway = os.environ.get("USE_AI_GATEWAY", "true").lower() == "true"

    print("=" * 60)
    print("  postprovision セットアップ開始")
    print(f"  Enterprise: {enable_ent} | AI Gateway: {use_ai_gateway}")
    print("=" * 60)

    # --- 共通ステップ 1-6 ---
    foundry_name = step1_foundry_project(rg, location)
    step2_dns_and_flow_logs(rg, location, enable_ent)
    step3_sql_setup(rg, enable_ent)
    apim_name = step4_apim_import(rg, sub)
    entra_app_id = step5_entra_app()
    step6_health_check(apim_name)

    # --- 分岐ステップ 7 (connections) ---
    step7_connections(foundry_name, apim_name, rg, sub, entra_app_id, use_ai_gateway)

    # --- 共通ステップ 8-10 ---
    step8_mcp_policy(apim_name, rg, sub, entra_app_id)
    if use_ai_gateway:
        step8b_ai_gateway_policy(apim_name, foundry_name, rg, sub)
    agent_name = step9_create_agent(foundry_name, apim_name)
    step10_publish_agent(foundry_name, agent_name, rg, sub)

    # --- 共通ステップ 11 ---
    step11_dashboards(rg, enable_ent)

    # --- 完了サマリ ---
    print("\n" + "=" * 60)
    print("  セットアップ完了")
    print("=" * 60)
    print("残りの手動ステップ:")
    print("  1. APIM -> MCP Servers -> Create MCP server（初回のみ）")
    print("     Source API: Inventory API / Name: inventory-mcp")
    print("     作成後に postprovision を再実行すると Step 8-10 が自動完了します:")
    print("     python scripts/postprovision.py")
    if enable_ent:
        print("  2. APIM ポータル -> Network -> 送信 -> VNet integration 有効化確認")
    n = 3 if enable_ent else 2
    print(f"  {n}. Foundry ポータルで Publish to Teams & M365 Copilot")
    print(f"  {n + 1}. M365 Admin Center で Organization scope 承認（オプション）")
    if use_ai_gateway:
        print("  * AI Gateway 有効: モデル呼び出しが APIM 経由でガバナンスされます")
    print("=" * 60)


if __name__ == "__main__":
    main()
