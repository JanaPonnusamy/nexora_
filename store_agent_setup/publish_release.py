"""Publish a built NexoraStoreAgent.exe as the current release for watchdogs.

    python -m store_agent_setup.publish_release <version> [--notes "..."]
    python -m store_agent_setup.publish_release <version> --exe path\\to.exe

Copies the exe into backend/agent_releases/<version>/NexoraStoreAgent.exe,
records its sha256 + size in dbo.agent_releases, and marks it ``is_current``
(the previous current release, if any, is un-marked - never deleted, so a
rollback is just re-publishing an old version). Every watchdog polling
/agent/watchdog/state picks up the new version within one cycle (60s).
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

import pyodbc

REPO = Path(__file__).resolve().parent.parent
DEFAULT_EXE = REPO / "dist" / "NexoraStoreAgent.exe"
RELEASES_DIR = REPO / "backend" / "agent_releases"

_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=192.168.10.73;DATABASE=NEXORA_PLATFORM;"
    "UID=sa;PWD=Admin123;TrustServerCertificate=yes;"
)


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish(version, exe_path, notes=None):
    exe_path = Path(exe_path)
    if not exe_path.is_file():
        raise SystemExit(f"exe not found: {exe_path}")

    dest_dir = RELEASES_DIR / version
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "NexoraStoreAgent.exe"
    shutil.copy2(exe_path, dest)

    sha256 = _sha256_of(dest)
    size = dest.stat().st_size

    conn = pyodbc.connect(_CONN_STR)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dbo.agent_releases SET is_current = 0 WHERE is_current = 1")
        cur.execute(
            """
            MERGE dbo.agent_releases AS T
            USING (SELECT ? AS version) AS S ON T.version = S.version
            WHEN MATCHED THEN UPDATE SET
                file_name = ?, sha256 = ?, file_size = ?, notes = ?, is_current = 1
            WHEN NOT MATCHED THEN INSERT
                (version, file_name, sha256, file_size, notes, is_current)
                VALUES (?, ?, ?, ?, ?, 1);
            """,
            (version, "NexoraStoreAgent.exe", sha256, size, notes,
             version, "NexoraStoreAgent.exe", sha256, size, notes),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"published {version}")
    print(f"  file:   {dest}")
    print(f"  sha256: {sha256}")
    print(f"  size:   {size} bytes")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--exe", default=str(DEFAULT_EXE))
    parser.add_argument("--notes", default=None)
    args = parser.parse_args(argv)
    publish(args.version, args.exe, args.notes)


if __name__ == "__main__":
    main(sys.argv[1:])
