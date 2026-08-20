"""Generates a standalone .sql file that updates NMA's SubLocation directly,
gated on UnitDescription = 'OIN', with no Python/Excel round-trip needed at
run time -- for running straight in SSMS (or sqlcmd) against the NMA branch
server (MSERVER-PC\\SQLEXPRESS / RShopaidLive).

Pulls the (ProductCode, SubLocation) pairs from the same Excel source used by
nma_branch_sublocation_update_from_excel.py, embeds them as a VALUES table,
and only updates rows that are both UnitDescription='OIN' and currently
blank/NULL -- identical guard to the Python script, just expressed in plain
SQL.

Usage:
    backend/.venv/Scripts/python backend/scripts/generate_nma_direct_update_sql.py <source.xlsx> [output.sql]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.nma_branch_sublocation_update_from_excel import read_excel_pairs


def _sql_str(s):
    return "'" + s.replace("'", "''") + "'"


def build_sql(pairs):
    values = ",\n    ".join(f"({pc}, {_sql_str(subloc)})" for pc, subloc in pairs)
    return f"""-- NMA branch SubLocation update, direct SQL (no Python needed).
-- Run against: MSERVER-PC\\SQLEXPRESS / RShopaidLive (dbo.Stores.StoreName='NMA')
-- Only writes Products.SubLocation, only where UnitDescription='OIN' AND
-- SubLocation is currently NULL/blank/'NULL'. No other columns/tables touched.

BEGIN TRANSACTION;

DECLARE @Pairs TABLE (ProductCode INT PRIMARY KEY, ProposedSubLocation VARCHAR(50));
INSERT INTO @Pairs (ProductCode, ProposedSubLocation) VALUES
    {values};

UPDATE p
SET p.SubLocation = v.ProposedSubLocation
OUTPUT inserted.ProductCode, inserted.ProductName, deleted.SubLocation AS OldSubLocation, inserted.SubLocation AS NewSubLocation
FROM Products p
JOIN @Pairs v ON v.ProductCode = p.ProductCode
WHERE UPPER(LTRIM(RTRIM(ISNULL(p.UnitDescription, '')))) = 'OIN'
  AND LTRIM(RTRIM(ISNULL(p.SubLocation, ''))) IN ('', 'NULL');

-- Review the OUTPUT rows above, then either:
COMMIT TRANSACTION;
-- or, if something looks wrong, run this instead of the COMMIT above:
-- ROLLBACK TRANSACTION;
"""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: generate_nma_direct_update_sql.py <source.xlsx> [output.sql]")
        sys.exit(1)
    pairs = read_excel_pairs(sys.argv[1])
    out_path = sys.argv[2] if len(sys.argv) > 2 else "nma_sublocation_update.sql"
    Path(out_path).write_text(build_sql(pairs), encoding="utf-8")
    print(f"Wrote {len(pairs)} pairs -> {out_path}")
