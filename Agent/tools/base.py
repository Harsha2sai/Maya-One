import logging
import os
import json
from livekit.agents import RunContext

logger = logging.getLogger(__name__)

def get_user_id(context: RunContext) -> str:
    """
    Extract user_id from LiveKit context.
    Tries multiple fallback strategies to ensure we always have a user_id.
    """
    # Strategy 1: Check if user_id attached to job_context
    if hasattr(context, 'job') and hasattr(context.job, 'user_id'):
        return context.job.user_id
    
    # Strategy 2: Check participant metadata (set during connection)
    if hasattr(context, 'room') and hasattr(context.room, 'local_participant'):
        participant = context.room.local_participant
        if hasattr(participant, 'metadata'):
            try:
                metadata = json.loads(participant.metadata)
                if 'user_id' in metadata:
                    return metadata['user_id']
            except:
                pass
    
    # Strategy 3: Environment fallback (for testing)
    fallback = os.getenv("USER_ID_FALLBACK", "anonymous-user")
    logger.warning(f"⚠️ Could not extract user_id from context, using fallback: {fallback}")
    return fallback
