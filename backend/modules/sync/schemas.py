from pydantic import BaseModel
from typing import List, Optional


class ColumnSchema(BaseModel):
    column_name: str
    data_type: str
    max_length: Optional[int] = None
    precision_value: Optional[int] = None
    scale_value: Optional[int] = None
    is_nullable: bool
    is_identity: bool
    is_primary_key: bool
    ordinal_position: int


class TableSchema(BaseModel):
    schema_name: str
    table_name: str
    columns: List[ColumnSchema]


class SchemaRegisterRequest(BaseModel):
    store_id: str
    database_name: str
    tables: List[TableSchema]