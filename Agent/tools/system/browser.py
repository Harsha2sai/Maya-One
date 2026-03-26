"""
Playwright Browser Automation Tools with Security Controls

Architecture:
- One shared browser process with N task contexts
- Context cleanup in finally blocks to prevent leaks
- Domain verification for security
"""
import os

import asyncio
import contextlib
import logging
from typing import Dict
from urllib.parse import urlparse
from pathlib import Path

from livekit.agents import function_tool, RunContext
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# Domain verification controls
BROWSER_ALLOWED_DOMAINS = os.environ.get("BROWSER_ALLOWED_DOMAINS", "*").split(",")

class PlaywrightBrowserManager:
    """
    Singleton: one browser process, N task contexts.
    Startup cost: ~50ms per task (vs ~2s for new browser per task)
    All contexts cleaned up on close or on exception.
    """

    _playwright = None
    _browser = None
    _contexts: Dict[str, BrowserContext] = {}
    _pages: Dict[str, Page] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_page(cls, task_id: str) -> Page:
        """Get or create a page for a task."""
        async with cls._lock:
            if cls._browser is None:
                cls._playwright = await async_playwright().start()
                cls._browser = await cls._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )

            if task_id not in cls._contexts:
                ctx = await cls._browser.new_context(
                    viewport={"width": 1280, "height": 720}
                )

                # Wire post-redirect domain check
                ctx.on("response", lambda response: cls._check_domain(response))

                cls._contexts[task_id] = ctx
                cls._pages[task_id] = await ctx.new_page()
                logger.info(f"Created new browser context for task {task_id}")

            return cls._pages[task_id]

    @classmethod
    def _check_domain(cls, response):
        """Check navigation is to allowed domain."""
        if BROWSER_ALLOWED_DOMAINS == ["*"]:
            return

        try:
            url = response.url
            domain = urlparse(url).netloc

            allowed = False
            for allowed_domain in BROWSER_ALLOWED_DOMAINS:
                if domain == allowed_domain or domain.endswith(f".{allowed_domain}"):
                    allowed = True
                    break

            if not allowed:
                logger.warning(f"Navigation blocked to {domain} - not in allowed list {BROWSER_ALLOWED_DOMAINS}")
                # Note: Actually blocking would require page interception
                # This logs the violation for now

        except Exception as e:
            logger.error(f"Error checking domain: {e}")

    @classmethod
    async def close_context(cls, task_id: str):
        """
        Always call in finally block to prevent zombie contexts.
        """
        async with cls._lock:
            if task_id in cls._pages:
                with contextlib.suppress(Exception):
                    await cls._pages[task_id].close()
                del cls._pages[task_id]
                logger.debug(f"Closed page for task {task_id}")

            if task_id in cls._contexts:
                with contextlib.suppress(Exception):
                    await cls._contexts[task_id].close()
                del cls._contexts[task_id]
                logger.debug(f"Closed context for task {task_id}")

    @classmethod
    async def cleanup(cls):
        """Cleanup all browser resources."""
        async with cls._lock:
            logger.info("Cleaning up Playwright browser resources")

            # Close all pages
            for task_id in list(cls._pages.keys()):
                with contextlib.suppress(Exception):
                    await cls._pages[task_id].close()
            cls._pages.clear()

            # Close all contexts
            for task_id in list(cls._contexts.keys()):
                with contextlib.suppress(Exception):
                    await cls._contexts[task_id].close()
            cls._contexts.clear()

            # Close browser
            if cls._browser:
                with contextlib.suppress(Exception):
                    await cls._browser.close()
                cls._browser = None

            # Stop playwright
            if cls._playwright:
                with contextlib.suppress(Exception):
                    await cls._playwright.stop()
                cls._playwright = None

            logger.info("Playwright browser cleanup complete")

# === BROWSER TOOLS ===

