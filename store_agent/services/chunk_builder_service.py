class ChunkBuilderService:
    """SYNC-034 Chunk Builder Engine."""

    def __init__(self, chunk_size=1000):
        self.chunk_size = chunk_size

    def build(self, rows):
        chunks = []
        for index in range(0, len(rows), self.chunk_size):
            chunks.append(rows[index:index + self.chunk_size])
        return chunks
