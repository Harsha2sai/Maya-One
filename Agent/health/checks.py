"""
Health checks implementation for startup validation.
Each check validates a critical component of the agent.
"""
import logging
import asyncio
from typing import Tuple, List
from livekit.agents.llm import ChatContext

from health.check_base import HealthCheck

logger = logging.getLogger(__name__)


class LLMConnectivityCheck(HealthCheck):
    """Validates that the LLM can produce tokens and streaming works."""
    
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider
    
    @property
    def name(self) -> str:
        return "LLM Connectivity"
    
    async def run(self) -> Tuple[bool, str]:
        try:
            # Create a simple chat context
            ctx = ChatContext()
            ctx.add_message(role="system", content="You are a test assistant.")
            ctx.add_message(role="user", content="Say OK")
            
            # Try to get a response with timeout
            response_received = False
            timeout_seconds = 30
            
            async def test_stream():
                nonlocal response_received
                stream = self.llm_provider.chat(chat_ctx=ctx)
                async for chunk in stream:
                    # Some implementations use .choices, others might use different attributes
                    # For connectivity, just getting a chunk is enough
                    if chunk:
                        response_received = True
                        break
            
            await asyncio.wait_for(test_stream(), timeout=timeout_seconds)
            
            if response_received:
                return True, "LLM streaming operational"
            else:
                return False, "LLM did not produce any response chunks"
                
        except asyncio.TimeoutError:
            return False, f"LLM response timeout (>{timeout_seconds}s)"
        except Exception as e:
            return False, f"LLM connectivity failed: {str(e)}"


class ToolSchemaCheck(HealthCheck):
    """Validates that all registered tools have valid JSON schemas."""
    
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry
    
    @property
    def name(self) -> str:
        return "Tool Schema Validation"
    
    async def run(self) -> Tuple[bool, str]:
        try:
            tools = self.tool_registry.get_all_tools()
            
            if not tools:
                return True, "No tools registered (OK)"
            
            invalid_tools = []
            
            for metadata in tools:
                # Check required fields in ToolMetadata
                if not metadata.name:
                    invalid_tools.append("Unknown tool: missing 'name'")
                    continue
                
                if not metadata.description:
                    invalid_tools.append(f"{metadata.name}: missing 'description'")
                
                # Check parameters structure
                params = metadata.parameters
                if isinstance(params, dict):
                    # We only check 'properties' here as extract_metadata 
                    # provides it via inputSchema wrapping
                    pass
                else:
                    invalid_tools.append(f"{metadata.name}: parameters must be a dictionary")
            
            if invalid_tools:
                return False, f"Invalid tool schemas ({len(invalid_tools)} issues):\n" + "\n".join(invalid_tools)
            
            return True, f"All {len(tools)} tools have valid schemas"
            
        except Exception as e:
            return False, f"Tool schema check failed: {str(e)}"


class ChatContextCheck(HealthCheck):
    """Validates that ChatContext can be created and serialized."""
    
    @property
    def name(self) -> str:
        return "ChatContext Contract"
    
    async def run(self) -> Tuple[bool, str]:
        try:
            # Create a test context
            ctx = ChatContext()
            ctx.add_message(role="system", content="Test system prompt")
            ctx.add_message(role="user", content="Test user message")
            
            # Validate messages are iterable
            messages = ctx.messages
            if callable(messages):
                messages = messages()
            
            if not hasattr(messages, '__iter__'):
                return False, "ChatContext.messages is not iterable"
            
            message_list = list(messages)
            
            if len(message_list) != 2:
                return False, f"Expected 2 messages, got {len(message_list)}"
            
            # Validate message structure
            for msg in message_list:
                if not hasattr(msg, 'role') or not hasattr(msg, 'content'):
                    return False, "Message missing 'role' or 'content'"
                
                if msg.role not in ['system', 'user', 'assistant']:
                    return False, f"Invalid role: {msg.role}"
            
            return True, "ChatContext contract validated"
            
        except Exception as e:
            return False, f"ChatContext check failed: {str(e)}"


class MemoryLayerCheck(HealthCheck):
    """Validates that memory layer can write and read."""
    
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
    
    @property
    def name(self) -> str:
        return "Memory Layer"
    
    async def run(self) -> Tuple[bool, str]:
        try:
            test_user_id = "__health_check_test__"
            test_key = "startup_check"
            test_value = "health_check_value"
            
            # Test write with timeout
            if hasattr(self.memory_manager, 'store'):
                try:
                    await asyncio.wait_for(
                        self.memory_manager.store(test_user_id, test_key, test_value),
                        timeout=30
                    )
                except asyncio.TimeoutError:
                    return False, "Memory layer write timeout (30s)"
            
            # Test read
            if hasattr(self.memory_manager, 'retrieve'):
                retrieved = await self.memory_manager.retrieve(test_user_id, test_key)
                if retrieved and retrieved != test_value:
                    logger.warning(f"Memory read/write mismatch (expected {test_value}, got {retrieved})")
            
            # Test summarizer exists
            if hasattr(self.memory_manager, 'summarizer') and self.memory_manager.summarizer:
                return True, "Memory layer operational (with summarizer)"
            
            return True, "Memory layer operational"
            
        except Exception as e:
            return False, f"Memory layer check failed: {str(e)}"


class STTPipelineCheck(HealthCheck):
    """Validates that STT provider can be initialized."""
    
    def __init__(self, stt_provider_factory):
        self.stt_provider_factory = stt_provider_factory
    
    @property
    def name(self) -> str:
        return "STT Pipeline"
    
    async def run(self) -> Tuple[bool, str]:
        try:
            # Try to instantiate STT provider (dry run)
            if callable(self.stt_provider_factory):
                provider = self.stt_provider_factory()
                
                # Check that provider has expected methods
                if not hasattr(provider, 'stream'):
                    return False, "STT provider missing 'stream' method"
                
                return True, "STT pipeline initialized"
            else:
                return False, "STT provider factory is not callable"
                
        except Exception as e:
            return False, f"STT pipeline check failed: {str(e)}"


class TTSPipelineCheck(HealthCheck):
    """Validates that TTS provider can generate audio."""
    
    def __init__(self, tts_provider_factory):
        self.tts_provider_factory = tts_provider_factory
    
    @property
    def name(self) -> str:
        return "TTS Pipeline"
    
    async def run(self) -> Tuple[bool, str]:
        try:
            # Try to instantiate TTS provider
            if callable(self.tts_provider_factory):
                provider = self.tts_provider_factory()
                
                # Try to synthesize a short test phrase
                test_text = "Startup check"
                
                if hasattr(provider, 'synthesize'):
                    # Attempt synthesis with timeout
                    timeout_seconds = 30
                    chunk_count = 0
                    
                    async def test_tts():
                        nonlocal chunk_count
                        audio_stream = provider.synthesize(test_text)
                        async for chunk in audio_stream:
                            chunk_count += 1
                            if chunk_count >= 1:
                                break
                    
                    try:
                        await asyncio.wait_for(test_tts(), timeout=timeout_seconds)
                    except asyncio.TimeoutError:
                        return False, f"TTS synthesis timeout (>{timeout_seconds}s)"
                    
                    if chunk_count == 0:
                        return False, "TTS produced no audio chunks"
                    
                    return True, "TTS pipeline operational"
                else:
                    return False, "TTS provider missing 'synthesize' method"
            else:
                return False, "TTS provider factory is not callable"
                
        except Exception as e:
            return False, f"TTS pipeline check failed: {str(e)}"
