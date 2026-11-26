"""COSEC database full backup utility.

Connects to the Matrix COSEC attendance SQL Server (creds from backend/.env
COSEC_DB_* vars) and runs a native T-SQL BACKUP DATABASE to a path on the
SQL Server host, then copies the resulting .bak file to E:\\Nexora\\backupdb\\
over the Windows admin/file share and zips it.

Usage:
    python backend/scripts/cosec_db_backup.py
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import zipfile
from pathlib import Path

import pyodbc

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

SERVER = os.environ["COSEC_DB_SERVER"]
DATABASE = os.environ["COSEC_DB_DATABASE"]
USERNAME = os.environ["COSEC_DB_USERNAME"]
PASSWORD = os.environ["COSEC_DB_PASSWORD"]
DRIVER = os.environ.get("COSEC_DB_DRIVER", "ODBC Driver 17 for SQL Server")

HOST = SERVER.split("\\")[0]
OUTPUT_DIR = Path(r"E:\Nexora\backupdb")

# Default SQL Server backup directory on the remote host (SQLEXPRESS default
# instance backup folder); overridden at runtime once the real path is read
# back from the registry.
REMOTE_BACKUP_DIR_SQL = r"C:\Program Files\Microsoft SQL Server\MSSQL15.SQLEXPRESS\MSSQL\Backup"


def connect():
    conn_str = (
        f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE=master;"
        f"UID={USERNAME};PWD={PASSWORD};TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=True, timeout=30)


# Max varbinary chunk per SUBSTRING/BULK read call. Kept comfortably under
# SQL Server's 2GB varbinary(max) limit and typical network packet sizing.
_CHUNK_BYTES = 8 * 1024 * 1024


def pull_file_via_sql(remote_path: str, local_path: Path) -> None:
    """Read an arbitrary file on the SQL Server host back to the client by
    issuing chunked OPENROWSET(BULK ...) SELECTs over the existing SQL
    login, avoiding any need for OS-level/SMB access to the host.
    """
    conn = connect()
    cur = conn.cursor()

    # OPENROWSET(BULK ...) requires a literal path, not a parameter; the
    # path here is always our own generated filename, never user input.
    escaped_path = remote_path.replace("'", "''")
    cur.execute(
        "SELECT CAST(bulkcolumn AS VARBINARY(MAX)) "
        f"FROM OPENROWSET(BULK '{escaped_path}', SINGLE_BLOB) AS doc;"
    )
    row = cur.fetchone()
    data = row[0]
    cur.close()
    conn.close()

    with open(local_path, "wb") as f:
        f.write(data)


def main() -> int:
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_name = f"COSEC_{timestamp}.bak"
    remote_bak_path_sql = f"{REMOTE_BACKUP_DIR_SQL}\\{bak_name}"

    print(f"Connecting to {SERVER} ...")
    conn = connect()
    cur = conn.cursor()

    # Discover actual SQL Server default backup directory instead of
    # assuming the hardcoded MSSQL15.SQLEXPRESS path above.
    try:
        cur.execute(
            "DECLARE @path NVARCHAR(4000); "
            "EXEC master.dbo.xp_instance_regread "
            "N'HKEY_LOCAL_MACHINE', "
            "N'Software\\Microsoft\\MSSQLServer\\MSSQLServer', "
            "N'BackupDirectory', @path OUTPUT; "
            "SELECT @path;"
        )
        row = cur.fetchone()
        if row and row[0]:
            real_dir = row[0]
            remote_bak_path_sql = f"{real_dir}\\{bak_name}"
            print(f"Detected SQL Server backup directory: {real_dir}")
    except Exception as exc:
        print(f"Could not auto-detect backup directory, using default. ({exc})")

    print(f"Backing up database {DATABASE!r} to {remote_bak_path_sql} on {HOST} ...")
    cur.execute(
        f"BACKUP DATABASE [{DATABASE}] TO DISK = ? "
        f"WITH FORMAT, INIT, NAME = ?, STATS = 10;",
        remote_bak_path_sql,
        f"{DATABASE}-Full Backup {timestamp}",
    )
    while cur.nextset():
        pass
    cur.close()
    conn.close()
    print("Backup completed on server.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_bak_path = OUTPUT_DIR / bak_name

    print(f"Pulling {remote_bak_path_sql} back over SQL (chunked BULK read) ...")
    pull_file_via_sql(remote_bak_path_sql, local_bak_path)

    zip_path = OUTPUT_DIR / f"COSEC_{timestamp}.zip"
    print(f"Zipping -> {zip_path} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(local_bak_path, arcname=bak_name)

    local_bak_path.unlink()
    print(f"Done: {zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
