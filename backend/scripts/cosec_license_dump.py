"""Dump the latest COSEC licence-update record to a plain text file.

Read-only: runs a single ``SELECT TOP 1`` against ``Mx_LicenseUpdateTrn`` on the
COSEC database and writes the newest row to ``E:\\nexora\\cosec.txt``.

It reuses the existing COSEC connection the Time Report module already owns
(``modules.time_report.database.get_connection``), so credentials come only from
backend/.env (COSEC_DB_SERVER/DATABASE/USERNAME/PASSWORD) — nothing is
hard-coded and no second connection mechanism is introduced.

    backend/.venv/Scripts/python scripts/cosec_license_dump.py
    backend/.venv/Scripts/python scripts/cosec_license_dump.py --out E:\\nexora\\cosec.txt

Any failure (missing config, DB unreachable, query error) is caught and written
into the same file so the output always reflects the last attempt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path(r"E:\nexora\cosec.txt")

QUERY = """
SELECT TOP 1
    NewLicenseKey,
    UpdateDate,
    LoginUser
FROM Mx_LicenseUpdateTrn
ORDER BY Id DESC
"""


def fetch_latest_license() -> dict | None:
    """Return the newest licence-update row as a dict, or None if the table is empty.

    Uses the shared read-only COSEC connection. Imported late so sys.path is set
    before the module (which pulls in backend/.env) loads.
    """
    sys.path.insert(0, str(BACKEND_DIR))
    from modules.time_report.database import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(QUERY)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))
    finally:
        conn.close()


def render(record: dict | None) -> str:
    if record is None:
        return "No license update record found.\n"
    return (
        f"NewLicenseKey={record.get('NewLicenseKey')}\n"
        f"UpdateDate={record.get('UpdateDate')}\n"
        f"LoginUser={record.get('LoginUser')}\n"
    )


def write_output(out_path: Path, text: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    try:
        record = fetch_latest_license()
        text = render(record)
    except Exception as exc:  # noqa: BLE001 - any failure must still land in the file
        text = f"ERROR: failed to read COSEC license update record.\n{type(exc).__name__}: {exc}\n"
        write_output(args.out, text)
        print(text, end="", file=sys.stderr)
        return 1

    write_output(args.out, text)
    print(f"wrote {args.out}")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
