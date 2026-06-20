from pathlib import Path
from textwrap import dedent

print("=" * 60)
print("SYNC-024B.1")
print("Schema Classification Catalog Runner")
print("=" * 60)

project_root = Path(__file__).resolve().parent.parent

target_file = (
    project_root
    / "store_agent"
    / "run_schema_classification_catalog.py"
)

code = dedent("""
from pathlib import Path

from schema_classification_catalog_generator import (
    SchemaClassificationCatalogGenerator
)


def main():

    schema_dir = (
        Path(__file__).parent
        / "schema"
    )

    snapshot_file = (
        schema_dir
        / "schema_snapshot.json"
    )

    output_file = (
        schema_dir
        / "schema_classification.json"
    )

    generator = (
        SchemaClassificationCatalogGenerator()
    )

    catalog = generator.generate(
        str(snapshot_file),
        str(output_file)
    )

    print("[OK] Classification Complete")
    print(f"OUTPUT : {output_file}")
    print(f"TABLES : {len(catalog)}")

    summary = {}

    for classification in catalog.values():

        summary[classification] = (
            summary.get(
                classification,
                0
            ) + 1
        )

    print()
    print("CLASSIFICATION SUMMARY")
    print("-" * 30)

    for key in sorted(summary.keys()):

        print(
            f"{key:<15} "
            f"{summary[key]}"
        )


if __name__ == "__main__":
    main()
""")

target_file.write_text(
    code,
    encoding="utf-8"
)

print(f"[OK] Created: {target_file}")
print()
print("SYNC-024B.1 INSTALL COMPLETE")