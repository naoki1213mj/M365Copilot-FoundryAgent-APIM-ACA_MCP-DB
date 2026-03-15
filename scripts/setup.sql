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
('WH-E', N'East Warehouse',    N'East Region',    50000),
('WH-C', N'Central Warehouse', N'Central Region', 35000),
('WH-W', N'West Warehouse',    N'West Region',    20000);

-- ========================================
-- 商品データ (20品)
-- ========================================
INSERT INTO products (product_code, product_name, category, unit_price, reorder_point, supplier) VALUES
('PRD-001', N'Wireless Mouse',             N'Electronics',      2980,  500, N'Supplier-A'),
('PRD-002', N'USB-C Hub 7-port',           N'Electronics',      1480, 1500, N'Supplier-A'),
('PRD-003', N'Noise Cancelling Headset',   N'Electronics',      1980,  400, N'Supplier-B'),
('PRD-004', N'Ergonomic Keyboard',         N'Electronics',      3980,  200, N'Supplier-B'),
('PRD-005', N'27-inch Monitor',            N'Electronics',     29800,   50, N'Supplier-C'),
('PRD-006', N'Ballpoint Pen 10-pack',      N'Office Supplies',  1280,  800, N'Supplier-D'),
('PRD-007', N'A4 Copy Paper 500-sheet',    N'Office Supplies',  2480,  300, N'Supplier-D'),
('PRD-008', N'Whiteboard Marker Set',      N'Office Supplies',  3280,  600, N'Supplier-E'),
('PRD-009', N'Desk Organizer',             N'Office Supplies',  4980,  400, N'Supplier-E'),
('PRD-010', N'Sticky Notes Assorted',      N'Office Supplies',  1680,  200, N'Supplier-F'),
('PRD-011', N'Standing Desk',              N'Furniture',        8980,  300, N'Supplier-G'),
('PRD-012', N'Office Chair Mesh',          N'Furniture',       15800,  200, N'Supplier-G'),
('PRD-013', N'Bookshelf 5-tier',           N'Furniture',       24800,  100, N'Supplier-H'),
('PRD-014', N'Meeting Table 6-seat',       N'Furniture',       49800,  150, N'Supplier-H'),
('PRD-015', N'LED Desk Lamp',              N'Lighting',         4580,  800, N'Supplier-I'),
('PRD-016', N'Ceiling Light Panel',        N'Lighting',        12800,  200, N'Supplier-I'),
('PRD-017', N'Power Strip 6-outlet',       N'Accessories',      1980,  300, N'Supplier-J'),
('PRD-018', N'Cable Management Kit',       N'Accessories',       780, 2000, N'Supplier-J'),
('PRD-019', N'Webcam HD 1080p',            N'Peripherals',      5480,  200, N'Supplier-K'),
('PRD-020', N'Portable Speaker',           N'Peripherals',      2980,  100, N'Supplier-K');

-- ========================================
-- 在庫データ (31行: WH-E 12品, WH-C 10品, WH-W 9品)
-- 発注点割れが 8件含まれる
-- ========================================
INSERT INTO inventory (product_id, warehouse_id, quantity, reserved)
SELECT p.product_id, w.warehouse_id, v.quantity, v.reserved
FROM (VALUES
    -- East Warehouse (WH-E = warehouse_id 1)
    ('PRD-001', 'WH-E', 1250,  30),
    ('PRD-002', 'WH-E', 3400, 200),
    ('PRD-004', 'WH-E',  340,  15),
    ('PRD-005', 'WH-E',   45,   5),  -- below reorder point (50)
    ('PRD-008', 'WH-E',  280,  10),
    ('PRD-010', 'WH-E',   75,   0),  -- below reorder point (200)
    ('PRD-013', 'WH-E',   95,   8),  -- below reorder point (100)
    ('PRD-015', 'WH-E',  920,  50),
    ('PRD-016', 'WH-E',  560,  20),
    ('PRD-017', 'WH-E',  120,   0),  -- below reorder point (300)
    ('PRD-018', 'WH-E', 2800, 100),
    ('PRD-020', 'WH-E',   30,   5),  -- below reorder point (100)
    -- Central Warehouse (WH-C = warehouse_id 2)
    ('PRD-001', 'WH-C',  480,  20),
    ('PRD-002', 'WH-C', 1200,  80),
    ('PRD-003', 'WH-C',  180,   0),  -- below reorder point (400)
    ('PRD-006', 'WH-C', 2200, 150),
    ('PRD-009', 'WH-C',  890,  30),
    ('PRD-011', 'WH-C',  670,  25),
    ('PRD-012', 'WH-C',  450,  15),
    ('PRD-014', 'WH-C',  320,  10),
    ('PRD-018', 'WH-C', 2800, 200),
    ('PRD-019', 'WH-C',  440,  10),
    -- West Warehouse (WH-W = warehouse_id 3)
    ('PRD-003', 'WH-W',  350,  10),
    ('PRD-006', 'WH-W',  680,  30),
    ('PRD-007', 'WH-W',  120,   5),  -- below reorder point (300)
    ('PRD-008', 'WH-W', 1600,  80),
    ('PRD-011', 'WH-W',  280,  10),
    ('PRD-012', 'WH-W',  180,   0),  -- below reorder point (200)
    ('PRD-015', 'WH-W', 1180,  40),
    ('PRD-019', 'WH-W',  310,  15),
    ('PRD-020', 'WH-W',  150,   5)
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
