import logging
from typing import List, Optional, Any
from livekit.agents.llm import ChatContext, LLM
from core.llm.smart_llm import SmartLLM
from core.llm.llm_roles import LLMRole, RoleConfig, get_role_config
from core.utils.intent_utils import normalize_intent

logger = logging.getLogger(__name__)

class RoleLLM:
    """
    Wrapper around SmartLLM that enforces Role-based configuration.
    Ensures that CHAT never sees tools, and WORKER always sees tools.
    """
    
    def __init__(self, smart_llm: SmartLLM):
        self.llm = smart_llm
        
    async def chat(self, 
                   role: LLMRole, 
                   chat_ctx: ChatContext, 
                   tools: List[Any] = None, 
                   **kwargs) -> Any:
        """
        Execute chat with role-specific constraints.
        """
        config = get_role_config(role)
        
        # 1. Enforce Tool Visibility
        effective_tools = None
        if config.include_tools:
            # Only allow tools if the role is configured for it
            effective_tools = tools
        elif tools:
             role_str = normalize_intent(role)
             logger.warning(f"🚫 Role {role_str} attempted to use tools but is configured WITHOUT tools. Tools suppressed.")
             effective_tools = None
             
        # 2. Apply Role Configuration
        # Pass temperature through extra_kwargs for SmartLLM to handle
        if 'extra_kwargs' not in kwargs:
            kwargs['extra_kwargs'] = {}
        kwargs['extra_kwargs']['temperature'] = config.temperature
        
        # 3. Message Sanitization & Budgeting
        from core.context.token_budget_guard import enforce_budget
        
        # Access messages from ChatContext (handle method vs property)
        messages = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
        
        # A. Deduplicate System Prompts
        original_system_count = sum(
            1 for m in messages
            if (m.role if hasattr(m, "role") else m.get("role", "")) == "system"
        )
        filtered_messages = [m for m in messages if m.role != "system"]
        
        # Re-inject correct system prompt from config
        from livekit.agents.llm import ChatMessage
        if config.system_prompt_template:
            # content must be a list
            sys_content = config.system_prompt_template
            if isinstance(sys_content, str):
                sys_content = [sys_content]
            filtered_messages.insert(0, ChatMessage(role="system", content=sys_content))
            
        # B. Enforce Token Budget
        # Convert ChatMessage objects to dicts for the guard
        # The guard expects list[dict], but we have list[ChatMessage]
        # We need a transformation layer or update the guard to handle objects.
        # Ideally, we update the guard to be robust. 
        # But `enforce_budget` works on a list of dicts.
        # Let's verify what `enforce_budget` actually expects. 
        # In token_budget_guard.py: enforce_budget(messages: List[Dict[str, str]])
        
        # So we must adapt.
        dict_messages = []
        for m in filtered_messages:
            content = m.content if hasattr(m, 'content') else m.get('content', '')
            # Normalization: Ensure content is string for the budget guard (it likely expects text)
            if isinstance(content, list):
                # Join simple string parts for token counting
                text_content = ""
                for part in content:
                    if isinstance(part, str): text_content += part
                    elif hasattr(part, "text"): text_content += part.text
                dict_content = text_content
            else:
                dict_content = str(content)
                
            role = m.role if hasattr(m, 'role') else m.get('role', 'user')
            dict_messages.append({"role": role, "content": dict_content})
            
        # Use the role's configured model for the budget check
        model_for_budget = config.model if config.model else "default"
        
        # Enforce budget on the dict representation
        safe_dict_messages = enforce_budget(dict_messages, model_name=model_for_budget)
        
        # Update Context if truncation happened or system prompt injection
        # check if update is needed
        needs_update = (
            len(safe_dict_messages) != len(dict_messages)
            or len(filtered_messages) != len(messages)
            # If we replaced an existing system prompt with role config prompt,
            # force context rewrite even when message count is unchanged.
            or (original_system_count > 0 and bool(config.system_prompt_template))
        )
        
        if needs_update:
             logger.info(f"📉 Updating context (Budget/SysPrompt): {len(messages)} -> {len(safe_dict_messages)}")
             reconstructed_messages = []
             for msg_dict in safe_dict_messages:
                 # Ensure content is list for ChatMessage
                 c = msg_dict["content"]
                 if isinstance(c, str):
                     c = [c]
                 try:
                     reconstructed_messages.append(ChatMessage(role=msg_dict["role"], content=c))
                 except Exception as e:
                     # Fallback for roles not supported by ChatMessage (e.g. 'tool')
                     logger.warning(f"⚠️ Could not create ChatMessage for role {msg_dict.get('role')}: {e}. Using dict.")
                     reconstructed_messages.append(msg_dict)
             
             # Safely update ChatContext content
             if hasattr(chat_ctx, "items") and isinstance(chat_ctx.items, list):
                 chat_ctx.items.clear()
                 chat_ctx.items.extend(reconstructed_messages)
             else:
                 # Fallback: try setting messages (might fail or shadow method)
                 # Or use private _items if available
                 if hasattr(chat_ctx, "_items") and isinstance(chat_ctx._items, list):
                     chat_ctx._items.clear()
                     chat_ctx._items.extend(reconstructed_messages)
                 else:
                     logger.warning("⚠️ Could not update ChatContext: no 'items' or '_items' list found.")
                     # Try setting messages as last resort (risky)
                     try:
                        chat_ctx.messages = reconstructed_messages
                     except:
                        pass

        
        role_str = normalize_intent(role)
        logger.info(f"🎭 RoleLLM executing as {role_str.upper()} (Model: {config.model or 'default'}, Tools: {len(effective_tools) if effective_tools else 0})")
        
        # 4. Model Routing
        # Dynamically resolve the correct LLM provider if configured for this role
        base_llm_override = None
        
        if config.provider and config.model:
            try:
                # Import factory here to avoid potential circular imports at module level
                from providers.factory import ProviderFactory
                
                role_str = normalize_intent(role)
                logger.debug(f"🔄 RoleLLM: resolving provider for {role_str} -> {config.provider}/{config.model}")
                base_llm_override = ProviderFactory.get_llm(
                    provider_name=config.provider, 
                    model=config.model, 
                    temperature=config.temperature
                )
            except Exception as e:
                logger.error(f"❌ RoleLLM failed to resolve provider {config.provider}: {e}")
                # Fallback to default (don't override)
        
        # Prepare kwargs
        if base_llm_override:
            # We must pass this to SmartLLM via extra_kwargs or directly if we modified signature
            # SmartLLM.chat signature: ..., extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN
            # We need to construct or merge extra_kwargs.
            
            # Implementation Detail: SmartLLMStream now looks for 'base_llm_override' in 'extra_kwargs'.
            # So we wrap it there.
            
            current_extra = kwargs.get('extra_kwargs', {})
            if current_extra is None: current_extra = {}
            current_extra['base_llm_override'] = base_llm_override
            kwargs['extra_kwargs'] = current_extra
            
            role_str = normalize_intent(role)
            logger.info(f"🎭 RoleLLM executing as {role_str.upper()} using {config.provider}/{config.model}")
        
        # SmartLLM.chat() is not async - it returns a stream directly
        return self.llm.chat(chat_ctx=chat_ctx, tools=effective_tools, **kwargs)
