import logging
import asyncio
import requests
from livekit.agents import function_tool, RunContext

logger = logging.getLogger(__name__)

@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get the current weather for a given city."""
    try:
        response = await asyncio.to_thread(requests.get, f"https://wttr.in/{city}?format=3", timeout=5)
        if response.status_code == 200:
            logger.info(f"Weather for {city}: {response.text.strip()}")
            return response.text.strip()   
        else:
            logger.error(f"Failed to get weather for {city}: {response.status_code}")
            return f"Could not retrieve weather for {city}."
    except Exception as e:
        logger.error(f"Error retrieving weather for {city}: {e}")
        return f"An error occurred while retrieving weather for {city}." 

@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    """Search the web using DuckDuckGo."""
    try:
        def _search():
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=3))
        
        # Add timeout to prevent hanging
        results = await asyncio.wait_for(asyncio.to_thread(_search), timeout=5.0)
        
        if results:
            response = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
            logger.info(f"Search results for '{query}': {len(results)} found")
            return response
        return f"No results found for '{query}'"
    except asyncio.TimeoutError:
        logger.warning(f"Web search timed out for '{query}'")
        return "I'm sorry, the search timed out. Please try again."
    except Exception as e:
        logger.error(f"Error searching the web for '{query}': {e}")
        return f"An error occurred while searching the web for '{query}'."
