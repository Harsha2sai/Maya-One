from livekit.agents import RunContext
import logging

logger = logging.getLogger(__name__)

def get_user_id(context: RunContext = None) -> str:
    """
    Extract user_id from the tool execution context.
    Falls back to 'anonymous' if not found.
    """
    if context and hasattr(context, 'job_context'):
        return getattr(context.job_context, 'user_id', 'anonymous')
    
    # Fallback for manual testing or if context is missing
    return 'anonymous'
