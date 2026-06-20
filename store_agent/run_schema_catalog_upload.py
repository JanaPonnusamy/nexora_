from services.schema_catalog_upload_service import (
    SchemaCatalogUploadService
)


def main():

    result = (
        SchemaCatalogUploadService()
        .upload()
    )

    print()
    print("=" * 80)
    print("SYNC-025B-B")
    print("Schema Catalog Upload")
    print("=" * 80)

    print()

    for key, value in result.items():
        print(
            f"{key}: {value}"
        )


if __name__ == "__main__":
    main()

