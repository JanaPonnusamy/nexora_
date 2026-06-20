from store_agent.schema_catalog_builder import SchemaCatalogBuilder

def test_schema_catalog_builder():
    builder = SchemaCatalogBuilder()

    result = builder.build([], [], [], [])

    assert "tables" in result
    assert "columns" in result
    assert "primary_keys" in result
    assert "identity_columns" in result
