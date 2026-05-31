from code_intel.process_files.splitter import Chunk


class VectorStore:
    buffer: list[Chunk] = []
    max_buffer_chunks: int = 50

    def store_chunk(self, chunk: Chunk):
        print(f"Stored  {chunk.project_folder}/{chunk.file_name}, from {chunk.start_line} to {chunk.end_line}")
        self.buffer.append(chunk)
        if len(self.buffer) > self.max_buffer_chunks:
            self.flush()

    def flush(self):
        print("flushed")
        self.buffer = []
