"""Specialized research routing agent used by the legacy agent registry."""
import logging

from core.agents.base import SpecializedAgent, AgentContext, AgentResponse
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult
from core.response.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)

class ResearchSpecialistAgent(SpecializedAgent):
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

    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        confidence = await self.can_handle(request.user_text, self._legacy_context_from_request(request))
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=confidence,
            reason="keyword_and_question_match",
            hard_constraints_passed=bool(str(request.user_text or "").strip()),
        )
    
    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        """Execute research task"""
        try:
            self.logger.info(f"🔍 Research Agent processing: {request}")

            # 1. Check RAG knowledge base
            from core.intelligence.rag_engine import get_rag_engine

            knowledge = await get_rag_engine().get_context(request)
            
            if knowledge:
                self.logger.info("📚 Found relevant knowledge in RAG")
                return ResponseFormatter.build_response(
                    f"Based on my knowledge base:\n\n{knowledge}",
                    structured_data={"source": "rag", "query": request},
                )
            
            # 2. If no RAG results, indicate need for web search
            self.logger.info("🌐 No local knowledge, recommending web search")
            return ResponseFormatter.build_response(
                "I don't have information about this in my knowledge base. I would need to search the web.",
                structured_data={"source": "none", "query": request},
                mode="direct",
            )
            
        except Exception as e:
            self.logger.error(f"❌ Research Agent error: {e}")
            return ResponseFormatter.build_response(
                "I encountered an error while researching.",
                structured_data={"error": str(e)},
            )

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text="Research handoff accepted.",
            voice_text=None,
            structured_payload={
                "query": request.user_text,
                "status": "accepted",
                "execution_mode": request.execution_mode,
            },
            next_action="continue",
        )
    
    def get_capabilities(self) -> list:
        return [
            "Knowledge base search (RAG)",
            "Information retrieval",
            "Question answering",
            "Research assistance"
        ]
