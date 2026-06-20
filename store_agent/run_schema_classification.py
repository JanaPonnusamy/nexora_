
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
