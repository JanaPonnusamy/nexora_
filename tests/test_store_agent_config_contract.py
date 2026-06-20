from store_agent.store_agent_config_contract import StoreAgentConfigContract

def test_contract_fields():
    assert "store_id" in StoreAgentConfigContract.REQUIRED_FIELDS
    assert "ho_api_url" in StoreAgentConfigContract.REQUIRED_FIELDS
