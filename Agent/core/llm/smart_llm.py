import logging
import asyncio
import copy
import random
import time
from typing import Callable, Awaitable, Any, List, Tuple

from livekit.agents.llm import (
    LLM, LLMStream, ChatContext, ChatMessage, ChatChunk, ToolChoice, ChoiceDelta
)
from livekit.agents.types import (
    NotGivenOr, NOT_GIVEN, DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions
)

from probes.runtime.probe_engine import probe_context, StreamProbe
from telemetry.session_monitor import get_session_monitor
from chaos.fault_injection import get_chaos_config

logger = logging.getLogger(__name__)

class SmartLLM(LLM):
    """
    Wraps the LLM to inject dynamic tools and context per turn, bypassing LiveKit's
    static tool initialization which causes schema validation errors.
    Proxies streaming calls to the underlying LLM using a custom LLMStream.
    """

    def __init__(self, base_llm: LLM, context_builder: Callable[[str], Awaitable[Tuple[str, List[Any]]]]):
        super().__init__()
        self.base_llm = base_llm
        self.context_builder = context_builder
        
    @property
    def model(self) -> str:
        return self.base_llm.model
        
    @property
    def provider(self) -> str:
        return self.base_llm.provider

    @property
    def label(self) -> str:
        return f"SmartLLM({self.base_llm.label})"

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: List[Any] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> "SmartLLMStream":
        return SmartLLMStream(
            llm=self,
            base_llm=self.base_llm,
            context_builder=self.context_builder,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
            parallel_tool_calls=parallel_tool_calls,
            tool_choice=tool_choice,
            extra_kwargs=extra_kwargs
        )

