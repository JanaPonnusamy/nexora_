
from store_agent.runtime_bootstrap_verification import (
    RuntimeBootstrapVerification
)

def test_runtime_bootstrap_verification():

    verifier = RuntimeBootstrapVerification()

    result = verifier.build_status(
        True,
        True,
        True,
        True,
        True
    )

    assert result["runtime_ready"] is True
