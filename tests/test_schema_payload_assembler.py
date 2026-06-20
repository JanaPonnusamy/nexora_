from store_agent.schema_payload_assembler import SchemaPayloadAssembler

def test_schema_payload_assembler():
    assembler = SchemaPayloadAssembler()

    payload = assembler.assemble(
        "STORE001",
        "DB001",
        {"tables":[]}
    )

    assert payload["store_id"] == "STORE001"
    assert payload["database_name"] == "DB001"
    assert "tables" in payload
