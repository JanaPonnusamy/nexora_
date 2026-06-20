from store_agent.end_state_verification import EndStateVerification

def test_end_state_verification():
    assert EndStateVerification().verify() is True
