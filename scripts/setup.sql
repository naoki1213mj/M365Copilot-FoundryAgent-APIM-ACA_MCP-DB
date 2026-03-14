-- ========================================
-- 在庫管理システム サンプルデータ
-- テーブル: products, warehouses, inventory
-- ========================================

-- 依存関係の順序で DROP
IF OBJECT_ID('inventory', 'U') IS NOT NULL DROP TABLE inventory;
IF OBJECT_ID('products', 'U') IS NOT NULL DROP TABLE products;
IF OBJECT_ID('warehouses', 'U') IS NOT NULL DROP TABLE warehouses;

-- 商品マスタ
CREATE TABLE products (
    product_id INT IDENTITY(1,1) PRIMARY KEY,
    product_code NVARCHAR(20) NOT NULL UNIQUE,
    product_name NVARCHAR(100) NOT NULL,
    category NVARCHAR(50) NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    reorder_point INT NOT NULL DEFAULT 100,
    supplier NVARCHAR(100),
    is_active BIT NOT NULL DEFAULT 1,
    created_at DATETIME2 DEFAULT GETDATE()
);

-- 倉庫マスタ
CREATE TABLE warehouses (
    warehouse_id INT IDENTITY(1,1) PRIMARY KEY,
    warehouse_code NVARCHAR(10) NOT NULL UNIQUE,
    warehouse_name NVARCHAR(100) NOT NULL,
    region NVARCHAR(50) NOT NULL,
    capacity INT NOT NULL,
    is_active BIT NOT NULL DEFAULT 1
);

-- 在庫（商品×倉庫の在庫数量）
CREATE TABLE inventory (
    inventory_id INT IDENTITY(1,1) PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(product_id),
    warehouse_id INT NOT NULL REFERENCES warehouses(warehouse_id),
    quantity INT NOT NULL DEFAULT 0,
    reserved INT NOT NULL DEFAULT 0,
    available AS (quantity - reserved) PERSISTED,
    last_updated DATETIME2 DEFAULT GETDATE(),
    CONSTRAINT UQ_product_warehouse UNIQUE (product_id, warehouse_id)
);

-- ========================================
-- 倉庫データ (3拠点)
-- ========================================
INSERT INTO warehouses (warehouse_code, warehouse_name, region, capacity) VALUES
('KWS', N'川崎倉庫', N'関東', 50000),
('OSK', N'大阪倉庫', N'関西', 35000),
('FKO', N'福岡倉庫', N'九州', 20000);

-- ========================================
-- 商品データ (20品)
-- ========================================
INSERT INTO products (product_code, product_name, category, unit_price, reorder_point, supplier) VALUES
('PRD-001', N'収納ボックス 3段',          N'収納',     2980,  500, N'アイリスオーヤマ'),
('PRD-002', N'収納ケース 標準',            N'収納',     1480, 1500, N'天馬'),
('PRD-003', N'押入れ収納ケース 標準',      N'収納',     1980,  400, N'天馬'),
('PRD-004', N'冷感寝具パッド シングル',    N'寝具',     3980,  200, N'ニトリ'),
('PRD-005', N'マットレス ダブル',          N'寝具',    29800,   50, N'シモンズ'),
('PRD-006', N'標準枕',                    N'寝具',     1280,  800, N'西川'),
('PRD-007', N'掛け布団カバー',            N'寝具',     2480,  300, N'西川'),
('PRD-008', N'フライパン 26cm',           N'キッチン',  3280,  600, N'ティファール'),
('PRD-009', N'キッチン収納ラック',        N'キッチン',  4980,  400, N'山善'),
('PRD-010', N'保存容器 4点セット',        N'キッチン',  1680,  200, N'イワキ'),
('PRD-011', N'折りたたみテーブル',        N'家具',     8980,  300, N'山善'),
('PRD-012', N'デスクチェア 布張り',        N'家具',    15800,  200, N'オカムラ'),
('PRD-013', N'ローボード 150cm',          N'家具',    24800,  100, N'大塚家具'),
('PRD-014', N'2人掛けソファ',             N'家具',    49800,  150, N'カリモク'),
('PRD-015', N'デスクライト',              N'照明',     4580,  800, N'パナソニック'),
('PRD-016', N'シーリングライト 8畳',      N'照明',    12800,  200, N'パナソニック'),
('PRD-017', N'吸水バスマット',            N'バス用品',  1980,  300, N'soil'),
('PRD-018', N'ハンガー 10本組',           N'洗濯用品',   780, 2000, N'マワ'),
('PRD-019', N'ロールスクリーン',          N'インテリア', 5480,  200, N'タチカワ'),
('PRD-020', N'装飾グリーン',              N'インテリア', 2980,  100, N'ニトリ');

