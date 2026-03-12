"""Container Apps の Managed Identity を SQL DB ユーザーとして登録し権限付与する。"""

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

# Container Apps MI ユーザー作成
try:
    cursor.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'inventory-api') "
        "CREATE USER [inventory-api] FROM EXTERNAL PROVIDER"
    )
    print("User [inventory-api] created or already exists")
except Exception as e:
    print(f"User creation error: {e}")

# 権限付与
for role in ("db_datareader", "db_datawriter"):
    try:
        cursor.execute(f"ALTER ROLE {role} ADD MEMBER [inventory-api]")
        print(f"  {role} granted")
    except Exception as e:
        print(f"  {role}: {e}")

conn.close()
print("Done!")
