
import logging
import os
from typing import Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from core.memory.hybrid_memory_manager import HybridMemoryManager
from core.memory.memory_models import MemorySource

logger = logging.getLogger(__name__)

class MemoryIngestor(FileSystemEventHandler):
    """
    Auto-ingestion service for knowledge files.
    Watches ~/.maya/knowledge/ and indexes new/modified files.
    """
    
    def __init__(self, watch_directory: str = None, memory_manager: HybridMemoryManager = None):
        self.watch_directory = watch_directory or os.path.expanduser("~/.maya/knowledge")
        if not memory_manager:
            raise ValueError("MemoryIngestor requires memory_manager injection")
        self.memory_manager = memory_manager
        self.observer: Optional[Observer] = None
        self._running = False
        self._started = False
        
        # Create watch directory if it doesn't exist
        os.makedirs(self.watch_directory, exist_ok=True)
        
        logger.info(f"MemoryIngestor initialized, watching: {self.watch_directory}")
    
    async def start(self):
        """Start watching the directory."""
        if self._running:
            logger.warning("MemoryIngestor already running")
            return

        self.observer = Observer()
        self.observer.schedule(self, self.watch_directory, recursive=True)
        try:
            self.observer.start()
        except Exception:
            self._running = False
            self._started = False
            self.observer = None
            raise

        self._running = True
        self._started = True
        logger.info(f"Started watching {self.watch_directory}")
    
    async def stop(self):
        """Stop watching the directory gracefully."""
        if not self._running:
            # Keep shutdown observability consistent even when ingestor never started.
            logger.info("MemoryIngestor stopped gracefully (already idle)")
            return

        self._running = False
        if self.observer:
            self.observer.stop()
            if self._started and self.observer.is_alive():
                # Join directly with a timeout; the executor-based join leaks a
                # live asyncio worker thread that keeps pytest/process exit open.
                self.observer.join(timeout=5.0)
            self.observer = None
        self._started = False
        logger.info("MemoryIngestor stopped gracefully")
    
    def on_created(self, event: FileSystemEvent):
        """Handle file creation events."""
        if not event.is_directory and self._is_supported_file(event.src_path):
            logger.info(f"New file detected: {event.src_path}")
            self._ingest_file(event.src_path)
    
    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events."""
        if not event.is_directory and self._is_supported_file(event.src_path):
            logger.info(f"File modified: {event.src_path}")
            self._ingest_file(event.src_path)
    
    def _is_supported_file(self, file_path: str) -> bool:
        """Check if file type is supported."""
        supported_extensions = ['.txt', '.md']
        return any(file_path.endswith(ext) for ext in supported_extensions)
    
    def _ingest_file(self, file_path: str):
        """Read and index a file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Chunk large files
            chunks = self._chunk_text(content, max_chunk_size=1000)
            
            for i, chunk in enumerate(chunks):
                if chunk.strip():  # Skip empty chunks
                    self.memory_manager.store_file_content(
                        file_path=file_path,
                        content=chunk,
                        metadata={
                            "chunk_index": i,
                            "total_chunks": len(chunks)
                        }
                    )
            
            logger.info(f"Ingested {file_path} ({len(chunks)} chunks)")
            
        except Exception as e:
            logger.error(f"Failed to ingest {file_path}: {e}")
    
    def _chunk_text(self, text: str, max_chunk_size: int = 1000) -> list[str]:
        """
        Split text into chunks for better retrieval.
        Tries to split on paragraph boundaries.
        """
        if len(text) <= max_chunk_size:
            return [text]
        
        chunks = []
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= max_chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def index_existing_files(self):
        """Index all existing files in the watch directory."""
        logger.info("Indexing existing files...")
        count = 0
        
        for root, _, files in os.walk(self.watch_directory):
            for file in files:
                file_path = os.path.join(root, file)
                if self._is_supported_file(file_path):
                    self._ingest_file(file_path)
                    count += 1
        
        logger.info(f"Indexed {count} existing files")
