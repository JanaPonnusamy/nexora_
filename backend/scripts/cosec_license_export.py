"""Export the latest COSEC license-update record to E:\\nexora\\cosec.txt.

Read-only. Reuses the existing COSEC connection from
``modules.time_report.database`` -- the one place COSEC credentials are read
from backend/.env (COSEC_DB_SERVER/DATABASE/USERNAME/PASSWORD) -- so no second
DB mechanism and no hard-coded credentials are introduced.

    backend/.venv/bin/python scripts/cosec_license_export.py

Any failure (missing config, unreachable DB, query error) is caught and written
into the same output file so the file always reflects the last run.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = Path(r"E:\nexora\cosec.txt")

_QUERY = """
    SELECT TOP 1
        NewLicenseKey,
        UpdateDate,
        LoginUser
    FROM Mx_LicenseUpdateTrn
    ORDER BY Id DESC
"""


def _write_output(text: str) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(text, encoding="utf-8")


def _format_record(row: dict) -> str:
    return (
        f"NewLicenseKey={row.get('NewLicenseKey')}\n"
        f"UpdateDate={row.get('UpdateDate')}\n"
        f"LoginUser={row.get('LoginUser')}\n"
    )


def fetch_latest_license() -> str:
    # Imported late: sys.path must include BACKEND_DIR first so `modules...`
    # resolves whether the script is run from repo root or backend/.
    sys.path.insert(0, str(BACKEND_DIR))
    from modules.time_report.database import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY)
        row = cur.fetchone()
        if row is None:
            return "No license update record found.\n"
        cols = [c[0] for c in cur.description]
        return _format_record(dict(zip(cols, row)))
    finally:
        conn.close()


def main() -> int:
    try:
        content = fetch_latest_license()
    except Exception as exc:  # noqa: BLE001 - any failure is reported to the file
        content = f"Error: failed to read COSEC license update record.\n{exc}\n"
        _write_output(content)
        print(content, end="")
        return 1

    _write_output(content)
    print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
