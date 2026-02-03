"""
Intent Layer Module
Classifies user input and routes to appropriate handler.
Reduces LLM dependency for routing decisions.
"""

import logging
import re
import threading
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from tool_registry import get_registry, ToolRegistry

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Types of user intents"""
    TOOL_ACTION = "tool_action"      # Requires executing a tool
    CONVERSATION = "conversation"     # Normal chat response
    MEMORY_QUERY = "memory_query"     # Answer from memory context
    CLARIFICATION = "clarification"   # Need more info from user


@dataclass
class IntentResult:
    """Result of intent classification"""
    intent_type: IntentType
    confidence: float
    matched_tool: Optional[str] = None
    extracted_params: Dict[str, Any] = None
    reason: str = ""
    
    def __post_init__(self):
        if self.extracted_params is None:
            self.extracted_params = {}


class IntentClassifier:
    """
    Classifies user intent using keyword matching and semantic analysis.
    Routes requests without heavy LLM dependency.
    """
    
    # Action verbs that indicate tool usage
    ACTION_VERBS = {
        'play', 'pause', 'stop', 'skip', 'next', 'previous', 'resume',
        'search', 'find', 'look', 'lookup', 'get', 'fetch',
        'send', 'email', 'message', 'notify',
        'add', 'remove', 'delete', 'create', 'queue',
        'set', 'change', 'update', 'modify',
        'show', 'list', 'display', 'open',
        'check', 'tell', 'give',
    }
    
    # Identity/memory keywords
    MEMORY_KEYWORDS = {
        'my name', 'who am i', 'remember me', 'my favorite', 'my preference',
        'you know me', 'about me', 'my profile', 'i told you', 'i said',
    }
    
    # Greeting/conversation patterns (Compiled)
    GREETING_PATTERNS = [
        re.compile(r'^(hi|hello|hey|good\s+(morning|afternoon|evening)|howdy)', re.IGNORECASE),
        re.compile(r'^(what\'?s up|how are you|how\'?s it going)', re.IGNORECASE),
        re.compile(r'^(thanks?|thank you|bye|goodbye|see you)', re.IGNORECASE),
    ]
    
    # Question patterns that need conversation
    CONVERSATION_PATTERNS = [
        re.compile(r'^(what|who|why|how|when|where)\s+(is|are|was|were|do|does|did|can|could|would|should)', re.IGNORECASE),
        re.compile(r'\?$', re.IGNORECASE),
    ]
    
    # Vague/unclear patterns needing clarification
    UNCLEAR_PATTERNS = [
        re.compile(r'^(do|can you|please|just|maybe|something)', re.IGNORECASE),
        re.compile(r'^(it|that|this|the thing)', re.IGNORECASE),
    ]
    
    # Identity patterns
    IDENTITY_PATTERNS = [
        re.compile(r'(what|who)\s*(is|am)\s*(my|i)', re.IGNORECASE),
        re.compile(r'my\s+name', re.IGNORECASE),
        re.compile(r'do you (know|remember)', re.IGNORECASE),
        re.compile(r'you know (my|me|who)', re.IGNORECASE),
    ]
    
    def __init__(self, registry: Optional[ToolRegistry] = None):
        """
        Initialize the intent classifier.
        
        Args:
            registry: Tool registry for matching. Uses global if not provided.
        """
        self.registry = registry or get_registry()
        self.logger = logging.getLogger(__name__)
    
    def classify(self, user_text: str, memory_context: str = "") -> IntentResult:
        """
        Classify user intent.
        
        Args:
            user_text: The user's input text
            memory_context: Available memory context (for MEMORY_QUERY detection)
            
        Returns:
            IntentResult with classification
        """
        text = user_text.strip().lower()
        
        if not text:
            return IntentResult(
                intent_type=IntentType.CLARIFICATION,
                confidence=1.0,
                reason="Empty input"
            )
        
        # 1. Check for memory/identity queries first
        memory_result = self._check_memory_query(text, memory_context)
        if memory_result:
            return memory_result
        
        # 2. Check for greetings/simple conversation
        greeting_result = self._check_greeting(text)
        if greeting_result:
            return greeting_result
        
        # 3. Check for action intent (tool usage)
        action_result = self._check_action_intent(text)
        if action_result:
            return action_result
        
        # 4. Check for unclear/vague requests
        unclear_result = self._check_unclear(text)
        if unclear_result:
            return unclear_result
        
        # 5. Default to conversation
        return IntentResult(
            intent_type=IntentType.CONVERSATION,
            confidence=0.6,
            reason="No specific intent detected, defaulting to conversation"
        )
    
    def _check_memory_query(self, text: str, memory_context: str) -> Optional[IntentResult]:
        """Check if this is a memory/identity query"""
        
        for pattern in self.IDENTITY_PATTERNS:
            if pattern.search(text):
                # Check if we have relevant memory
                if memory_context:
                    return IntentResult(
                        intent_type=IntentType.MEMORY_QUERY,
                        confidence=0.9,
                        reason="Identity/memory question with context available"
                    )
                else:
                    # No memory, will need conversation response
                    return IntentResult(
                        intent_type=IntentType.CONVERSATION,
                        confidence=0.8,
                        reason="Identity question but no memory context"
                    )
        
        # Check direct memory keywords
        for keyword in self.MEMORY_KEYWORDS:
            if keyword in text:
                return IntentResult(
                    intent_type=IntentType.MEMORY_QUERY if memory_context else IntentType.CONVERSATION,
                    confidence=0.85,
                    reason=f"Memory keyword detected: {keyword}"
                )
        
        return None
    
    def _check_greeting(self, text: str) -> Optional[IntentResult]:
        """Check if this is a greeting or simple conversation"""
        
        for pattern in self.GREETING_PATTERNS:
            if pattern.search(text):
                return IntentResult(
                    intent_type=IntentType.CONVERSATION,
                    confidence=0.95,
                    reason="Greeting detected"
                )
        
        # Very short messages are usually conversational
        if len(text.split()) <= 2 and not any(v in text for v in self.ACTION_VERBS):
            return IntentResult(
                intent_type=IntentType.CONVERSATION,
                confidence=0.7,
                reason="Short conversational message"
            )
        
        return None
    
    def _check_action_intent(self, text: str) -> Optional[IntentResult]:
        """Check if this requires a tool action"""
        
        words = set(text.split())
        
        # Check for action verbs
        action_matches = words & self.ACTION_VERBS
        
        if action_matches:
            # Try to match to a specific tool
            best_match = self.registry.get_best_match(text, min_confidence=50.0)
            
            if best_match:
                return IntentResult(
                    intent_type=IntentType.TOOL_ACTION,
                    confidence=0.85,
                    matched_tool=best_match,
                    reason=f"Action verb '{list(action_matches)[0]}' + tool match: {best_match}"
                )
            else:
                # Action intent but no clear tool match
                matches = self.registry.match_tool(text, top_k=3)
                if matches and matches[0][1] > 40:
                    return IntentResult(
                        intent_type=IntentType.TOOL_ACTION,
                        confidence=0.7,
                        matched_tool=matches[0][0],
                        reason=f"Action verb detected, best guess: {matches[0][0]}"
                    )
        
        # Check for tool-specific keywords even without action verbs
        tool_keywords = {
            'spotify': 'music',
            'weather': 'weather', 
            'email': 'communication',
            'song': 'music',
            'track': 'music',
            'playlist': 'music',
            'temperature': 'weather',
        }
        
        for keyword, category in tool_keywords.items():
            if keyword in text:
                tools = self.registry.get_tools_by_category(category)
                if tools:
                    best_match = self.registry.get_best_match(text)
                    if best_match:
                        return IntentResult(
                            intent_type=IntentType.TOOL_ACTION,
                            confidence=0.75,
                            matched_tool=best_match,
                            reason=f"Tool keyword '{keyword}' detected"
                        )
                    else:
                        # Fallback to first tool in category
                        return IntentResult(
                            intent_type=IntentType.TOOL_ACTION,
                            confidence=0.6,
                            matched_tool=tools[0].name,
                            reason=f"Tool keyword '{keyword}' detected, using category default"
                        )
        
        return None
    
    def _check_unclear(self, text: str) -> Optional[IntentResult]:
        """Check if the request is too vague"""
        
        # Very short with vague words
        words = text.split()
        if len(words) <= 3:
            for pattern in self.UNCLEAR_PATTERNS:
                if pattern.search(text):
                    return IntentResult(
                        intent_type=IntentType.CLARIFICATION,
                        confidence=0.7,
                        reason="Vague request detected"
                    )
        
        return None
    
    def extract_params(self, text: str, tool_name: str) -> Dict[str, Any]:
        """
        Extract parameters for a tool from user text.
        
        Args:
            text: User's input
            tool_name: Name of the matched tool
            
        Returns:
            Dictionary of extracted parameters
        """
        params = {}
        tool = self.registry.get_tool(tool_name)
        
        if not tool:
            return params
        
        # Basic extraction patterns
        # This can be enhanced with more sophisticated NLP
        
        # Extract quoted strings
        quoted = re.findall(r'"([^"]*)"', text)
        if quoted:
            # Assign to first string parameter
            for param_name, param_info in tool.parameters.items():
                if isinstance(param_info, dict) and param_info.get('type') == 'string':
                    params[param_name] = quoted[0]
                    break
        
        # Extract email addresses
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        if emails:
            for param_name in ['to_email', 'email', 'recipient']:
                if param_name in tool.parameters:
                    params[param_name] = emails[0]
                    break
        
        # Extract cities for weather
        if 'weather' in tool_name.lower():
            # Common city extraction
            city_pattern = r'(?:in|at|for)\s+(\w+(?:\s+\w+)?)'
            city_match = re.search(city_pattern, text)
            if city_match:
                params['city'] = city_match.group(1).title()
        
        # Extract app_name for System Control tools
        if tool_name in ['open_app', 'close_app']:
            # Remove verb and common words to isolate app name
            clean_text = text.lower()
            
            # Common prefixes to strip
            prefixes = [
                'open', 'launch', 'start', 'run', 
                'close', 'stop', 'quit', 'kill', 'exit',
                'can you', 'please', 'could you', 'would you'
            ]
            
            # Sort by length desc to remove longest matches first
            prefixes.sort(key=len, reverse=True)
            
            for prefix in prefixes:
                if clean_text.startswith(prefix):
                    clean_text = clean_text[len(prefix):].strip()
            
            # Remove common suffixes/fillers
            fillers = ['app', 'application', 'program', 'browser']
            for filler in fillers:
                clean_text = clean_text.replace(f" {filler}", "").replace(f"{filler} ", "")
                
            clean_text = clean_text.strip()
            
            if clean_text:
                params['app_name'] = clean_text
        
        return params


# Global classifier instance (thread-safe)
_classifier: Optional[IntentClassifier] = None
_classifier_lock = threading.Lock()


def get_classifier() -> IntentClassifier:
    """Get the global intent classifier (thread-safe singleton)"""
    global _classifier
    
    # Fast path: check without lock for performance
    if _classifier is not None:
        return _classifier
    
    # Slow path: acquire lock and double-check
    with _classifier_lock:
        if _classifier is None:
            _classifier = IntentClassifier()
    
    return _classifier


def classify_intent(text: str, memory_context: str = "") -> IntentResult:
    """Convenience function to classify intent"""
    return get_classifier().classify(text, memory_context)
