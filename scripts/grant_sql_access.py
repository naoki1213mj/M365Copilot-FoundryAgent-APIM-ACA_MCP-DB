"""Azure SQL へ Entra ID で接続し、指定 principal に DB ロールを付与する。"""

import argparse
import struct

import pyodbc
from azure.identity import DefaultAzureCredential

SQL_ACCESS_TOKEN_OPTION = 1256


def build_access_token() -> bytes:
    """Azure SQL 用アクセストークンを pyodbc 形式へ変換する。"""
    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
    encoded = token.token.encode("utf-16-le")
    return struct.pack(f"<I{len(encoded)}s", len(encoded), encoded)


def build_connection_string(server: str, database: str) -> str:
    """ODBC Driver 18 を使う Azure SQL 接続文字列を返す。"""
    return (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )


def grant_reader_role(server: str, database: str, principal_name: str) -> None:
    """指定 principal に contained user と db_datareader を付与する。"""
    connection = pyodbc.connect(
        build_connection_string(server, database),
        attrs_before={SQL_ACCESS_TOKEN_OPTION: build_access_token()},
    )
    connection.autocommit = True

    try:
        cursor = connection.cursor()
        cursor.execute(
            f"IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '{principal_name}') "
            f"CREATE USER [{principal_name}] FROM EXTERNAL PROVIDER;"
        )
        cursor.execute(
            "IF NOT EXISTS ("
            "SELECT 1 "
            "FROM sys.database_role_members rm "
            "JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id "
            "JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id "
            f"WHERE r.name = 'db_datareader' AND m.name = '{principal_name}'"
            ") ALTER ROLE [db_datareader] ADD MEMBER ["
            f"{principal_name}];"
        )
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grant db_datareader to an Entra principal"
    )
    parser.add_argument("--server", required=True, help="Azure SQL server FQDN")
    parser.add_argument("--database", required=True, help="Database name")
    parser.add_argument(
        "--principal-name", required=True, help="Entra principal display name"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    grant_reader_role(args.server, args.database, args.principal_name)
    print(args.principal_name)


if __name__ == "__main__":
    main()