class SmartLLMStream(LLMStream):
    def __init__(
        self, 
        llm: SmartLLM, 
        base_llm: LLM,
        context_builder, 
        parallel_tool_calls: NotGivenOr[bool],
        tool_choice: NotGivenOr[ToolChoice],
        extra_kwargs: NotGivenOr[dict[str, Any]],
        **kwargs
    ):
        super().__init__(llm, **kwargs)
        self.base_llm = base_llm
        self.context_builder = context_builder
        self.parallel_tool_calls = parallel_tool_calls
        self.tool_choice = tool_choice
        self.extra_kwargs = extra_kwargs

    async def _run(self):
        # 0. Start Telemetry
        from telemetry.session_monitor import get_session_monitor
        monitor = get_session_monitor()
        monitor.start_request()
        
        # 1. Extract user message
        user_msg = ""
        try:
             # Logic to extract user message
             messages = self._chat_ctx.messages
             if callable(messages): messages = messages()
             # Logic to find the last user message
             for msg in reversed(list(messages)):
                if msg.role == "user" and msg.content:
                    user_msg = msg.content
                    if isinstance(user_msg, list):
                         user_msg = " ".join([str(c) for c in user_msg if isinstance(c, str)])
                    break
        except Exception as e:
            logger.error(f"Error reading chat context: {e}")

        # 2. Build Context
        system_prompt = "You are a helpful assistant."
        limit_tools = self._tools or []
        
        try:
            # context_builder is async
            res = await self.context_builder(user_msg)
            if isinstance(res, tuple):
                system_prompt, dynamic_tools = res
                if dynamic_tools:
                    limit_tools = dynamic_tools
        except Exception as e:
             logger.error(f"Error building context: {e}")

        # 3. Create filtered context for the base LLM
        # 3. Create filtered context for the base LLM
        # Fix: Construct message list directly to avoid mutating ChatContext
        # and to handle the method/generator nature of .messages() correctly.
        messages = []
        
        # 3.1 Add System Prompt
        # Fix: ChatMessage content must be a list
        messages.append(ChatMessage(role="system", content=[system_prompt]))
        
        # 3.2 Copy existing messages (excluding old system prompts)
        original_msgs = self._chat_ctx.messages
        if callable(original_msgs):
            original_msgs = original_msgs()
            
        for msg in original_msgs:
            if msg.role == "system":
                continue
            messages.append(msg)
            
        new_ctx = ChatContext(messages)

        # 3.1 Telemetry: Record Context Size
        total_chars = len(system_prompt) + len(user_msg)
        monitor.record_metric('context_size', total_chars / 4) # Est tokens

        # 3.5. Fix tool schemas to ensure Groq compatibility
        # Deep copy tools to avoid mutating the originals
        fixed_tools = []
        if limit_tools:
            for tool in limit_tools:
                # Create a deep copy to avoid mutating the original
                tool_copy = copy.deepcopy(tool)
                
                # Ensure the tool has the correct schema structure
                # Tools should have .info.parameters (Pydantic model or dict)
                if hasattr(tool_copy, 'info') and hasattr(tool_copy.info, 'parameters'):
                    params = tool_copy.info.parameters
                    
                    # If parameters is a dict-like schema, ensure it has 'properties'
                    if isinstance(params, dict):
                        if 'properties' not in params:
                            logger.debug(f"🔧 Adding 'properties': {{}} to tool '{tool_copy.info.name}'")
                            params['properties'] = {}
                        tool_copy.info.parameters = params
                
                fixed_tools.append(tool_copy)
        
        logger.debug(f"🔧 Passing {len(fixed_tools)} tools to base LLM")

        # 4. Create base stream
        start_time = asyncio.get_event_loop().time()
        first_chunk_time = None
        tokens_out = 0
        
        try:
            # CHAOS FAULT INJECTION
            chaos_config = get_chaos_config()
            if chaos_config.enabled:
                # 1. Latency Injection
                if chaos_config.llm_latency_multiplier > 1.0:
                    delay = random.uniform(0.5, 2.0) * (chaos_config.llm_latency_multiplier - 1.0)
                    logger.warning(f"🔥 CHAOS: Injecting {delay:.2f}s latency")
                    await asyncio.sleep(delay)

                # 2. Rate Limit Simulation
                if chaos_config.rate_limit_probability > 0 and random.random() < chaos_config.rate_limit_probability:
                    logger.warning("🔥 CHAOS: Simulating 429 Rate Limit")
                    raise Exception("429: Rate Limit Exceeded (Simulated)")

                # 3. Generic Failure Simulation
                if chaos_config.tool_failure_rate > 0 and random.random() < chaos_config.tool_failure_rate:
                    logger.warning("🔥 CHAOS: Simulating 500 API Failure")
                    raise Exception("500: Internal Server Error (Simulated)")

            base_stream = self.base_llm.chat(
                chat_ctx=new_ctx,
                tools=fixed_tools if fixed_tools else None,
                extra_kwargs=self.extra_kwargs
            )
            
            logger.info("🧠 SmartLLM: starting stream")
            
            # Wrap stream with probe for validation
            # Increased timeout to 10s to handle potential rate limit retries
            probed_stream = StreamProbe(base_stream, timeout_seconds=10.0)
            
            # 5. Proxy the stream chunks
            async for chunk in probed_stream:
                # Log chunk for debugging
                logger.info(f"🧠 SmartLLM chunk: {chunk}")
                
                now = asyncio.get_event_loop().time()
                if first_chunk_time is None:
                    first_chunk_time = now
                    ttfb = first_chunk_time - start_time
                    monitor.record_metric('stream_first_chunk_latency', ttfb)
                
                # Try to capture precise usage if provided by the provider
                if hasattr(chunk, 'usage') and chunk.usage:
                    if chunk.usage.prompt_tokens:
                        monitor.record_metric('tokens_in', chunk.usage.prompt_tokens)
                    if chunk.usage.completion_tokens:
                        monitor.record_metric('tokens_out', chunk.usage.completion_tokens)
                
                if chunk.delta and chunk.delta.content:
                    tokens_out += 1 # Rough count as fallback
                
                # Ensure we are yielding valid LiveKit LLMChunks
                if isinstance(chunk, ChatChunk):
                     logger.info(f"🧠 Sending valid ChatChunk to LiveKit (Content: {chunk.delta.content[:20] if chunk.delta and chunk.delta.content else 'None'})")
                     await self._event_ch.send(chunk)
                else:
                     logger.warning(f"⚠️ Received non-ChatChunk: {type(chunk)}. Attempting to wrap in ChatChunk.")
                     # If it's a raw string or similar, try to wrap it (though this path is unlikely with standard providers)
                     # For now, just forward and hope, or we could construct a ChatChunk manually if needed.
                     await self._event_ch.send(chunk)
            

            
            end_time = asyncio.get_event_loop().time()
            monitor.record_metric('llm_latency', end_time - start_time)
            
            # Use rough count if precise usage wasn't captured
            if monitor.current_metrics.tokens_out == 0:
                monitor.record_metric('tokens_out', tokens_out)
                
            monitor.end_request()
                
        except Exception as e:
            print(f"DEBUG: SmartLLMStream error: {e}", flush=True) # DEBUG
            logger.error(f"SmartLLM stream error: {e}")
            monitor.record_metric('probe_failures', 1)
            monitor.end_request()
            raise e
