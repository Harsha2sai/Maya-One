
print("1. Starting test_startup_hang.py")
try:
    import aiohttp
    print("2. Imported aiohttp")
except ImportError as e:
    print(f"FAILED to import aiohttp: {e}")
except Exception as e:
    print(f"ERROR importing aiohttp: {e}")

try:
    from livekit import agents
    print("3. Imported livekit.agents")
except Exception as e:
    print(f"ERROR importing livekit.agents: {e}")

try:
    from livekit.agents.llm import utils
    print("4. Imported livekit.agents.llm.utils")
except Exception as e:
    print(f"ERROR importing livekit.agents.llm.utils: {e}")

print("5. Done")
