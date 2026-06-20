from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_has_identity_discovery():
    scanner = SchemaScanner()
    assert hasattr(scanner, "get_identity_columns")
