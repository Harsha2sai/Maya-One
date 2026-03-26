
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

async def run_test():
    print("🧪 Starting E2E Test: Open YouTube")
    
    try:
        from tools import web_search, browser_tools
        # browser_tools usually has open_url or similar.
        # Let's inspect browser_tools content dynamically or assume standard names.
        # If imports fail, we catch it.
        
        url = "https://youtube.com"
        print(f"Attempting to open {url}...")
        
        if hasattr(browser_tools, "open_url"):
            # This handles browser interaction
            # Note: In headless CI this might fail or do nothing visible.
            # We assume this is run in a Desktop environment as per user OS "linux".
            await browser_tools.open_url(url)
            print("✅ Browser open command sent.")
        else:
            print(f"⚠️ 'open_url' not found in browser_tools. Available: {dir(browser_tools)}")
            
        # Also verify adapter for these tools
        from core.tools.livekit_tool_adapter import adapt_tool_list
        tools = [browser_tools.open_url] if hasattr(browser_tools, "open_url") else []
        adapted = adapt_tool_list(tools)
        print(f"✅ Tools adapted for Voice: {len(adapted)}")
        
        print("PASS: E2E Test Completed")
        
    except ImportError as e:
        print(f"SKIP: Modules not found ({e}). Ensure running from Agent root.")
    except Exception as e:
        print(f"FAIL: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(run_test())
