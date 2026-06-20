from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_exists():
    scanner = SchemaScanner()
    assert scanner is not None
