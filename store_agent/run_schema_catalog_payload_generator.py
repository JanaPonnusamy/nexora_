from store_agent.services.schema_catalog_payload_generator import (
    SchemaCatalogPayloadGenerator
)

def main():
    result = SchemaCatalogPayloadGenerator().generate()

    print("[OK] Schema Catalog Payload Generated")
    print(f"ROWS     : {result['payload_rows']}")
    print(f"OUTPUT   : {result['output_file']}")

if __name__ == "__main__":
    main()
