from store_agent.execution.execution_dispatcher import ExecutionDispatcher
from store_agent.execution.execution_context import ExecutionContext

def test_dispatcher():

    dispatcher = ExecutionDispatcher()

    result = dispatcher.dispatch(
        ExecutionContext(
            '1',
            '1',
            '1',
            'FULL_SYNC',
            'MANUAL'
        )
    )

    assert result.success is True
