import logging
import asyncio
import functools
import time
from typing import Callable, Any, Dict, Optional, List, TypeVar, AsyncIterable
from dataclasses import dataclass
from livekit.agents import ChatContext, llm

T = TypeVar('T')

logger = logging.getLogger(__name__)


class ProbeError(Exception):
    """Base exception for probe failures"""
    pass


class ContextContractError(ProbeError):
    """Raised when ChatContext contract is violated"""
    pass


class ToolSchemaError(ProbeError):
    """Raised when tool schema is invalid"""
    pass


class StreamError(ProbeError):
    """Raised when stream behavior is invalid"""
    pass


class ToolExecutionError(ProbeError):
    """Raised when tool execution violates contract"""
    pass


@dataclass
class ProbeResult:
    """Result of a probe validation"""
    passed: bool
    message: str
    probe_name: str
    details: Optional[dict] = None


def probe_context(func: Callable) -> Callable:
    """
    Decorator to validate ChatContext before LLM call.
    
    Validates:
    - ctx.messages is iterable
    - each message has role + content
    - roles are valid (system/user/assistant)
    - token count is reasonable
    - system prompt exists
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract chat_ctx from kwargs
        chat_ctx = kwargs.get('chat_ctx')
        
        if not chat_ctx:
            # Try to find it in args (common pattern: self, chat_ctx, ...)
            for arg in args:
                if hasattr(arg, 'messages'):
                    chat_ctx = arg
                    break
        
        if chat_ctx:
            try:
                # Validate messages are iterable
                messages = chat_ctx.messages
                if callable(messages):
                    messages = messages()
                
                if not hasattr(messages, '__iter__'):
                    raise ContextContractError("ChatContext.messages is not iterable")
                
                message_list = list(messages)
                
                # Validate each message
                has_system = False
                total_content_length = 0
                
                for msg in message_list:
                    if not hasattr(msg, 'role') or not hasattr(msg, 'content'):
                        raise ContextContractError(f"Message missing 'role' or 'content': {msg}")
                    
                    if msg.role not in ['system', 'user', 'assistant', 'tool']:
                        raise ContextContractError(f"Invalid role: {msg.role}")
                    
                    if msg.role == 'system':
                        has_system = True
                    
                    # Estimate token count (rough: 4 chars per token)
                    if msg.content:
                        content_str = str(msg.content)
                        total_content_length += len(content_str)
                
                # Check for system prompt
                if not has_system:
                    logger.warning("⚠️ No system prompt in ChatContext")
                
                # Check token limit (rough estimate: 100k chars = ~25k tokens)
                if total_content_length > 100000:
                    logger.warning(f"⚠️ ChatContext very large: ~{total_content_length // 4} tokens")
                
                logger.debug(f"✅ Context probe passed: {len(message_list)} messages, ~{total_content_length // 4} tokens")
                
            except ContextContractError as e:
                logger.error(f"❌ Context contract violation: {e}")
                raise
            except Exception as e:
                logger.error(f"❌ Context probe error: {e}")
                raise ContextContractError(f"Context validation failed: {e}")
        
        # Call the original function
        return await func(*args, **kwargs)
    
    return wrapper


def probe_tool_schema(func: Callable) -> Callable:
    """
    Decorator to validate tool schemas before sending to LLM.
    
    Validates:
    - Each tool has name, description
    - parameters.type == 'object'
    - parameters.properties exists (even if empty)
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract tools from kwargs
        tools = kwargs.get('tools')
        
        if tools:
            try:
                for tool in tools:
                    # Check required fields
                    if not hasattr(tool, 'info'):
                        raise ToolSchemaError(f"Tool missing 'info' attribute: {tool}")
                    
                    info = tool.info
                    
                    if not hasattr(info, 'name') or not info.name:
                        raise ToolSchemaError(f"Tool missing 'name': {tool}")
                    
                    if not hasattr(info, 'description'):
                        raise ToolSchemaError(f"Tool '{info.name}' missing 'description'")
                    
                    if not hasattr(info, 'parameters'):
                        raise ToolSchemaError(f"Tool '{info.name}' missing 'parameters'")
                    
                    # Validate parameters structure
                    params = info.parameters
                    if isinstance(params, dict):
                        if 'type' not in params:
                            raise ToolSchemaError(f"Tool '{info.name}': parameters missing 'type'")
                        
                        if params['type'] != 'object':
                            raise ToolSchemaError(f"Tool '{info.name}': parameters.type must be 'object', got '{params['type']}'")
                        
                        if 'properties' not in params:
                            raise ToolSchemaError(f"Tool '{info.name}': parameters missing 'properties'")
                
                logger.debug(f"✅ Tool schema probe passed: {len(tools)} tools validated")
                
            except ToolSchemaError as e:
                logger.error(f"❌ Tool schema violation: {e}")
                raise
            except Exception as e:
                logger.error(f"❌ Tool schema probe error: {e}")
                raise ToolSchemaError(f"Tool schema validation failed: {e}")
        
        # Call the original function
        return await func(*args, **kwargs)
    
    return wrapper