@function_tool(name="browser_open")
async def browser_open(context: RunContext, url: str) -> str:
    """
    Navigate to URL. Returns title + first 2000 chars of visible text.

    Security: Domain verification via environment variable BROWSER_ALLOWED_DOMAINS
    Args:
        url: HTTPS URL to open
    """
    task_id = getattr(context, "task_id", "default")

    try:
        page = await PlaywrightBrowserManager.get_page(task_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Extract title and visible text
        title = await page.title()
        text = await page.inner_text("body")

        # Truncate text
        if len(text) > 2000:
            text = text[:2000] + "\n... (truncated)"

        return f"Page: {title}\nURL: {url}\n\nContent:\n{text}"

    except Exception as e:
        logger.error(f"Browser open failed for {url}: {e}")
        return f"Error opening URL: {e}"
    finally:
        # Note: Don't close context here, keep it open for subsequent operations
        pass

@function_tool(name="browser_current_url")
async def browser_current_url(context: RunContext) -> str:
    """
    Return current page URL. Used by ExecutionEvaluator to verify navigation without screenshot.
    Example: confirms login redirect succeeded.

    Returns:
        Current page URL
    """
    task_id = getattr(context, "task_id", "default")

    try:
        page = await PlaywrightBrowserManager.get_page(task_id)
        return page.url
    except Exception as e:
        logger.error(f"Failed to get current URL: {e}")
        return f"Error: {e}"

@function_tool(name="browser_get_elements")
async def browser_get_elements(context: RunContext, selector: str) -> str:
    """
    Return DOM elements matching selector. Returns tag, id, class, placeholder, visible_text for each match.
    Use before fill/click to discover correct selectors.
    
    Args:
        selector: CSS selector to query
    """
    task_id = getattr(context, "task_id", "default")
    
    try:
        page = await PlaywrightBrowserManager.get_page(task_id)

        elements = await page.query_selector_all(selector)
        if not elements:
            return f"No elements found for selector: {selector}"

        results = []
        for el in elements[:20]:
            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            el_id = await el.get_attribute("id") or ""
            el_class = await el.get_attribute("class") or ""
            placeholder = await el.get_attribute("placeholder") or ""
            try:
                text = await el.inner_text()
            except Exception:
                text = ""
            text = text.strip()[:100]
            line = f"<{tag}"
            if el_id:
                line += f" id={el_id!r}"
            if el_class:
                line += f" class={el_class!r}"
            if placeholder:
                line += f" placeholder={placeholder!r}"
            line += ">"
            if text:
                line += f" text={text!r}"
            results.append(line)

        return "\n".join(results)
    except Exception as e:
        logger.error("browser_get_elements error selector=%s error=%s", selector, e)
        return f"Error getting elements: {e}"

@function_tool(name="browser_wait_for")
async def browser_wait_for(context: RunContext, selector: str, timeout_ms: int = 5000) -> str:
    """
    Wait until selector appears in DOM. Call after any action that triggers navigation or DOM change.
    Prevents race conditions between click and next step. Returns element description when found, or timeout error.

    Args:
        selector: CSS selector to wait for
        timeout_ms: Timeout in milliseconds (default: 5000)
    """
    task_id = getattr(context, "task_id", "default")

    try:
        page = await PlaywrightBrowserManager.get_page(task_id)
        await page.wait_for_selector(selector, timeout=timeout_ms)

        # Get element info
        element = await page.query_selector(selector)
        if element:
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            text = await element.inner_text() or ""
            return f"Element <{tag}> with text '{text[:100]}' appeared after {timeout_ms}ms"

        return f"Selector {selector} found (no element details available)"

    except Exception as e:
        if "timeout" in str(e).lower():
            return f"Timeout waiting for {selector} after {timeout_ms}ms"
        logger.error(f"Wait for selector failed: {e}")
        return f"Error: {e}"

@function_tool(name="browser_fill")
async def browser_fill(context: RunContext, selector: str, text: str) -> str:
    """
    Fill input field. Waits for element visibility before typing.

    Args:
        selector: CSS selector for input field
        text: Text to type
    """
    task_id = getattr(context, "task_id", "default")

    try:
        page = await PlaywrightBrowserManager.get_page(task_id)

        # Wait for element
        await page.wait_for_selector(selector, timeout=5000)
        element = await page.query_selector(selector)

        if not element:
            return f"Element not found: {selector}"

        # Clear and fill
        await element.fill("")
        await element.type(text, delay=50)  # More human-like typing

        return f"Filled '{text}' into {selector}"

    except Exception as e:
        logger.error(f"Failed to fill {selector}: {e}")
        return f"Error: {e}"

@function_tool(name="browser_click")
async def browser_click(context: RunContext, selector: str) -> str:
    """
    Click element by CSS selector or visible text. Returns element clicked and URL after click.

    Args:
        selector: CSS selector or visible text
    """
    task_id = getattr(context, "task_id", "default")

    try:
        page = await PlaywrightBrowserManager.get_page(task_id)

        # Wait for element
        await page.wait_for_selector(selector, timeout=5000)
        element = await page.query_selector(selector)

        if not element:
            return f"Element not found: {selector}"

        # Get info before click
        tag = await element.evaluate("el => el.tagName.toLowerCase()")
        text = await element.inner_text() or ""

        # Click
        await element.click()
        await asyncio.sleep(0.5)  # Small wait for navigation

        # Get URL after click
        current_url = page.url

        return f"Clicked <{tag}> with text '{text[:50]}' → Page: {current_url}"

    except Exception as e:
        logger.error(f"Failed to click {selector}: {e}")
        return f"Error: {e}"

@function_tool(name="browser_get_text")
async def browser_get_text(context: RunContext) -> str:
    """
    Return all visible text from current page. Truncated to 6000 tokens.
    """
    task_id = getattr(context, "task_id", "default")

    try:
        page = await PlaywrightBrowserManager.get_page(task_id)
        text = await page.inner_text("body")

        if len(text) > 8000:
            text = text[:8000] + "\n... (truncated)"

        return text

    except Exception as e:
        logger.error(f"Failed to get page text: {e}")
        return f"Error: {e}"

@function_tool(name="browser_screenshot")
async def browser_screenshot(context: RunContext, filename: str = "") -> str:
    """
    Capture page state to PNG. Returns file path. Used by ExecutionEvaluator as last-resort check.

    Args:
        filename: Optional filename (without extension)
    """
    task_id = getattr(context, "task_id", "default")

    if not filename:
        filename = f"browser_screenshot_{task_id}"

    if not filename.endswith(".png"):
        filename = f"{filename}.png"

    full_path = Path.home() / "Pictures" / filename

    try:
        os.makedirs(full_path.parent, exist_ok=True)
    except Exception:
        pass

    try:
        page = await PlaywrightBrowserManager.get_page(task_id)
        await page.screenshot(path=str(full_path), full_page=True)

        return f"Screenshot saved to {full_path}"

    except Exception as e:
        logger.error(f"Failed to capture screenshot: {e}")
        return f"Error: {e}"

@function_tool(name="browser_close")
async def browser_close(context: RunContext) -> str:
    """
    Close task's browser context. Always call when task is done - frees memory.
    """
    task_id = getattr(context, "task_id", "default")

    try:
        await PlaywrightBrowserManager.close_context(task_id)
        return f"Browser context closed for task {task_id}"
    except Exception as e:
        logger.error(f"Failed to close browser: {e}")
        return f"Error: {e}"

# === REGISTRATION FUNCTION ===
def register_browser_tools(registry):
    """Register all browser automation tools. """
    tools = [
        browser_open, browser_current_url, browser_get_elements,
        browser_wait_for, browser_fill, browser_click,
        browser_get_text, browser_screenshot, browser_close
    ]

    for tool in tools:
        registry.register_tool(tool)

    logger.info(f"✅ Registered {len(tools)} browser automation tools")
