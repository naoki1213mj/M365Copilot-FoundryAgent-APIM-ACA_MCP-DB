---
description: "新しい在庫クエリエンドポイントを追加する"
mode: agent
tools: ['codebase']
---
src/main.py に新しい GET エンドポイントを追加してください: {{query_description}}

既存の get_inventory_by_sku / list_inventory のパターンに従う。summary/description を丁寧に（APIM MCP メタデータ用）。パラメータ化 SQL、contextmanager、needs_reorder 計算フィールド、日本語エラーメッセージ。
