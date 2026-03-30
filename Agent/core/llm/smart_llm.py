import logging
import asyncio
import copy
import random
import time
from typing import Callable, Awaitable, Any, List, Tuple, Optional

from livekit.agents.llm import (
    LLM, LLMStream, ChatContext, ChatMessage, ChatChunk, ToolChoice, ChoiceDelta
)
from livekit.agents.types import (
    NotGivenOr, NOT_GIVEN, DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions
)

from probes.runtime.probe_engine import probe_context, StreamProbe
from telemetry.session_monitor import get_session_monitor
from chaos.fault_injection import get_chaos_config
from persistence.session_manager import SessionManager
from core.context.context_guard import ContextGuard

logger = logging.getLogger(__name__)

_PROVIDER_HOST_MAP = {
    "groq": "api.groq.com",
    "elevenlabs": "api.elevenlabs.io",
    "deepgram": "api.deepgram.com",
    "cartesia": "api.cartesia.ai",
    "openai": "api.openai.com",
}

class SmartLLM(LLM):
    """
    Wraps the LLM to inject dynamic tools and context per turn, bypassing LiveKit's
    static tool initialization which causes schema validation errors.
    Proxies streaming calls to the underlying LLM using a custom LLMStream.
    Supports failover to a fallback LLM if the primary fails.
    Persists generated responses to SessionManager.
    Enforces token limits using ContextGuard.
    """

    def __init__(
        self, 
        base_llm: LLM, 
        context_builder: Callable[[str], Awaitable[Tuple[str, List[Any]]]], 
        fallback_llm: Optional[LLM] = None,
        session_manager: Optional[SessionManager] = None,
        session_id: Optional[str] = None,
        context_guard: Optional[ContextGuard] = None
    ):
        super().__init__()
        self.base_llm = base_llm
        self.fallback_llm = fallback_llm
        self.context_builder = context_builder
        self.session_manager = session_manager
        self.session_id = session_id
        self.session_id = session_id
        self.context_guard = context_guard
        self._recent_tools = []
        self.provider_supervisor = None
        
    @property
    def model(self) -> str:
        return self.base_llm.model
        
    @property
    def provider(self) -> str:
        return self.base_llm.provider

    @property
    def label(self) -> str:
        return f"SmartLLM({self.base_llm.label})"

    def set_provider_supervisor(self, supervisor: Any) -> None:
        self.provider_supervisor = supervisor

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: List[Any] | None = None,
        fnc_ctx: Any | None = None, # Added fnc_ctx support
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> "SmartLLMStream":
        # Map fnc_ctx to tools if provided and tools is missing
        if tools is None and fnc_ctx is not None:
             tools = fnc_ctx if isinstance(fnc_ctx, list) else [fnc_ctx]

        return SmartLLMStream(
            llm=self,
            base_llm=self.base_llm,
            fallback_llm=self.fallback_llm,
            context_builder=self.context_builder,
            chat_ctx=chat_ctx,
            tools=tools, # Stream expects 'tools' internal usage
            conn_options=conn_options,
            parallel_tool_calls=parallel_tool_calls,
            tool_choice=tool_choice,
            extra_kwargs=extra_kwargs,
            session_manager=self.session_manager,
            session_id=self.session_id,
            context_guard=self.context_guard
        )

