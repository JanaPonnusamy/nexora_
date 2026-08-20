"""Script to restore / un-dump `nexora_platform_dump (1).sql` into SQL Server (Docker or Remote).

Splits the SQL script into `GO`-delimited batches and executes them sequentially.
Usage:
    python restore_dump.py
"""

import os
import re
import sys
from dotenv import load_dotenv

load_dotenv()

# Add current dir to path to import database config
sys.path.insert(0, os.path.dirname(__file__))

from config.database import get_connection

DUMP_FILE = os.path.join(os.path.dirname(__file__), "nexora_platform_dump (1).sql")


def run_dump():
    if not os.path.exists(DUMP_FILE):
        print(f"Error: Dump file not found at {DUMP_FILE}")
        sys.exit(1)

    print(f"Reading dump file: {DUMP_FILE} ...")
    with open(DUMP_FILE, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split by 'GO' on its own line (case-insensitive)
    batches = re.split(r"^\s*GO\s*$", sql_content, flags=re.IGNORECASE | re.MULTILINE)

    print(f"Found {len(batches)} SQL batches to execute.")
    server = os.getenv("DB_SERVER", "127.0.0.1")

    # The dump creates its own database and issues `USE [...]`, so connect to
    # `master`: the target database does not exist yet on a fresh server.
    os.environ["DB_DATABASE"] = "master"
    print(f"Connecting to SQL Server at {server} (master)...")

    conn = get_connection()
    try:
        conn.autocommit = True
    except AttributeError:
        pass
    cursor = conn.cursor()

    success_count = 0
    error_count = 0

    for i, batch in enumerate(batches, start=1):
        clean_batch = batch.strip()
        if not clean_batch:
            continue

        try:
            cursor.execute(clean_batch)
            success_count += 1
            if i % 20 == 0 or i == len(batches):
                print(f"Processed batch {i}/{len(batches)}...")
        except Exception as ex:
            error_count += 1
            print(f"Warning in batch {i}: {ex}")

    cursor.close()
    conn.close()

    print("\n==========================================")
    print("Dump restore FAILED." if error_count else "Dump restore completed successfully!")
    print(f"Successful batches: {success_count}")
    print(f"Errors/Warnings:     {error_count}")
    print("==========================================")
    if error_count:
        sys.exit(1)


if __name__ == "__main__":
    run_dump()
