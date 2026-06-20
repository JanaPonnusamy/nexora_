
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
