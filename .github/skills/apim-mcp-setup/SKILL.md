---
name: apim-mcp-setup
description: "APIM で REST API を MCP サーバーとして公開する手順。Triggers: APIM MCP, MCP server, REST to MCP, Foundry tool setup, MCP 設定, ツール接続, export REST as MCP"
---
# APIM MCP Server Setup

## 手順

### 1. OpenAPI インポート
Portal → APIM → APIs → + Add API → OpenAPI → Container Apps の /openapi.json URL

### 2. MCP Server 作成
Portal → APIM → MCP Servers → + Create MCP server → API 選択 → operations を tool として公開。Server URL をコピー。

### 3. Diagnostics（必須）
Portal → APIM → Diagnostic settings → App Insights → **Frontend Response payload bytes = 0**。`context.Response.Body` を読む policy も禁止。省くと MCP 不安定。

### 4. Foundry 接続
Foundry → Agent → Add tool → MCP Server → Server URL 貼り付け → 認証: Subscription Key (demo) / Entra token (prod)

### 5. テスト
Playground: 「INV-004 の在庫を教えて」→ tool call + 構造化レスポンス確認

## ティア要件

| Tier | MCP | VNet Out | 推奨 |
|------|-----|----------|------|
| Consumption | ❌ | ❌ | × |
| Standard v2 | ✅ | ✅ | **デモ・本番** |
| Premium v2 | ✅ | ✅(full) | エンタープライズ |

## 制約 (2026-03)
MCP tools のみ（resources/prompts 非対応）。Streamable HTTP + SSE 対応。

## 参考
- https://learn.microsoft.com/en-us/azure/api-management/export-rest-mcp-server
- https://learn.microsoft.com/en-us/azure/api-management/mcp-server-overview
- https://learn.microsoft.com/en-us/azure/api-management/secure-mcp-servers
