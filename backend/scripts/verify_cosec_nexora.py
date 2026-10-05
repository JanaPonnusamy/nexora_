"""Verify the replicated Cosec_Nexora target DB (read-only)."""
from __future__ import annotations
import os
import pyodbc


def conn():
    return pyodbc.connect(
        f"DRIVER={{{os.getenv('DB_DRIVER','ODBC Driver 17 for SQL Server')}}};"
        f"SERVER={os.getenv('DB_SERVER')};DATABASE={os.getenv('DB_DATABASE')};"
        f"UID={os.getenv('DB_USERNAME')};PWD={os.getenv('DB_PASSWORD')};TrustServerCertificate=yes;",
        autocommit=True,
    )


def main() -> int:
    c = conn(); cur = c.cursor()
    print("DB:", os.getenv("DB_SERVER"), "/", os.getenv("DB_DATABASE"))
    cur.execute("SELECT name FROM sys.tables ORDER BY name")
    tables = [r.name for r in cur.fetchall()]
    print("tables:", tables)
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM dbo.[{t}]")
        print(f"  {t}: {cur.fetchone()[0]} rows")
    cur.execute("""SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='Mx_ATDEventTrn'""")
    print("Mx_ATDEventTrn columns:", cur.fetchone()[0])
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
