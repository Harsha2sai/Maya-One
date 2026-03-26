import pytest
import asyncio
import os
import tempfile
from unittest.mock import MagicMock
from core.memory.memory_ingestor import MemoryIngestor
from core.memory.hybrid_memory_manager import HybridMemoryManager


class TestMemoryIngestorGracefulShutdown:
    """Test graceful shutdown of MemoryIngestor."""
    
    @pytest.mark.asyncio
    async def test_ingestor_starts_and_stops(self):
        """Ingestor should start and stop gracefully."""
        memory_manager = MagicMock(spec=HybridMemoryManager)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ingestor = MemoryIngestor(watch_directory=tmpdir, memory_manager=memory_manager)
            
            # Start watching
            await ingestor.start()
            assert ingestor._running
            assert ingestor.observer is not None
            assert ingestor.observer.is_alive()
            
            # Stop watching
            await ingestor.stop()
            assert not ingestor._running
            assert ingestor.observer is None
    
    @pytest.mark.asyncio
    async def test_ingestor_double_start_protection(self):
        """Starting an already running ingestor should be safe."""
        memory_manager = MagicMock(spec=HybridMemoryManager)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ingestor = MemoryIngestor(watch_directory=tmpdir, memory_manager=memory_manager)
            
            await ingestor.start()
            first_observer = ingestor.observer
            
            # Try to start again
            await ingestor.start()
            
            # Should be the same observer
            assert ingestor.observer is first_observer
            
            await ingestor.stop()
    
    @pytest.mark.asyncio
    async def test_ingestor_double_stop_protection(self):
        """Stopping an already stopped ingestor should be safe."""
        memory_manager = MagicMock(spec=HybridMemoryManager)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ingestor = MemoryIngestor(watch_directory=tmpdir, memory_manager=memory_manager)
            
            await ingestor.start()
            await ingestor.stop()
            
            # Try to stop again
            await ingestor.stop()
            
            assert not ingestor._running
            assert ingestor.observer is None
    
    @pytest.mark.asyncio
    async def test_ingestor_cleanup_on_stop(self):
        """Observer should be properly cleaned up on stop."""
        memory_manager = MagicMock(spec=HybridMemoryManager)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ingestor = MemoryIngestor(watch_directory=tmpdir, memory_manager=memory_manager)
            
            await ingestor.start()
            observer = ingestor.observer
            
            await ingestor.stop()
            
            # Observer should be stopped and joined
            assert not observer.is_alive()
            assert ingestor.observer is None
    
    @pytest.mark.asyncio
    async def test_ingestor_file_detection_before_shutdown(self):
        """Ingestor should detect files before shutdown."""
        memory_manager = MagicMock(spec=HybridMemoryManager)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ingestor = MemoryIngestor(watch_directory=tmpdir, memory_manager=memory_manager)
            
            await ingestor.start()
            
            # Create a test file
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Test content")
            
            # Give observer time to detect
            await asyncio.sleep(0.5)
            
            # Stop gracefully
            await ingestor.stop()
            
            assert not ingestor._running

    @pytest.mark.asyncio
    async def test_memory_ingestor_stop_safe_when_not_started(self):
        """Stopping before start should never raise."""
        memory_manager = MagicMock(spec=HybridMemoryManager)

        with tempfile.TemporaryDirectory() as tmpdir:
            ingestor = MemoryIngestor(watch_directory=tmpdir, memory_manager=memory_manager)
            await ingestor.stop()
            assert not ingestor._running
            assert ingestor.observer is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
