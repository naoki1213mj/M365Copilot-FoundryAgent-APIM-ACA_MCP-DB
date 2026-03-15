"""Foundry Agent テスト（第3世代: Responses API）

inventory-assistant に問い合わせて MCP ツール呼び出しを確認する。
MCP ツールは approval が必要なので、自動承認ループを実装。
"""

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = os.environ.get("AGENT_NAME", "inventory-assistant")
AGENT_VERSION = os.environ.get("AGENT_VERSION", "")  # 空なら最新バージョンを自動取得

credential = DefaultAzureCredential()
project_client = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
openai_client = project_client.get_openai_client()

# バージョン自動解決
if not AGENT_VERSION:
    versions = list(project_client.agents.list_versions(AGENT_NAME, order="desc", limit=1))
    if not versions:
        raise RuntimeError(f"エージェント '{AGENT_NAME}' のバージョンが見つかりません")
    AGENT_VERSION = versions[0].version
    print(f"最新バージョン自動取得: {AGENT_NAME}:{AGENT_VERSION}")

# テストクエリ
test_query = "East Warehouse で発注点割れしている商品を教えて"
print(f"質問: {test_query}")
print("-" * 50)

# Response 生成
response = openai_client.responses.create(
    input=[{"role": "user", "content": test_query}],
    extra_body={
        "agent_reference": {
            "name": AGENT_NAME,
            "version": AGENT_VERSION,
            "type": "agent_reference",
        }
    },
)

# MCP approval ループ
max_loops = 5
for i in range(max_loops):
    # MCP approval request があるか確認
    approval_needed = False
    for item in response.output:
        if getattr(item, "type", None) == "mcp_approval_request":
            approval_needed = True
            print(f"[MCP 承認要求] id={item.id}")
            # 自動承認して続行
            response = openai_client.responses.create(
                input=[
                    {
                        "type": "mcp_approval_response",
                        "approve": True,
                        "approval_request_id": item.id,
                    }
                ],
                extra_body={
                    "agent_reference": {
                        "name": AGENT_NAME,
                        "version": AGENT_VERSION,
                        "type": "agent_reference",
                    },
                    "previous_response_id": response.id,
                },
            )
            break

    if not approval_needed:
        break

# 結果出力
print("\n回答:")
print(response.output_text)

# ツール呼び出し詳細
print("\n--- 出力アイテム詳細 ---")
for item in response.output:
    item_type = getattr(item, "type", "unknown")
    print(f"  type: {item_type}")
    if item_type == "mcp_call":
        print(f"    server: {getattr(item, 'server_label', 'N/A')}")
        print(f"    tool: {getattr(item, 'name', 'N/A')}")
        print(f"    args: {getattr(item, 'arguments', 'N/A')}")
    elif item_type == "mcp_call_output":
        output_val = getattr(item, "output", "N/A")
        if isinstance(output_val, str) and len(output_val) > 200:
            output_val = output_val[:200] + "..."
        print(f"    output: {output_val}")
