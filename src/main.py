"""在庫参照 API

Foundry Agent → APIM Standard v2 (MCP) → this API → Azure SQL Database
各 REST エンドポイントが APIM 経由で MCP ツールとして公開される。
認証: DefaultAzureCredential + Entra トークンで Azure SQL に接続（Entra ID Only 認証）
ローカル開発: az login 済みなら DefaultAzureCredential が自動でトークンを取得
"""

import logging
import os
import struct
import time
from contextlib import contextmanager
from typing import Literal

import pyodbc
from azure.core.exceptions import AzureError
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

# --- 構造化ログ ---
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("inventory_api")


def configure_observability() -> None:
    """Application Insights 接続文字列がある場合だけ OpenTelemetry を有効化する。"""
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not connection_string:
        return

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(
        connection_string=connection_string,
        logger_name="inventory_api",
        enable_live_metrics=False,
    )


configure_observability()

app = FastAPI(
    title="在庫参照API",
    description=(
        "在庫管理 REST API。商品検索、倉庫別在庫照会、発注点割れアラートに対応。"
        "APIM 経由で MCP サーバーとして公開され、Foundry エージェント / M365 Copilot から利用可能。"
    ),
    version="2.0.0",
)


# --- OTel リクエスト計測ミドルウェア ---
@app.middleware("http")
async def observability_middleware(request: Request, call_next) -> Response:
    """各リクエストの処理時間を計測してレスポンスヘッダーに付与する。"""
    start = time.monotonic()
    response: Response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 2)
    response.headers["X-Duration-Ms"] = str(duration_ms)
    logger.info(
        "request completed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


# --- DB 接続 ---
def _get_mi_token() -> bytes:
    """DefaultAzureCredential で Azure SQL 用のアクセストークンを取得し、pyodbc attrs_before 用にエンコードする。"""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
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
    conn.setdecoding(pyodbc.SQL_CHAR, encoding="utf-8")
    conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-16-le")
    conn.setencoding(encoding="utf-8")
    try:
        yield conn
    finally:
        conn.close()


def _rows_to_dicts(cursor) -> list[dict]:
    """pyodbc Row を dict のリストに変換する。"""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _row_to_dict(cursor, row) -> dict:
    """pyodbc Row 1件を dict に変換する。"""
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


# ======================================
# 商品マスタ
# ======================================
@app.get(
    "/products",
    summary="商品一覧を取得する",
    description=("商品マスタの一覧を返します。category で絞り込み可能。各商品の reorder_point（発注点）も含まれます。"),
    response_description="商品情報のリスト",
)
def list_products(
    category: str | None = Query(None, description="カテゴリで絞り込み（例: Electronics, Office Supplies）"),
    limit: int = Query(100, ge=1, le=500, description="最大取得件数"),
):
    with get_db() as conn:
        cursor = conn.cursor()
        q = "SELECT TOP(?) product_code, product_name, category, unit_price, reorder_point, supplier, is_active FROM products WHERE is_active = 1"
        p: list = [limit]
        if category:
            q += " AND category = ?"
            p.append(category)
        q += " ORDER BY product_code"
        cursor.execute(q, p)
        return _rows_to_dicts(cursor)


@app.get(
    "/products/{code}",
    summary="商品コードで商品を1件検索する",
    description="指定した商品コード（例: PRD-001）の商品情報を返します。",
    response_description="商品情報",
)
def get_product_by_code(code: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT product_code, product_name, category, unit_price, reorder_point, supplier, is_active "
            "FROM products WHERE product_code = ?",
            code,
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"商品コード '{code}' は見つかりませんでした")
        return _row_to_dict(cursor, row)


# ======================================
# 在庫
# ======================================
@app.get(
    "/inventory",
    summary="在庫一覧を条件付きで取得する",
    description=(
        "商品×倉庫の在庫情報を返します。warehouse_code で倉庫絞り込み、"
        "category でカテゴリ絞り込み、low_stock_only=true で発注点割れのみ。"
    ),
    response_description="在庫情報のリスト",
)
def list_inventory(
    warehouse_code: str | None = Query(None, description="倉庫コード（例: WH-E, WH-C, WH-W）"),
    category: str | None = Query(None, description="カテゴリ（例: Electronics）"),
    low_stock_only: bool = Query(False, description="true で発注点割れの商品だけ返す"),
    limit: int = Query(100, ge=1, le=500, description="最大取得件数"),
):
    with get_db() as conn:
        cursor = conn.cursor()
        q = """
            SELECT TOP(?)
                p.product_code, p.product_name, p.category,
                w.warehouse_code, w.warehouse_name,
                i.quantity, i.reserved, i.available,
                p.reorder_point,
                CASE WHEN i.quantity < p.reorder_point THEN 1 ELSE 0 END AS needs_reorder,
                i.last_updated
            FROM inventory i
            INNER JOIN products p ON p.product_id = i.product_id
            INNER JOIN warehouses w ON w.warehouse_id = i.warehouse_id
            WHERE p.is_active = 1
        """
        p: list = [limit]
        if warehouse_code:
            q += " AND w.warehouse_code = ?"
            p.append(warehouse_code)
        if category:
            q += " AND p.category = ?"
            p.append(category)
        if low_stock_only:
            q += " AND i.quantity < p.reorder_point"
        q += " ORDER BY p.product_code, w.warehouse_code"
        cursor.execute(q, p)
        return _rows_to_dicts(cursor)


@app.get(
    "/inventory/alerts",
    summary="発注点割れの商品一覧を取得する",
    description=(
        "在庫数が発注点を下回っている商品の一覧を返します。不足数量 (shortage) と充足率 (fill_rate) を含みます。"
    ),
    response_description="発注点割れ商品のリスト",
)
def get_inventory_alerts(
    category: str | None = Query(None, description="カテゴリで絞り込み"),
    sort_by: Literal["shortage", "fill_rate"] = Query("shortage", description="ソート基準"),
):
    with get_db() as conn:
        cursor = conn.cursor()
        q = """
            SELECT
                p.product_code, p.product_name, p.category,
                w.warehouse_code, w.warehouse_name,
                i.quantity, i.reserved, i.available,
                p.reorder_point,
                (p.reorder_point - i.quantity) AS shortage,
                CAST(i.quantity AS FLOAT) / NULLIF(p.reorder_point, 0) AS fill_rate,
                p.supplier
            FROM inventory i
            INNER JOIN products p ON p.product_id = i.product_id
            INNER JOIN warehouses w ON w.warehouse_id = i.warehouse_id
            WHERE p.is_active = 1 AND i.quantity < p.reorder_point
        """
        p: list = []
        if category:
            q += " AND p.category = ?"
            p.append(category)
        order = "shortage DESC" if sort_by == "shortage" else "fill_rate ASC"
        q += f" ORDER BY {order}"
        cursor.execute(q, p)
        return _rows_to_dicts(cursor)


# ======================================
# 倉庫
# ======================================
@app.get(
    "/warehouses",
    summary="倉庫一覧と在庫サマリを取得する",
    description=("全倉庫の情報と、各倉庫の在庫品目数・総在庫数・発注点割れ件数を返します。"),
    response_description="倉庫一覧と在庫サマリ",
)
def list_warehouses():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                w.warehouse_code, w.warehouse_name, w.region, w.capacity,
                COUNT(i.inventory_id) AS item_count,
                COALESCE(SUM(i.quantity), 0) AS total_quantity,
                COALESCE(SUM(i.reserved), 0) AS total_reserved,
                SUM(CASE WHEN i.quantity < p.reorder_point THEN 1 ELSE 0 END) AS alert_count
            FROM warehouses w
            LEFT JOIN inventory i ON i.warehouse_id = w.warehouse_id
            LEFT JOIN products p ON p.product_id = i.product_id
            WHERE w.is_active = 1
            GROUP BY w.warehouse_code, w.warehouse_name, w.region, w.capacity
            ORDER BY w.warehouse_code
        """)
        return _rows_to_dicts(cursor)


@app.get(
    "/warehouses/{code}/stock",
    summary="特定倉庫の在庫詳細を取得する",
    description="指定した倉庫コード（例: WH-E）の全在庫をカテゴリ別サマリ付きで返します。",
    response_description="倉庫別在庫詳細",
)
def get_warehouse_stock(
    code: str,
    category: str | None = Query(None, description="カテゴリで絞り込み"),
):
    with get_db() as conn:
        cursor = conn.cursor()
        # 倉庫存在確認
        cursor.execute("SELECT warehouse_name FROM warehouses WHERE warehouse_code = ?", code)
        wh = cursor.fetchone()
        if not wh:
            raise HTTPException(status_code=404, detail=f"倉庫コード '{code}' は見つかりませんでした")

        q = """
            SELECT
                p.product_code, p.product_name, p.category,
                i.quantity, i.reserved, i.available,
                p.reorder_point,
                CASE WHEN i.quantity < p.reorder_point THEN 1 ELSE 0 END AS needs_reorder,
                i.last_updated
            FROM inventory i
            INNER JOIN products p ON p.product_id = i.product_id
            INNER JOIN warehouses w ON w.warehouse_id = i.warehouse_id
            WHERE w.warehouse_code = ? AND p.is_active = 1
        """
        p: list = [code]
        if category:
            q += " AND p.category = ?"
            p.append(category)
        q += " ORDER BY p.category, p.product_code"
        cursor.execute(q, p)
        items = _rows_to_dicts(cursor)

        # カテゴリ別サマリを計算
        summary: dict[str, dict] = {}
        for item in items:
            cat = item["category"]
            if cat not in summary:
                summary[cat] = {"category": cat, "item_count": 0, "total_quantity": 0, "alert_count": 0}
            summary[cat]["item_count"] += 1
            summary[cat]["total_quantity"] += item["quantity"]
            if item["needs_reorder"]:
                summary[cat]["alert_count"] += 1

        return {
            "warehouse_code": code,
            "warehouse_name": wh[0],
            "items": items,
            "category_summary": list(summary.values()),
        }


# ======================================
# ヘルスチェック
# ======================================
@app.get("/health", include_in_schema=False)
def health():
    try:
        with get_db() as conn:
            conn.cursor().execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "auth": "entra_id"}
    except (pyodbc.Error, AzureError) as e:
        logger.exception("health check failed")
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})
