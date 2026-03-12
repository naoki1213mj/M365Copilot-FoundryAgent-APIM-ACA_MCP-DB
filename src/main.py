"""在庫参照 API

Foundry Agent → APIM Standard v2 (MCP) → this API → Azure SQL Database
認証: DefaultAzureCredential + Entra トークンで Azure SQL に接続（Entra ID Only 認証）
ローカル開発: az login 済みなら DefaultAzureCredential が自動でトークンを取得
"""

import logging
import os
import struct
from contextlib import contextmanager
from typing import Optional

import pyodbc
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
app = FastAPI(
    title="在庫参照API",
    description="在庫コントロール用 REST API。SKU 検索、倉庫/カテゴリ絞り込み、発注点割れアラートに対応。APIM 経由で MCP サーバーとして公開され、Foundry エージェント / M365 Copilot から利用可能。",
    version="1.0.0",
)


def _get_mi_token() -> bytes:
    """DefaultAzureCredential で Azure SQL 用のアクセストークンを取得し、pyodbc attrs_before 用にエンコードする。"""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
    # pyodbc の SQL_COPT_SS_ACCESS_TOKEN (1256) に渡すバイナリ形式
    token_bytes = token.token.encode("utf-16-le")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


@contextmanager
def get_db():
    """DB 接続。DefaultAzureCredential で Entra ID トークン認証。"""
    server = os.environ["SQL_SERVER_FQDN"]
    db = os.environ["SQL_DATABASE_NAME"]
    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{server},1433;Database={db};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    conn = pyodbc.connect(conn_str, attrs_before={1256: _get_mi_token()})
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row) -> dict:
    return {
        "sku": row.sku,
        "product_name": row.product_name,
        "category": row.category,
        "warehouse": row.warehouse,
        "quantity": row.quantity,
        "reorder_point": row.reorder_point,
        "needs_reorder": row.quantity < row.reorder_point,
        "last_updated": str(row.last_updated),
    }


@app.get(
    "/inventory/{sku}",
    summary="SKUコードで在庫を1件検索する",
    description="指定 SKU（例: INV-001）の在庫情報を返します。needs_reorder が true なら発注推奨。",
    response_description="在庫情報",
)
def get_inventory_by_sku(sku: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory WHERE sku = ?", sku)
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"SKU '{sku}' は見つかりませんでした"
            )
        return row_to_dict(row)


@app.get(
    "/inventory",
    summary="在庫一覧を条件付きで取得する",
    description="warehouse で倉庫絞り込み、category でカテゴリ絞り込み、low_stock_only=true で発注点割れのみ。",
    response_description="在庫情報のリスト",
)
def list_inventory(
    warehouse: Optional[str] = Query(None, description="倉庫名（例: 川崎倉庫）"),
    category: Optional[str] = Query(None, description="カテゴリ（例: 寝具）"),
    low_stock_only: bool = Query(False, description="true で発注点割れの商品だけ返す"),
):
    with get_db() as conn:
        cursor = conn.cursor()
        q, p = "SELECT * FROM inventory WHERE 1=1", []
        if warehouse:
            q += " AND warehouse = ?"
            p.append(warehouse)
        if category:
            q += " AND category = ?"
            p.append(category)
        if low_stock_only:
            q += " AND quantity < reorder_point"
        cursor.execute(q + " ORDER BY sku", p)
        return [row_to_dict(r) for r in cursor.fetchall()]


@app.get("/health", include_in_schema=False)
def health():
    try:
        with get_db() as conn:
            conn.cursor().execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "auth": "entra_id"}
    except Exception as e:
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": str(e)}
        )