-- ========================================
-- 在庫データ (31行: KWS 12品, OSK 10品, FKO 9品)
-- 発注点割れが 8件含まれる
-- ========================================
INSERT INTO inventory (product_id, warehouse_id, quantity, reserved)
SELECT p.product_id, w.warehouse_id, v.quantity, v.reserved
FROM (VALUES
    -- 川崎倉庫 (KWS = warehouse_id 1)
    ('PRD-001', 'KWS', 1250,  30),
    ('PRD-002', 'KWS', 3400, 200),
    ('PRD-004', 'KWS',  340,  15),
    ('PRD-005', 'KWS',   45,   5),  -- 発注点割れ (50)
    ('PRD-008', 'KWS',  280,  10),
    ('PRD-010', 'KWS',   75,   0),  -- 発注点割れ (200)
    ('PRD-013', 'KWS',   95,   8),  -- 発注点割れ (100)
    ('PRD-015', 'KWS',  920,  50),
    ('PRD-016', 'KWS',  560,  20),
    ('PRD-017', 'KWS',  120,   0),  -- 発注点割れ (300)
    ('PRD-018', 'KWS', 2800, 100),
    ('PRD-020', 'KWS',   30,   5),  -- 発注点割れ (100)
    -- 大阪倉庫 (OSK = warehouse_id 2)
    ('PRD-001', 'OSK',  480,  20),
    ('PRD-002', 'OSK', 1200,  80),
    ('PRD-003', 'OSK',  180,   0),  -- 発注点割れ (400)
    ('PRD-006', 'OSK', 2200, 150),
    ('PRD-009', 'OSK',  890,  30),
    ('PRD-011', 'OSK',  670,  25),
    ('PRD-012', 'OSK',  450,  15),
    ('PRD-014', 'OSK',  320,  10),
    ('PRD-018', 'OSK', 2800, 200),
    ('PRD-019', 'OSK',  440,  10),
    -- 福岡倉庫 (FKO = warehouse_id 3)
    ('PRD-003', 'FKO',  350,  10),
    ('PRD-006', 'FKO',  680,  30),
    ('PRD-007', 'FKO',  120,   5),  -- 発注点割れ (300)
    ('PRD-008', 'FKO', 1600,  80),
    ('PRD-011', 'FKO',  280,  10),
    ('PRD-012', 'FKO',  180,   0),  -- 発注点割れ (200)
    ('PRD-015', 'FKO', 1180,  40),
    ('PRD-019', 'FKO',  310,  15),
    ('PRD-020', 'FKO',  150,   5)
) AS v(product_code, warehouse_code, quantity, reserved)
INNER JOIN products p ON p.product_code = v.product_code
INNER JOIN warehouses w ON w.warehouse_code = v.warehouse_code;

-- MCP 用読み取り専用ロール
BEGIN TRY
    IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'mcp_readonly_role')
        CREATE ROLE mcp_readonly_role
END TRY
BEGIN CATCH
    -- ロールが既存の場合は無視
    PRINT 'Role mcp_readonly_role already exists'
END CATCH;
GRANT SELECT ON products TO mcp_readonly_role;
GRANT SELECT ON warehouses TO mcp_readonly_role;
GRANT SELECT ON inventory TO mcp_readonly_role;
GRANT VIEW DATABASE STATE TO mcp_readonly_role;
