"""
Example Skill: Weather Lookup
Demonstrates the skill package format.
"""
from core.skills.schema import Skill, SkillMetadata, SkillFunction, PermissionLevel
import logging

logger = logging.getLogger(__name__)

async def get_weather(city: str) -> str:
    """Get weather for a city"""
    # This would call a real weather API
    logger.info(f"🌤️ Getting weather for {city}")
    return f"Weather in {city}: Sunny, 72°F (simulated)"

async def get_forecast(city: str, days: int = 3) -> str:
    """Get weather forecast"""
    logger.info(f"📅 Getting {days}-day forecast for {city}")
    return f"{days}-day forecast for {city}: Mostly sunny (simulated)"

def init_weather_skill():
    """Initialize the weather skill"""
    logger.info("🌤️ Weather skill initialized")

def cleanup_weather_skill():
    """Cleanup the weather skill"""
    logger.info("🌤️ Weather skill cleaned up")

def create_skill() -> Skill:
    """Create the weather skill package"""
    
    metadata = SkillMetadata(
        name="weather",
        version="1.0.0",
        description="Weather lookup and forecasting",
        author="Maya-One Team",
        permissions=[PermissionLevel.NETWORK],
        tags=["weather", "forecast", "utility"]
    )
    
    functions = [
        SkillFunction(
            name="get_weather",
            description="Get current weather for a city",
            handler=get_weather,
            parameters={
                "city": {"type": "string", "description": "City name"}
            },
            required_params=["city"]
        ),
        SkillFunction(
            name="get_forecast",
            description="Get weather forecast",
            handler=get_forecast,
            parameters={
                "city": {"type": "string", "description": "City name"},
                "days": {"type": "integer", "description": "Number of days"}
            },
            required_params=["city"]
        )
    ]
    
    return Skill(
        metadata=metadata,
        functions=functions,
        init_handler=init_weather_skill,
        cleanup_handler=cleanup_weather_skill
    )
