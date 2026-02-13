"""
Execution Router Module
Routes requests based on intent classification.
Handles tool execution, LLM responses, and clarification flows.
"""

import logging
from typing import Optional, Callable, Dict, Any, Awaitable
from dataclasses import dataclass

from core.intent.classifier import IntentType, IntentResult, get_classifier
from core.registry.tool_registry import get_registry
from core.intelligence.rag_engine import get_rag_engine
from core.agents.registry import get_agent_registry
from core.agents.base import AgentContext

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    """Result of routing a request"""
    handled: bool
    response: Optional[str] = None
    tool_executed: Optional[str] = None
    intent_type: Optional[IntentType] = None  # Add this field
    needs_llm: bool = False
    error: Optional[str] = None


class ExecutionRouter:
    """
    Routes requests based on intent classification.
    Executes tools, retrieves memory, or delegates to LLM.
    """
    
    def __init__(
        self,
        tool_executor: Optional[Callable[[str, Dict], Awaitable[str]]] = None,
        memory_context: str = "",
    ):
        """
        Initialize the execution router.
        
        Args:
            tool_executor: Async function to execute tools (name, params) -> result
            memory_context: Current memory context string
        """
        self.classifier = get_classifier()
        self.registry = get_registry()
        self.tool_executor = tool_executor
        self.memory_context = memory_context
        self.logger = logging.getLogger(__name__)
        self.agent_registry = get_agent_registry()
        
        # Clarification templates
        self.clarification_templates = [
            "I'd be happy to help! Could you tell me more about what you'd like to do?",
            "I want to make sure I understand. What would you like me to help with?",
            "Could you give me a bit more detail about what you're looking for?",
        ]
        self._clarification_index = 0
    
    def set_memory_context(self, context: str) -> None:
        """Update the memory context"""
        self.memory_context = context
    
    def set_tool_executor(self, executor: Callable[[str, Dict], Awaitable[str]]) -> None:
        """Set the tool executor function"""
        self.tool_executor = executor
    
    async def route(self, user_text: str, context: Any = None, assistant: Any = None) -> RouteResult:
        """
        Route a user request based on intent.
        
        Args:
            user_text: The user's input text
            context: Execution context (e.g. user role)
            assistant: Optional assistant instance for detailed access
            
        Returns:
            RouteResult with handling information
        """
        # Session Telemetry initialization (if not already started)
        from telemetry.session_monitor import get_session_monitor
        monitor = get_session_monitor()

        # Classify intent
        intent = self.classifier.classify(user_text, self.memory_context)
        
        self.logger.info(f"🎯 Intent: {intent.intent_type.value} (conf={intent.confidence:.2f})")
        
        # 1. Check for Knowledge in RAG store (Semantic grounding)
        # We do this for both CONVERSATION and specific queries
        knowledge_context = ""
        if intent.confidence > 0.3: # Threshold for looking up knowledge
             self.logger.info(f"🔍 Searching RAG for: '{user_text}'")
             knowledge_context = await get_rag_engine().get_context(user_text)
             if knowledge_context:
                 self.logger.info("📚 Found relevant knowledge in vector store")
                 monitor.record_metric('memory_retrieval_count', 1, increment=True)

        # Route based on intent type
        if intent.intent_type == IntentType.TOOL_ACTION:
            result = await self._handle_tool_action(user_text, intent, context)
            if knowledge_context:
                result.response = f"{result.response}\n\n[Background Knowledge]:\n{knowledge_context}"
            return result
        
        elif intent.intent_type == IntentType.MEMORY_QUERY:
            result = self._handle_memory_query(user_text, intent)
            if not result.handled and knowledge_context:
                return RouteResult(
                    handled=True,
                    response=f"Based on what I know:\n{knowledge_context}",
                    intent_type=intent.intent_type,
                    needs_llm=True
                )
            return result
        
        elif intent.intent_type == IntentType.CLARIFICATION:
            return self._handle_clarification(user_text, intent)
        
        else:  # CONVERSATION
            if knowledge_context:
                return RouteResult(
                    handled=True,
                    response=f"Here is some information I found:\n{knowledge_context}",
                    intent_type=intent.intent_type,
                    needs_llm=True
                )
            return self._handle_conversation(user_text, intent)
    
    async def _handle_tool_action(self, user_text: str, intent: IntentResult, context: Any = None) -> RouteResult:
        """Handle a tool action intent"""
        
        if not intent.matched_tool:
            self.logger.warning("Tool action intent but no tool matched")
            return RouteResult(
                handled=False,
                needs_llm=True,
                intent_type=intent.intent_type,
                error="Could not determine which tool to use"
            )
        
        tool = self.registry.get_tool(intent.matched_tool)
        if not tool:
            self.logger.error(f"Matched tool not found in registry: {intent.matched_tool}")
            return RouteResult(
                handled=False,
                needs_llm=True,
                intent_type=intent.intent_type,
                error="Tool not available"
            )
        
        # Extract parameters
        params = self.classifier.extract_params(user_text, intent.matched_tool)
        
        # Check required parameters
        missing_params = [p for p in tool.required_params if p not in params]
        if missing_params:
            self.logger.info(f"Missing required params: {missing_params}")
            return RouteResult(
                handled=True,
                response=f"I need a bit more info. What's the {missing_params[0].replace('_', ' ')}?",
                intent_type=intent.intent_type,
                needs_llm=False
            )
        
        # Execute the tool
        if self.tool_executor:
            try:
                self.logger.info(f"🔧 Executing tool: {intent.matched_tool}")
                from telemetry.session_monitor import get_session_monitor
                monitor = get_session_monitor()
                monitor.record_metric('tool_calls_count', 1, increment=True)
                
                result = await self.tool_executor(intent.matched_tool, params, context=context)
                return RouteResult(
                    handled=True,
                    response=result,
                    tool_executed=intent.matched_tool,
                    intent_type=intent.intent_type,
                    needs_llm=True
                )
            except Exception as e:
                self.logger.error(f"Tool execution failed: {e}")
                
                # Provide friendly error message
                friendly_msg = "I encountered a problem while trying to perform that action."
                if "missing" in str(e).lower() and "argument" in str(e).lower():
                    friendly_msg = "I seem to be missing some details to complete that request. Could you be more specific?"
                
                return RouteResult(
                    handled=True,
                    response=friendly_msg,
                    error=str(e),
                    intent_type=intent.intent_type,
                    needs_llm=False
                )
        else:
            # No executor, delegate to LLM with tool info
            return RouteResult(
                handled=False,
                needs_llm=True,
                intent_type=intent.intent_type,
                tool_executed=intent.matched_tool
            )
    
    def _handle_memory_query(self, user_text: str, intent: IntentResult) -> RouteResult:
        """Handle a memory/identity query"""
        
        if not self.memory_context:
            return RouteResult(
                handled=False,
                needs_llm=True,
                response=None,
                intent_type=intent.intent_type
            )
        
        # Extract relevant info from memory context
        user_lower = user_text.lower()
        
        # Check for name queries
        if 'name' in user_lower or 'who am i' in user_lower:
            # Try to find name in memory
            import re
            name_patterns = [
                r"name\s+is\s+(\w+)",
                r"called\s+(\w+)",
                r"user['']?s?\s+name[:\s]+(\w+)",
            ]
            for pattern in name_patterns:
                match = re.search(pattern, self.memory_context, re.IGNORECASE)
                if match:
                    name = match.group(1)
                    return RouteResult(
                        handled=True,
                        response=f"Your name is {name}.",
                        needs_llm=False,
                        intent_type=intent.intent_type
                    )
        
        # Memory exists but couldn't extract specific answer
        # Let LLM use the context
        return RouteResult(
            handled=False,
            needs_llm=True,
            intent_type=intent.intent_type
        )
    
    def _handle_clarification(self, user_text: str, intent: IntentResult) -> RouteResult:
        """Handle a request that needs clarification"""
        
        response = self.clarification_templates[self._clarification_index]
        self._clarification_index = (self._clarification_index + 1) % len(self.clarification_templates)
        
        return RouteResult(
            handled=True,
            response=response,
            needs_llm=False,
            intent_type=intent.intent_type
        )
    
    def _handle_conversation(self, user_text: str, intent: IntentResult) -> RouteResult:
        """Handle a conversational request - delegate to LLM"""
        
        return RouteResult(
            handled=False,
            needs_llm=True,
            intent_type=intent.intent_type
        )


# Global router instance
_router: Optional[ExecutionRouter] = None


def get_router() -> ExecutionRouter:
    """Get the global execution router"""
    global _router
    if _router is None:
        _router = ExecutionRouter()
    return _router


def reset_router() -> None:
    """Reset the global router"""
    global _router
    _router = None


async def route_request(user_text: str) -> RouteResult:
    """Convenience function to route a request"""
    return await get_router().route(user_text)
