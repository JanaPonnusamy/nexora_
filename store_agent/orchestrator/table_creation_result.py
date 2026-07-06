class TableCreationResult:

    def __init__(
        self,
        success=True,
        tables_created=0,
        columns_created=0,
        message=''
    ):
        self.success = success
        self.tables_created = tables_created
        self.columns_created = columns_created
        self.message = message
