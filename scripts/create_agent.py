"""Foundry Agent 作成スクリプト（第3世代: azure-ai-projects 2.x, Responses API ベース）

APIM MCP Server 経由で在庫 API を呼び出すエージェントを作成する。
認証は Key-based（APIM Subscription Key）。
"""

import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential

# --- 設定（環境変数から取得） ---
PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL", "gpt-5-mini")
AGENT_NAME = "inventory-assistant"
MCP_SERVER_URL = os.environ["MCP_SERVER_URL"]

INSTRUCTIONS = """あなたは在庫管理アシスタントです。
商品部デリバリー担当者からの問い合わせに対して、MCP ツールを使って在庫データを照会し、日本語で回答します。

ルール:
- SKU を指定された場合 → get_inventory_by_sku ツールを使う
- 倉庫指定・カテゴリ指定・発注点割れ確認 → list_inventory ツールを使う
- needs_reorder が true の商品は「⚠ 発注推奨」と伝える
- quantity と reorder_point の差分も併せて報告する
- データの更新はできません（読み取り専用）
- 回答は簡潔に、表形式を使うと見やすい"""

# --- エージェント作成 ---
credential = DefaultAzureCredential()
project_client = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=credential,
)

agent = project_client.agents.create_version(
    agent_name=AGENT_NAME,
    definition=PromptAgentDefinition(
        model=MODEL,
        instructions=INSTRUCTIONS,
        tools=[
            MCPTool(
                server_label="inventory-mcp",
                server_url=MCP_SERVER_URL,
                # 認証なし（APIM subscription key は Foundry 側の接続設定で管理）
                # 本番では project_connection_id を使って認証する
            ),
        ],
    ),
)

print(f"エージェント作成完了: {agent.name}:{agent.version}")
print(f"  モデル: {MODEL}")
print(f"  MCP Server: {MCP_SERVER_URL}")
