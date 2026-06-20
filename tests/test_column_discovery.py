from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_has_get_columns():
    scanner = SchemaScanner()
    assert hasattr(scanner, "get_columns")
