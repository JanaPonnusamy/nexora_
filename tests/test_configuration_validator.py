from store_agent.configuration_validator import ConfigurationValidator

def test_configuration_validator():
    validator = ConfigurationValidator()

    assert validator.validate({
        "SQL_SERVER":"X",
        "SQL_DATABASE":"Y",
        "STORE_ID":"Z",
        "HO_API_URL":"A"
    }) is True
