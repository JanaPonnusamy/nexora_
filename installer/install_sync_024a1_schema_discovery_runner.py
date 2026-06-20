from pathlib import Path
from textwrap import dedent

print("=" * 50)
print("SYNC-024A.1 INSTALLER")
print("Schema Discovery Runner")
print("=" * 50)

project_root = Path(__file__).resolve().parent.parent

runner_file = project_root / "store_agent" / "run_schema_discovery.py"

runner_code = dedent("""
# SYNC-024A.1 generated runner
print("Schema Discovery Runner")
""")

runner_file.write_text(runner_code, encoding="utf-8")

print(f"[OK] Created: {runner_file}")
