from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_has_primary_key_discovery():
    scanner = SchemaScanner()
    assert hasattr(scanner, "get_primary_keys")
