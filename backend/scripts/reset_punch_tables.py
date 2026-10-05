"""Reset device-fed tables in Cosec_Nexora (clears test data). Masters untouched."""
from __future__ import annotations
import os
import pyodbc


def main() -> int:
    c = pyodbc.connect(
        f"DRIVER={{{os.getenv('DB_DRIVER','ODBC Driver 17 for SQL Server')}}};"
        f"SERVER={os.getenv('DB_SERVER')};DATABASE={os.getenv('DB_DATABASE')};"
        f"UID={os.getenv('DB_USERNAME')};PWD={os.getenv('DB_PASSWORD')};TrustServerCertificate=yes;",
        autocommit=True,
    )
    cur = c.cursor()
    cur.execute("DELETE FROM dbo.Mx_ATDEventTrn")
    if cur.tables(table="matrix_push_raw").fetchone():
        cur.execute("DELETE FROM dbo.matrix_push_raw")
    cur.execute("SELECT COUNT(*) FROM dbo.Mx_ATDEventTrn")
    print("Mx_ATDEventTrn rows after reset:", cur.fetchone()[0])
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
