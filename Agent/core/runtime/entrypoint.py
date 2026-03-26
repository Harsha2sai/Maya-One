
import logging
import re
from core.runtime.global_agent import GlobalAgentContainer
from core.observability.trace_context import current_trace_id, set_trace_context
from core.response.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


_CONSOLE_FAST_GREETING_RE = re.compile(r"^\s*(hi|hello|hey)\b", re.IGNORECASE)
_CONSOLE_FAST_IDENTITY_RE = re.compile(
    r"\b(what(?:'s| is)\s+your\s+name|who are you|who (?:made|created|built) you)\b",
    re.IGNORECASE,
)


def _try_console_preinit_fast_response(user_text: str) -> str | None:
    text = str(user_text or "").strip()
    if not text:
        return None
    if _CONSOLE_FAST_IDENTITY_RE.search(text):
        return "I'm Maya, your AI voice assistant, made by Harsha."
    if _CONSOLE_FAST_GREETING_RE.search(text):
        return "Hello. I'm Maya. How can I help you today?"
    if "how are you" in text.lower():
        return "I'm doing well. I'm ready to help."
    return None


async def console_entrypoint(user_text: str) -> None:
    """
    Strict Gateway for Console Input.
    
    Routes directly to the Global Shared Orchestrator via GlobalAgentContainer.
    Does NOT creating valid context, sessions, or orchestrators.
    """
    if not user_text:
        return

    try:
        set_trace_context(
            trace_id=current_trace_id(),
            session_id="console_session",
            user_id="console_user",
        )
        if not GlobalAgentContainer._initialized:
            fast_response = _try_console_preinit_fast_response(user_text)
            if fast_response:
                logger.info("console_preinit_fast_path_matched")
                print(f"\n🤖 Maya: {fast_response}\n")
                return
            await GlobalAgentContainer.initialize()

        # Route through the unified global container
        # This uses the exact same Orchestrator instance as the Worker would (minus audio)
        response = await GlobalAgentContainer.handle_user_message(user_text)
        
        # Print response to stdout for the user to see
        if response:
            normalized = ResponseFormatter.normalize_response(response)
            print(f"\n🤖 Maya: {normalized.display_text}\n")
            
    except Exception as e:
        logger.error(f"❌ Console processing error: {e}")
        print(f"❌ Error: {e}")
