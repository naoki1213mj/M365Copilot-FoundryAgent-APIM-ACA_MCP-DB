"""setup.sql をEntra ID トークン認証で実行し、サンプルデータを投入する。"""

import os
import struct

import pyodbc
from azure.identity import DefaultAzureCredential

SERVER = os.environ["SQL_SERVER_FQDN"]
DATABASE = os.environ.get("SQL_DATABASE_NAME", "inventory_db")

cred = DefaultAzureCredential()
tok = cred.get_token("https://database.windows.net/.default")
token_bytes = tok.token.encode("utf-16-le")
token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

conn = pyodbc.connect(
    f"Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{SERVER},1433;"
    f"Database={DATABASE};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;",
    attrs_before={1256: token_struct},
)
conn.autocommit = True
cursor = conn.cursor()

with open("scripts/setup.sql", encoding="utf-8") as f:
    sql = f.read()

for stmt in sql.split(";"):
    stmt = stmt.strip()
    if stmt:
        try:
            cursor.execute(stmt)
        except Exception as e:
            print(f"Error: {e}\nStatement: {stmt[:80]}...")

# 確認
for table in ("products", "warehouses", "inventory"):
    cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 — テーブル名は固定リテラル
    count = cursor.fetchone()[0]
    print(f"  {table}: {count} rows")

conn.close()