class SmartLLMStream(LLMStream):
    def __init__(
        self, 
        llm: SmartLLM, 
        base_llm: LLM,
        fallback_llm: Optional[LLM],
        context_builder, 
        parallel_tool_calls: NotGivenOr[bool],
        tool_choice: NotGivenOr[ToolChoice],
        extra_kwargs: NotGivenOr[dict[str, Any]],
        session_manager: Optional[SessionManager] = None,
        session_id: Optional[str] = None,
        context_guard: Optional[ContextGuard] = None,
        tools: List[Any] | None = None, # Explicitly accept tools
        **kwargs
    ):
        super().__init__(llm, tools=tools, **kwargs)
        # Allow overriding base_llm for this specific stream (per-turn routing)
        # Fix: Pop 'base_llm_override' so it doesn't get passed to the underlying client
        if isinstance(extra_kwargs, dict):
            self.base_llm = extra_kwargs.pop("base_llm_override", base_llm)
        else:
            self.base_llm = base_llm
        self.fallback_llm = fallback_llm
        self.context_builder = context_builder
        self.parallel_tool_calls = parallel_tool_calls
        self.tool_choice = tool_choice
        self.extra_kwargs = extra_kwargs
        self.session_manager = session_manager
        self.session_id = session_id
        self.context_guard = context_guard
        self._provided_tools = tools # Store provided tools
        self.full_response_text = ""
        self._recent_tools = getattr(llm, "_recent_tools", [])
        if not hasattr(llm, "_recent_tools"):
            llm._recent_tools = []
        self.provider_supervisor = getattr(llm, "provider_supervisor", None)

    def _provider_key(self, llm_instance: Any, label: str) -> str:
        provider = str(getattr(llm_instance, "provider", "") or "").strip().lower()
        if provider:
            return _PROVIDER_HOST_MAP.get(provider, provider)
        return str(label or "unknown").strip().lower()

    def _check_tool_loop(self, tools: List[Any]) -> bool:
        # This is a bit tricky because we don't know WHICH tool the LLM *will* call yet.
        # The user's snippet:
        # "if self._recent_tools.count(tool_name) >= 2: return _static_stream(...)"
        # acts AFTER the tool call is generated but BEFORE execution.
        # However, SmartLLM wraps the LLM *generation*. It doesn't execute tools itself (the orchestration loop does, or the tool stream consumer).
        # Wait, LiveKit's LLMStream yields `ChatChunk` which might contain `tool_calls`.
        # If we want to blocking the LLM from *generating* a repeated tool call, we can't easily do it unless we inspect the chunk.
        # BUT, the user's instruction says: "Add before executing tool calls" ... "This stops rapid repeated tool calls."
        # And "Replace with: stream = ... tools=fixed_tools ...".
        
        # Actually, the user's snippet for loop guard seems to be intended for the *Orchestrator* or *Worker*?
        # "open core/llm/smart_llm.py... Add before executing tool calls:" 
        # SmartLLM *doesn't* execute tools. It generates them.
        # The Orchestrator or Worker executes them.
        # UNLESS the user means "before *sending* the tool definition to the LLM"? No, that doesn't make sense.
        # OR, maybe they mean inside `_attempt_stream` when `fnc_ctx` is processed?
        
        # Let's look closer at the user request:
        # "Add before executing tool calls: ... tool_name = tool_call.name ... if count >= 2 return _static_stream"
        
        # This implies we are intercepting the OUTPUT of the LLM.
        # In `_attempt_stream`, we iterate `async for chunk in probed_stream`.
        # We can inspect `chunk.tool_calls`.
        
        return False


    def _force_resolve_tools(self, intent: str = "default"):
        """
        Resolve tools from agent at runtime with INTENT-BASED FILTERING.
        Returns only relevant tools based on the user's intent to reduce token usage.
        """
        all_tools = []
        
        # Priority 0: Explicitly provided tools to the stream (e.g. from RoleLLM)
        if self._provided_tools is not None:
             logger.info(f"🔧 Using explicitly provided tools: {len(self._provided_tools)}")
             return self._provided_tools

        # Priority 1: SmartLLM instance tools (if any)
        if hasattr(self, "_tools") and self._tools:
            all_tools = self._tools
        # Priority 2: Tools from context_builder.agent
        elif self.context_builder and hasattr(self.context_builder, "agent"):
            agent = self.context_builder.agent
            if hasattr(agent, "_tools") and agent._tools:
                all_tools = agent._tools
        # Priority 3: Tools from session context (if available)
        elif self.session_manager and self.session_id:
            session = self.session_manager.get_session(self.session_id)
            if session and hasattr(session, "tools"):
                all_tools = session.tools

        # Priority 4: Final fallback to GlobalAgentContainer (Crucial for Console Mode)
        if not all_tools:
            try:
                from core.runtime.global_agent import GlobalAgentContainer
                all_tools = GlobalAgentContainer.get_tools()
            except Exception:
                pass

        logger.debug(f"🔍 DEBUG: all_tools count: {len(all_tools)}")
        if not all_tools:
            logger.debug("🔍 SmartLLM: No tools available in any registry.")
            return []

        # PHASE 4: Tool filtering based on intent to reduce context bloat
        # Only return all tools for specific intents
        if intent in ("task_request", "action", "planning"):
            logger.info(f"🔧 Using ALL {len(all_tools)} tools for intent: {intent}")
            return all_tools

        # For chat/small talk, return minimal tool set (if any)
        # if intent in ("small_talk", "chat", "greeting"):
            # Return empty list for chat - CHAT role shouldn't use tools
            # logger.info(f"🔧 Using 0 tools for intent: {intent} (small talk mode)")
            # return []

        # For general/unknown, return essential tools only
        essential_tool_keywords = ["web_search", "get_weather", "get_time", "get_date", "memory", "save", "remember", "report_tool", "retrieve"]
        filtered_tools = [
            t for t in all_tools
            if any(kw in str(getattr(t, 'name', '')).lower() for kw in essential_tool_keywords)
        ]
        logger.info(f"🔧 Filtered {len(all_tools)} -> {len(filtered_tools)} essential tools for intent: {intent}")
        return filtered_tools if filtered_tools else all_tools

    async def _run(self):
        # 0. Start Telemetry
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
        # 2. Build Context
        system_prompt = "You are a helpful assistant."
        
        # 🔥 CRITICAL FIX — force tool resolution every turn
        limit_tools = self._force_resolve_tools()
        if limit_tools:
            logger.info(f"🧰 Tools available to LLM: {len(limit_tools)}")
        
        # New: List to hold the constructed messages
        constructed_messages = []
        
        try:
            # context_builder is async
            # Updated signature: passes chat_ctx
            res = await self.context_builder(user_msg, chat_ctx=self._chat_ctx)
            
            if isinstance(res, tuple):
                # LRCS returns (messages, tools)
                constructed_messages, dynamic_tools = res
                # Merge prepared chat context memory markers on success path.
                # Context builder can omit these messages, which breaks recall prompts.
                if self._chat_ctx:
                    chat_messages = self._chat_ctx.messages
                    if callable(chat_messages):
                        chat_messages = chat_messages()
                    existing_ids = {id(m) for m in constructed_messages}
                    existing_contents = {str(getattr(m, "content", "")) for m in constructed_messages}
                    for msg in chat_messages:
                        if getattr(msg, "role", "") == "system":
                            continue
                        msg_content = str(getattr(msg, "content", ""))
                        if "[Memory]" not in msg_content:
                            continue
                        if id(msg) in existing_ids or msg_content in existing_contents:
                            continue
                        constructed_messages.append(msg)
                        existing_ids.add(id(msg))
                        existing_contents.add(msg_content)
                # Respect explicitly provided tools (e.g. RoleLLM phase allowlists).
                if dynamic_tools and self._provided_tools is None:
                    limit_tools = dynamic_tools
            else:
                # Fallback for old signature (shouldn't happen if updated correctly)
                logger.warning("Context builder returned legacy format, adapting...")
                if isinstance(res, tuple):
                     sys_p, dyn_t = res
                     if isinstance(sys_p, str):
                         sys_p = [{"type": "text", "text": sys_p}]
                     constructed_messages = [ChatMessage(role="system", content=sys_p)]
        except Exception as e:
             logger.error(f"Error building context: {e}")
             # Fallback to simple system prompt if builder fails
             # FIX 1: ContentPart requires dict {type, text}, not a bare string
             constructed_messages = [ChatMessage(role="system", content=[{"type": "text", "text": system_prompt}])]
             msgs = self._chat_ctx.messages
             if callable(msgs): msgs = msgs()
             constructed_messages.extend([m for m in msgs if m.role != "system"])

        if self.context_guard:
            try:
                # NEW: Use FinalContextGuard logic (adapter pattern if needed)
                # But here we are using 'context_guard' which was injected as ContextGuard type.
                # The user instruction was "Add FinalContextGuard before LLM streaming".
                # We should import and use it here.
                
                from core.context.final_context_guard import FinalContextGuard
                # If injected guard is old type, wrap it or use new one. 
                # Ideally we should refrain from dynamic instantiation inside method, but 
                # given the directive, let's enforce it.
                
                final_guard = FinalContextGuard() # Default 128k
                
                # Convert to dicts for guard
                history_dicts = []
                for m in constructed_messages:
                    msg_dict = {"role": m.role, "content": m.content}
                    if hasattr(m, "tool_calls") and m.tool_calls:
                         msg_dict["tool_calls"] = m.tool_calls
                    history_dicts.append(msg_dict)
                
                # Guard
                safe_dicts = final_guard.ensure_safe(history_dicts)
                
                # Reconstruct
                constructed_messages = []
                for d in safe_dicts:
                     msg = ChatMessage(role=d["role"], content=d["content"])
                     if "tool_calls" in d: msg.tool_calls = d["tool_calls"]
                     constructed_messages.append(msg)
                
                logger.debug(f"🛡️ FinalContextGuard passed. Size: {len(constructed_messages)}")

            except Exception as e:
                logger.error(f"⚠️ FinalContextGuard failed: {e}")
                # Fallback: Proceed with original messages, but log error


        # 3. Use the constructed messages for the base LLM
        # We create a new ChatContext with the EXACT list returned by the builder
        # DEBUG: Dump final message schema to validate content format before LLM call
        logger.debug(
            f"📋 Final context payload ({len(constructed_messages)} msgs): "
            + str([{"role": m.role, "content_type": type(m.content).__name__,
                    "content_preview": str(m.content)[:120]} for m in constructed_messages])
        )
        _memory_count = sum(
            1 for m in constructed_messages
            if "[Memory]" in str(getattr(m, "content", ""))
        )
        logger.info(
            "smart_llm_context_audit memory_msgs=%d total_msgs=%d",
            _memory_count, len(constructed_messages)
        )
        new_ctx = ChatContext(constructed_messages)

        # 3.1 Telemetry: Record Context Size
        total_chars = sum(len(str(m.content)) for m in constructed_messages)
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

                    # Ensure an explicit object schema for strict providers.
                    if params is None:
                        tool_copy.info.parameters = {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        }
                    elif isinstance(params, dict):
                        if 'properties' not in params:
                            logger.debug(f"🔧 Adding 'properties': {{}} to tool '{tool_copy.info.name}'")
                            params['properties'] = {}
                        if 'required' not in params:
                            params['required'] = []
                        if 'type' not in params:
                            params['type'] = "object"
                        tool_copy.info.parameters = params
                
                fixed_tools.append(tool_copy)
        
        # 🚨 HARD GUARD: Prevent silent chat mode fallback.
        # EXCEPTIONS:
        # - Planner / strict JSON generation flows.
        # - Explicit tool-less reasoning requests (tool_choice='none').
        if not fixed_tools:
            # Check for "pure generation" request (like Planning) by inspecting system prompt
            msgs = self._chat_ctx.messages
            if callable(msgs): msgs = msgs()
            # Robust check for Planning/JSON generation roles
            sys_prompts = [m.content[0] if isinstance(m.content, list) else m.content for m in msgs if m.role == "system"]
            is_planning = any(
                "Output ONLY valid JSON" in p or 
                "Task Planner" in p or 
                "strict JSON object" in p 
                for p in sys_prompts
            )
            
            allow_toolless = self.tool_choice == "none"

            if not is_planning and not allow_toolless:
                raise RuntimeError(
                    "LLM chat path invoked without tools. This should NEVER happen. "
                    "All user input must route through orchestrator → planner → worker → tool."
                )
            else:
                logger.info("🧠 SmartLLM: Allowing explicit tool-less execution")
        
        logger.debug(f"🔧 Passing {len(fixed_tools)} tools to base LLM")

        # 4. Run stream with Failover
        providers = [(self.base_llm, "Primary")]
        if self.fallback_llm:
            providers.append((self.fallback_llm, "Fallback"))

        success = False
        last_error = None

        for llm_instance, label in providers:
            provider_key = self._provider_key(llm_instance, label)
            if self.provider_supervisor and not self.provider_supervisor.should_allow_request(provider_key):
                logger.warning(
                    "circuit_breaker_open provider=%s label=%s — skipping to fallback",
                    provider_key,
                    label,
                )
                continue
            try:
                await self._attempt_stream(llm_instance, label, new_ctx, fixed_tools, monitor)
                if self.provider_supervisor:
                    self.provider_supervisor.mark_healthy(provider_key)
                success = True
                break
            except Exception as e:
                logger.error(f"❌ {label} LLM failed: {e}")
                if self.provider_supervisor:
                    self.provider_supervisor.mark_failed(provider_key, e)
                last_error = e
        
        if not success:
            logger.critical("🔥 All LLM providers failed.")
            monitor.record_metric('probe_failures', 1)
            monitor.end_request()
            if last_error:
                raise last_error
            else:
                 raise Exception("All providers failed with no exception captured")

    async def _attempt_stream(self, llm_instance, label, ctx, tools, monitor):
        start_time = asyncio.get_event_loop().time()
        first_chunk_time = None
        tokens_out = 0
        self.full_response_text = "" # Reset for new attempt
        
        # CHAOS FAULT INJECTION
        chaos_config = get_chaos_config()
        if chaos_config.enabled and label == "Primary":
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

        if label == "Fallback":
            logger.warning(f"⚠️ Switching to {label} LLM: {llm_instance.label}")

        if self._check_tool_loop(tools):
             logger.warning("🔄 Tool loop detected in SmartLLM. Preventing re-execution.")
             # We can't easily return a text response here because we need to yield a stream.
             # But the context guard logic earlier injects a SYSTEM WARNING.
             # The user asked to "return _static_stream(...)" if loop. 
             # Let's implement _static_stream or a generator.
             pass 

        base_stream = llm_instance.chat(
            chat_ctx=ctx,
            tools=tools if tools is not None else [], # ⭐ FIX 3: Pass empty list if no tools
            tool_choice="none" if not tools else "auto", # ⭐ FIX 2: Force "none" if no tools
            extra_kwargs=self.extra_kwargs
        )
        
        logger.info(f"🧠 SmartLLM: starting stream with {label}")
        
        # Wrap stream with probe for validation
        probed_stream = StreamProbe(base_stream, timeout_seconds=10.0)
        # Track tool-call frequency per stream attempt only.
        # This prevents cross-turn false positives (e.g., legitimate repeated create_task requests).
        turn_tool_counts: dict[str, int] = {}
        
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
                tokens_out += 1 
                self.full_response_text += chunk.delta.content
            
            if isinstance(chunk, ChatChunk):
                 # ⭐ FIX 4: Tool Loop Guard (Interception)
                 if chunk.delta and chunk.delta.tool_calls:
                     filtered_calls = []
                     for tc in chunk.delta.tool_calls:
                         fn_name = tc.name # ⭐ FIX: LiveKit FunctionToolCall has .name, not .function.name
                         # Ensure tool call has type
                         if not hasattr(tc, 'type') or not tc.type:
                             tc.type = 'function'
                         # Update history
                         self._llm._recent_tools.append(fn_name)
                         self._llm._recent_tools = self._llm._recent_tools[-10:] # Keep last 10
                         turn_tool_counts[fn_name] = turn_tool_counts.get(fn_name, 0) + 1
                         
                         # Check frequency
                         if turn_tool_counts[fn_name] >= 3: # Allow 2 retries within this stream
                             logger.warning(f"🔄 LOOP DETECTED: {fn_name} called 3+ times recently. Blocking.")
                             # We can replace this tool call with a text warning or just drop it.
                             # To be safe, we'll drop it and inject a text chunk saying why.
                             # But we can't easily inject a text chunk into the stream if the provider didn't send one.
                             # We'll just NOT send this tool call.
                             await self._event_ch.send(ChatChunk(
                                 id=chunk.id,
                                 delta=ChoiceDelta(content=f"\n[SYSTEM: Blocked repeated call to {fn_name} to prevent infinite loop.]", role="assistant")
                             ))
                             continue
                         
                         filtered_calls.append(tc)
                     
                     # Replace chunk tool calls with filtered list
                     if len(filtered_calls) != len(chunk.delta.tool_calls):
                         chunk.delta.tool_calls = filtered_calls

                 await self._event_ch.send(chunk)
            else:
                 logger.warning(f"⚠️ Received non-ChatChunk: {type(chunk)}. Forwarding anyway.")
                 await self._event_ch.send(chunk)
        
        end_time = asyncio.get_event_loop().time()
        monitor.record_metric('llm_latency', end_time - start_time)
        
        if monitor.current_metrics.tokens_out == 0:
            monitor.record_metric('tokens_out', tokens_out)
            
        # Persistence
        if self.session_manager and self.session_id and self.full_response_text:
            try:
                self.session_manager.add_message(
                    session_id=self.session_id,
                    role="assistant",
                    content=self.full_response_text
                )
                logger.info(f"💾 Persisted assistant response for session {self.session_id}")
            except Exception as e:
                logger.error(f"❌ Failed to persist assistant response: {e}")

        monitor.end_request()
