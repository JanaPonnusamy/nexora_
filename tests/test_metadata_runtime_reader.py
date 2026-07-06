
from store_agent.runtime.metadata_runtime_reader import MetadataRuntimeReader

def test_metadata_reader():
    reader = MetadataRuntimeReader()
    tables = reader.get_tables()
    assert len(tables) > 0
