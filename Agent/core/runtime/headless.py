
import asyncio
import logging
from typing import Any, Callable, Dict, Optional
from livekit import agents

logger = logging.getLogger(__name__)

class HeadlessParticipant:
    """Mock participant for console user."""
    def __init__(self, identity: str = "console_user"):
        self.identity = identity
        self.name = "Console User"
        self.metadata = "{}"
        self.kind = "agent" # Close enough
        self.attributes = {}

class HeadlessRoom:
    """
    Mock LiveKit Room for Console Mode.
    Absorbs event subscriptions and data publishing without network I/O.
    """
    def __init__(self):
        self.name = "console-room"
        self.remote_participants = {
            "console_user": HeadlessParticipant()
        }
        self.local_participant = HeadlessParticipant("agent")
        self._handlers = {}

    def on(self, event: str, handler: Callable):
        """Register event handler (no-op but stores it)."""
        logger.debug(f"HeadlessRoom: Registered handler for '{event}'")
        self._handlers[event] = handler

    def emit(self, event: str, *args, **kwargs):
        """Trigger a local event handler."""
        if event in self._handlers:
            try:
                if asyncio.iscoroutinefunction(self._handlers[event]):
                    asyncio.create_task(self._handlers[event](*args, **kwargs))
                else:
                    self._handlers[event](*args, **kwargs)
            except Exception as e:
                logger.error(f"HeadlessRoom: Error in handler for '{event}': {e}")

    async def connect(self, *args, **kwargs):
        logger.info("HeadlessRoom: Connected (Virtual)")

    async def disconnect(self):
        logger.info("HeadlessRoom: Disconnected (Virtual)")

    # Data Packet Mocks
    async def perform_rpc(self, *args, **kwargs):
        logger.debug("HeadlessRoom: perform_rpc called (Ignored)")
        return "ok"

    async def local_participant_publish_data(self, *args, **kwargs):
        # We might want to capture this for verification!
        logger.debug(f"HeadlessRoom: Published data: {args} {kwargs}")

class HeadlessJob:
    """Mock Job"""
    def __init__(self):
        self.id = "job-console-123"

class HeadlessJobContext(agents.JobContext):
    """
    Mock JobContext that provides a HeadlessRoom.
    Satisfies AgentOrchestrator's dependency on `ctx.room`.
    """
    def __init__(self):
        # We don't call super().__init__ because it requires real arguments
        # We just mock the interface
        self._room = HeadlessRoom()
        self._job = HeadlessJob()
    
    @property
    def room(self):
        return self._room

    @property
    def job(self):
        return self._job
    
    @property
    def agent(self):
        return None 

    async def connect(self):
        pass
    
    async def disconnect(self):
        pass
