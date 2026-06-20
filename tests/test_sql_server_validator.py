from store_agent.sql_server_validator import SqlServerValidator

def test_sql_server_validator():

    validator = SqlServerValidator()

    assert validator.validate_version_text(
        "Microsoft SQL Server 2014"
    ) is True
