from pathlib import Path

print("=" * 50)
print("SYNC-024B.1 INSTALLER")
print("Schema Classification Runner")
print("=" * 50)

project_root = Path(__file__).resolve().parent.parent

runner_file = project_root / "store_agent" / "run_schema_classification.py"

runner_code = """
from pathlib import Path
from schema_classification_engine import SchemaClassificationEngine

def main():
    root = Path(__file__).parent

    snapshot_file = root / "schema" / "schema_snapshot.json"
    output_file = root / "schema" / "schema_classification.json"

    engine = SchemaClassificationEngine()

    results = engine.classify(
        str(snapshot_file),
        str(output_file)
    )

    print("[OK] Classification Complete")
    print(f"[OK] Output: {output_file}")

    for category, tables in results.items():
        print(f"{category}: {len(tables)}")

if __name__ == "__main__":
    main()
"""

runner_file.write_text(runner_code, encoding="utf-8")

print(f"[OK] Created: {runner_file}")
print("SYNC-024B.1 INSTALL COMPLETE")