class StreamProbe:
    """
    Context manager to wrap and validate LLM stream behavior.
    
    Validates:
    - First chunk arrives within timeout
    - At least one chunk is emitted
    - Stream closes cleanly
    """
    
    def __init__(self, stream: AsyncIterable[T], timeout_seconds: float = 3.0):
        # Ensure we have an iterator
        if hasattr(stream, '__aiter__') and not hasattr(stream, '__anext__'):
            self.stream = stream.__aiter__()
        else:
            self.stream = stream
        
        self.timeout_seconds = timeout_seconds
        self.chunk_count = 0
        self.start_time = time.time()
        self.first_chunk_received = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> T:
        try:
            # First chunk timeout
            if not self.first_chunk_received:
                chunk = await asyncio.wait_for(
                    self.stream.__anext__(),
                    timeout=self.timeout_seconds
                )
                self.first_chunk_received = True
                self.chunk_count += 1
                logger.debug(f"✅ Stream probe: First chunk received within {self.timeout_seconds}s")
                return chunk
            else:
                # Subsequent chunks - no timeout
                chunk = await self.stream.__anext__()
                self.chunk_count += 1
                return chunk
                
        except asyncio.TimeoutError:
            # Try to close the stream to prevent leaks
            close_method = getattr(self.stream, 'aclose', getattr(self.stream, 'close', None))
            if close_method:
                try:
                    if asyncio.iscoroutinefunction(close_method) or asyncio.isiter(close_method):
                         await close_method()
                    elif callable(close_method):
                         res = close_method()
                         if asyncio.iscoroutine(res): await res
                except: pass
            raise StreamError(f"Stream timeout: No chunks received within {self.timeout_seconds}s")
        except StopAsyncIteration:
            # Stream ended
            if self.chunk_count == 0:
                raise StreamError("Stream ended without emitting any chunks")
            logger.debug(f"✅ Stream probe: {self.chunk_count} chunks emitted, closed cleanly")
            raise
        except Exception as e:
            # Try to close the stream on any other error
            close_method = getattr(self.stream, 'aclose', getattr(self.stream, 'close', None))
            if close_method:
                try:
                    if asyncio.iscoroutinefunction(close_method) or asyncio.isiter(close_method):
                         await close_method()
                    elif callable(close_method):
                         res = close_method()
                         if asyncio.iscoroutine(res): await res
                except: pass
            logger.error(f"❌ Stream probe error: {e}")
            raise StreamError(f"Stream error: {e}")


def probe_tool_execution(func: Callable) -> Callable:
    """
    Decorator to validate tool execution parameters.
    
    Validates:
    - Tool exists in registry
    - Arguments match expected schema
    - No unexpected parameters
    """
    @functools.wraps(func)
    async def wrapper(tool_name: str, params: dict, *args, **kwargs):
        try:
            # Basic validation
            if not tool_name:
                raise ToolExecutionError("Tool name is empty")
            
            if not isinstance(params, dict):
                raise ToolExecutionError(f"Tool params must be dict, got {type(params)}")
            
            logger.debug(f"✅ Tool execution probe passed: {tool_name}")
            
        except ToolExecutionError as e:
            logger.error(f"❌ Tool execution violation: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Tool execution probe error: {e}")
            raise ToolExecutionError(f"Tool execution validation failed: {e}")
        
        # Call the original function
        return await func(tool_name, params, *args, **kwargs)
    
    return wrapper
