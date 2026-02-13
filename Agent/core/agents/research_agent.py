"""
Research Agent - Specialized in knowledge retrieval and web research.
"""
import logging
from typing import Dict, Any
from core.agents.base import SpecializedAgent, AgentContext, AgentResponse
from core.intelligence.rag_engine import get_rag_engine

logger = logging.getLogger(__name__)

class ResearchAgent(SpecializedAgent):
    """
    Specialized agent for research tasks.
    Uses RAG and web search to gather information.
    """
    
    def __init__(self):
        super().__init__("research")
        self.research_keywords = [
            'research', 'find', 'look up', 'search', 'what is', 'who is',
            'explain', 'tell me about', 'information', 'learn', 'study'
        ]
    
    async def can_handle(self, request: str, context: AgentContext) -> float:
        """Determine if this is a research request"""
        request_lower = request.lower()
        
        # Check for research keywords
        keyword_matches = sum(1 for kw in self.research_keywords if kw in request_lower)
        
        # Check for question markers
        is_question = '?' in request or request_lower.startswith(('what', 'who', 'why', 'how', 'when', 'where'))
        
        # Calculate confidence
        confidence = 0.0
        if keyword_matches > 0:
            confidence += 0.4 * min(keyword_matches, 2)
        if is_question:
            confidence += 0.3
        
        return min(confidence, 1.0)
    
    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        """Execute research task"""
        try:
            self.logger.info(f"🔍 Research Agent processing: {request}")
            
            # 1. Check RAG knowledge base
            knowledge = await get_rag_engine().get_context(request)
            
            if knowledge:
                self.logger.info("📚 Found relevant knowledge in RAG")
                return AgentResponse(
                    success=True,
                    content=f"Based on my knowledge base:\n\n{knowledge}",
                    data={"source": "rag", "query": request}
                )
            
            # 2. If no RAG results, indicate need for web search
            self.logger.info("🌐 No local knowledge, recommending web search")
            return AgentResponse(
                success=True,
                content="I don't have information about this in my knowledge base. I would need to search the web.",
                data={"source": "none", "query": request},
                requires_handoff=True,
                handoff_to="web_search"  # Future capability
            )
            
        except Exception as e:
            self.logger.error(f"❌ Research Agent error: {e}")
            return AgentResponse(
                success=False,
                content="I encountered an error while researching.",
                error=str(e)
            )
    
    def get_capabilities(self) -> list:
        return [
            "Knowledge base search (RAG)",
            "Information retrieval",
            "Question answering",
            "Research assistance"
        ]
