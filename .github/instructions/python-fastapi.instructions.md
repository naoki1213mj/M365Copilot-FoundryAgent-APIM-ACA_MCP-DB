---
name: Python FastAPI 規約
description: FastAPI 在庫 API のコーディングルール。APIM MCP メタデータに直結する OpenAPI description の書き方を強制。
applyTo: "src/**/*.py"
---
# Python / FastAPI Rules
- Python 3.12. Type hints on all signatures.
- FastAPI: always set summary, description, response_description — APIM uses these as MCP tool metadata. Poor descriptions = poor agent tool selection.
- Use Query() with description for all query parameters. The description becomes the MCP tool parameter description.
- DB: pyodbc via contextmanager.
- Return structured dicts with computed fields (needs_reorder).
- HTTPException: Japanese detail for business errors (404, 400).
- No print(). Use logging module. No secrets in code.
