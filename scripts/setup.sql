IF OBJECT_ID('inventory', 'U') IS NOT NULL DROP TABLE inventory;
CREATE TABLE inventory (
    sku NVARCHAR(20) PRIMARY KEY, product_name NVARCHAR(100) NOT NULL,
    category NVARCHAR(50) NOT NULL, warehouse NVARCHAR(50) NOT NULL,
    quantity INT NOT NULL, reorder_point INT NOT NULL,
    last_updated DATETIME2 DEFAULT GETDATE()
);
INSERT INTO inventory (sku, product_name, category, warehouse, quantity, reorder_point) VALUES
('INV-001',N'収納ボックス 3段',N'収納',N'川崎倉庫',1250,500),
('INV-002',N'収納ケース 標準',N'収納',N'川崎倉庫',3400,1500),
('INV-003',N'押入れ収納ケース 標準',N'収納',N'大阪倉庫',180,400),
('INV-004',N'冷感寝具パッド シングル',N'寝具',N'川崎倉庫',340,200),
('INV-005',N'マットレス ダブル',N'寝具',N'川崎倉庫',45,50),
('INV-006',N'標準枕',N'寝具',N'大阪倉庫',2200,800),
('INV-007',N'掛け布団カバー',N'寝具',N'福岡倉庫',120,300),
('INV-008',N'フライパン 26cm',N'キッチン',N'福岡倉庫',1600,600),
('INV-009',N'キッチン収納ラック',N'キッチン',N'大阪倉庫',890,400),
('INV-010',N'保存容器 4点セット',N'キッチン',N'川崎倉庫',75,200),
('INV-011',N'折りたたみテーブル',N'家具',N'大阪倉庫',670,300),
('INV-012',N'デスクチェア 布張り',N'家具',N'福岡倉庫',180,200),
('INV-013',N'ローボード 150cm',N'家具',N'川崎倉庫',95,100),
('INV-014',N'2人掛けソファ',N'家具',N'大阪倉庫',320,150),
('INV-015',N'デスクライト',N'照明',N'福岡倉庫',2100,800),
('INV-016',N'シーリングライト 8畳',N'照明',N'川崎倉庫',560,200),
('INV-017',N'吸水バスマット',N'バス用品',N'川崎倉庫',120,300),
('INV-018',N'ハンガー 10本組',N'洗濯用品',N'大阪倉庫',5600,2000),
('INV-019',N'ロールスクリーン',N'インテリア',N'福岡倉庫',440,200),
('INV-020',N'装飾グリーン',N'インテリア',N'川崎倉庫',30,100);
