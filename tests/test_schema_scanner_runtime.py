from store_agent.schema_scanner import SchemaScanner

def test_schema_scan_result():
    result = SchemaScanner().scan()

    assert "tables" in result
    assert "columns" in result
