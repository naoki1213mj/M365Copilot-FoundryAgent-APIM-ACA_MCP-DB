"""Foundry Agent 作成スクリプト（第3世代: azure-ai-projects 2.x, Responses API ベース）

APIM MCP Server 経由で在庫 API を呼び出すエージェントを作成する。
認証の既定経路は project_connection_id（Entra JWT）。fallback として追加ヘッダーも渡せる。
SDK 2.x では create_version で新バージョンを作成。delete_agent API は非対応。
"""

import json
import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential

# --- 設定（環境変数から取得） ---
PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL", "gpt-5-mini")
AGENT_NAME = os.environ.get("AGENT_NAME", "inventory-assistant")
MCP_SERVER_URL = os.environ["MCP_SERVER_URL"]
MCP_SERVER_LABEL = os.environ.get("MCP_SERVER_LABEL", "inventory-mcp")
MCP_PROJECT_CONNECTION_ID = os.environ.get("MCP_PROJECT_CONNECTION_ID")
APIM_SUBSCRIPTION_KEY = os.environ.get("APIM_SUBSCRIPTION_KEY")
MCP_HEADERS_JSON = os.environ.get("MCP_HEADERS_JSON")

INSTRUCTIONS = """あなたは在庫管理アシスタントです。
ユーザーからの問い合わせに対して、MCP ツールを使って在庫データを照会し、日本語で回答します。

ルール:
- 商品を検索する場合 → get-products または get-products-by-code ツールを使う
- 在庫を検索する場合 → get-inventory ツールを使う
- 発注点割れ確認 → get-inventory-alerts ツールを使う
- 倉庫別照会 → get-warehouses または get-warehouses-stock-by-code ツールを使う
- needs_reorder が 1 の商品は「⚠ 発注推奨」と伝える
- shortage（不足数）と fill_rate（充足率）も併せて報告する
- データの更新はできません（読み取り専用）
- 回答は簡潔に、表形式を使うと見やすい"""

# --- エージェント作成 ---
credential = DefaultAzureCredential()
project_client = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=credential,
)

mcp_headers: dict[str, str] | None = None
if MCP_HEADERS_JSON:
    loaded_headers = json.loads(MCP_HEADERS_JSON)
    if not isinstance(loaded_headers, dict):
        raise ValueError("MCP_HEADERS_JSON must be a JSON object")
    mcp_headers = {str(key): str(value) for key, value in loaded_headers.items()}
elif APIM_SUBSCRIPTION_KEY:
    mcp_headers = {"Ocp-Apim-Subscription-Key": APIM_SUBSCRIPTION_KEY}

mcp_tool_kwargs: dict[str, object] = {
    "server_label": MCP_SERVER_LABEL,
    "server_url": MCP_SERVER_URL,
    "require_approval": "never",
}
if MCP_PROJECT_CONNECTION_ID:
    mcp_tool_kwargs["project_connection_id"] = MCP_PROJECT_CONNECTION_ID
if mcp_headers:
    mcp_tool_kwargs["headers"] = mcp_headers

# --- 既存エージェントの確認（SDK 2.x は create_version で新バージョン作成、削除不要） ---
try:
    existing_versions = list(project_client.agents.list_versions(AGENT_NAME, limit=10))
    if existing_versions:
        print(f"既存エージェント検出: {AGENT_NAME} ({len(existing_versions)} versions) → 新バージョン作成")
except ResourceNotFoundError:
    pass  # 存在しない場合は新規作成
except Exception as e:
    print(f"  既存エージェント確認スキップ: {e}")

agent = project_client.agents.create_version(
    agent_name=AGENT_NAME,
    definition=PromptAgentDefinition(
        model=MODEL,
        instructions=INSTRUCTIONS,
        tools=[
            MCPTool(**mcp_tool_kwargs),
        ],
    ),
)

print(f"エージェント作成完了: {agent.name}:{agent.version}")
print(f"  モデル: {MODEL}")
print(f"  エージェント名: {AGENT_NAME}")
print(f"  MCP Server: {MCP_SERVER_URL}")
print(f"  MCP Label: {MCP_SERVER_LABEL}")
if MCP_PROJECT_CONNECTION_ID:
    print(f"  MCP Connection: {MCP_PROJECT_CONNECTION_ID}")
if mcp_headers:
    print(f"  MCP Headers: {list(mcp_headers.keys())}")
