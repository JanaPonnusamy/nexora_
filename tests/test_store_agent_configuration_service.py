from store_agent.store_agent_config_contract import StoreAgentConfigContract

def test_contract_has_required_fields():
    assert len(StoreAgentConfigContract.REQUIRED_FIELDS) > 0
