import logging
from datetime import datetime
from livekit.agents import function_tool, RunContext

logger = logging.getLogger(__name__)

@function_tool()
async def get_current_datetime(
    context: RunContext,
    dummy: str = ""
) -> str:
    """Get the current date and time.
    
    Args:
        dummy: Unused parameter (optional)
    """
    import pytz
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    return f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}"

@function_tool()
async def get_date(
    context: RunContext,
    dummy: str = ""
) -> str:
    """Get today's date.
    
    Args:
        dummy: Unused parameter (optional)
    """
    import pytz
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    return f"Today is {now.strftime('%A, %B %d, %Y')}"

@function_tool()
async def get_time(
    context: RunContext,
    dummy: str = ""
) -> str:
    """Get the current time.
    
    Args:
        dummy: Unused parameter (optional)
    """
    import pytz
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    return f"The time is {now.strftime('%I:%M %p')}"
