"""在庫参照 API ユニットテスト

DB 接続をモックしてエンドポイント単位でテスト。
Azure 接続なしでローカル実行可能。
"""

import os
import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# テスト用環境変数
os.environ.setdefault("SQL_SERVER_FQDN", "localhost")
os.environ.setdefault("SQL_DATABASE_NAME", "test_db")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from main import app  # noqa: E402

client = TestClient(app)


# ================================================
# ヘルパー: モック DB カーソル
# ================================================
def _make_mock_cursor(rows: list[tuple], columns: list[str]):
    """pyodbc の cursor を模擬する MagicMock を返す。"""
    cursor = MagicMock()
    cursor.description = [(col,) for col in columns]
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = rows[0] if rows else None
    return cursor


# ================================================
# /health
# ================================================
class TestHealth:
    @patch("main.get_db")
    def test_health_ok(self, mock_get_db):
        mock_conn = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


# ================================================
# /products
# ================================================
PRODUCT_COLS = [
    "product_code",
    "product_name",
    "category",
    "unit_price",
    "reorder_point",
    "supplier",
    "is_active",
]
SAMPLE_PRODUCT = ("PRD-001", "Wireless Mouse", "Electronics", 2980.0, 500, "Supplier-A", True)


class TestProducts:
    @patch("main.get_db")
    def test_list_products(self, mock_get_db):
        cursor = _make_mock_cursor([SAMPLE_PRODUCT], PRODUCT_COLS)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/products")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["product_code"] == "PRD-001"

    @patch("main.get_db")
    def test_list_products_with_category(self, mock_get_db):
        cursor = _make_mock_cursor([SAMPLE_PRODUCT], PRODUCT_COLS)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/products?category=Electronics")
        assert resp.status_code == 200

    @patch("main.get_db")
    def test_get_product_by_code(self, mock_get_db):
        cursor = _make_mock_cursor([SAMPLE_PRODUCT], PRODUCT_COLS)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/products/PRD-001")
        assert resp.status_code == 200
        assert resp.json()["product_code"] == "PRD-001"

    @patch("main.get_db")
    def test_get_product_not_found(self, mock_get_db):
        cursor = _make_mock_cursor([], PRODUCT_COLS)
        cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/products/INVALID")
        assert resp.status_code == 404


# ================================================
# /inventory
# ================================================
INVENTORY_COLS = [
    "product_code",
    "product_name",
    "category",
    "warehouse_code",
    "warehouse_name",
    "quantity",
    "reserved",
    "available",
    "reorder_point",
    "needs_reorder",
    "last_updated",
]
SAMPLE_INVENTORY = (
    "PRD-001",
    "Wireless Mouse",
    "Electronics",
    "WH-E",
    "East Warehouse",
    1250,
    30,
    1220,
    500,
    0,
    "2026-03-14",
)


class TestInventory:
    @patch("main.get_db")
    def test_list_inventory(self, mock_get_db):
        cursor = _make_mock_cursor([SAMPLE_INVENTORY], INVENTORY_COLS)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/inventory")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @patch("main.get_db")
    def test_list_inventory_filters(self, mock_get_db):
        cursor = _make_mock_cursor([SAMPLE_INVENTORY], INVENTORY_COLS)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/inventory?warehouse_code=WH-E&category=Electronics&low_stock_only=true")
        assert resp.status_code == 200

    def test_limit_validation(self):
        resp = client.get("/inventory?limit=0")
        assert resp.status_code == 422  # バリデーションエラー

        resp = client.get("/inventory?limit=999")
        assert resp.status_code == 422


# ================================================
# /inventory/alerts
# ================================================
ALERT_COLS = [
    "product_code",
    "product_name",
    "category",
    "warehouse_code",
    "warehouse_name",
    "quantity",
    "reserved",
    "available",
    "reorder_point",
    "shortage",
    "fill_rate",
    "supplier",
]
SAMPLE_ALERT = (
    "PRD-005",
    "27-inch Monitor",
    "Electronics",
    "WH-E",
    "East Warehouse",
    45,
    5,
    40,
    50,
    5,
    0.9,
    "Supplier-C",
)


class TestInventoryAlerts:
    @patch("main.get_db")
    def test_alerts(self, mock_get_db):
        cursor = _make_mock_cursor([SAMPLE_ALERT], ALERT_COLS)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/inventory/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["shortage"] == 5

    @patch("main.get_db")
    def test_alerts_sort_by_fill_rate(self, mock_get_db):
        cursor = _make_mock_cursor([SAMPLE_ALERT], ALERT_COLS)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/inventory/alerts?sort_by=fill_rate")
        assert resp.status_code == 200

    def test_alerts_invalid_sort(self):
        resp = client.get("/inventory/alerts?sort_by=invalid")
        assert resp.status_code == 422


# ================================================
# /warehouses
# ================================================
WAREHOUSE_COLS = [
    "warehouse_code",
    "warehouse_name",
    "region",
    "capacity",
    "item_count",
    "total_quantity",
    "total_reserved",
    "alert_count",
]
SAMPLE_WAREHOUSE = ("WH-E", "East Warehouse", "East Region", 50000, 12, 9630, 443, 3)


class TestWarehouses:
    @patch("main.get_db")
    def test_list_warehouses(self, mock_get_db):
        cursor = _make_mock_cursor([SAMPLE_WAREHOUSE], WAREHOUSE_COLS)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/warehouses")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["warehouse_code"] == "WH-E"

    @patch("main.get_db")
    def test_warehouse_stock(self, mock_get_db):
        stock_cols = [
            "product_code",
            "product_name",
            "category",
            "quantity",
            "reserved",
            "available",
            "reorder_point",
            "needs_reorder",
            "last_updated",
        ]
        stock_row = ("PRD-001", "Wireless Mouse", "Electronics", 1250, 30, 1220, 500, 0, "2026-03-14")

        # fetchone (倉庫存在確認) + fetchall (在庫データ)
        cursor = MagicMock()
        cursor.fetchone.return_value = ("East Warehouse",)
        cursor.description = [(col,) for col in stock_cols]
        cursor.fetchall.return_value = [stock_row]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/warehouses/WH-E/stock")
        assert resp.status_code == 200
        data = resp.json()
        assert data["warehouse_code"] == "WH-E"
        assert len(data["items"]) == 1
        assert len(data["category_summary"]) == 1

    @patch("main.get_db")
    def test_warehouse_not_found(self, mock_get_db):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.get("/warehouses/INVALID/stock")
        assert resp.status_code == 404


# ================================================
# OpenAPI spec
# ================================================
class TestOpenAPI:
    def test_openapi_json(self):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        assert spec["info"]["title"] == "在庫参照API"
        paths = list(spec["paths"].keys())
        assert "/products" in paths
        assert "/inventory" in paths
        assert "/inventory/alerts" in paths
        assert "/warehouses" in paths
