from store_agent.execution.ho_table_creation_client import HOTableCreationClient

class TableCreationOrchestrator:

    def execute(self, execution_id):

        result = (
            HOTableCreationClient()
            .build(execution_id)
        )

        return {
            "success": True,
            "result": result
        }
