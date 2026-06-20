from services.sync_schema_catalog_generator import SyncSchemaCatalogGenerator

def main():
    result = SyncSchemaCatalogGenerator().generate()
    print(result)

if __name__ == "__main__":
    main()
