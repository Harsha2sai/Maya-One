import asyncio
from typing import Callable, Awaitable
from core.observability.trace_context import current_trace_id, set_trace_context


async def run_console_agent(entrypoint_fnc: Callable[..., Awaitable[None]]) -> None:
    """
    Console runtime harness.

    Called by LifecycleManager in CONSOLE mode.
    Responsible only for starting the interactive loop.
    """

    print("\n💬 CONSOLE MODE READY. Type 'exit' to quit.\n")

    loop = asyncio.get_running_loop()
    while True:
        try:
            # Non-blocking input to allow background tasks (TaskWorker) to run
            user_input = await loop.run_in_executor(None, input, "Enter message: ")
            user_input = user_input.strip()

            if user_input.lower() in {"exit", "quit"}:
                print("👋 Exiting console mode.")
                return

            # Call injected entrypoint
            set_trace_context(
                trace_id=current_trace_id(),
                session_id="console_session",
                user_id="console_user",
            )
            await entrypoint_fnc(user_input)

        except KeyboardInterrupt:
            print("\n👋 Console interrupted. Exiting.")
            return
