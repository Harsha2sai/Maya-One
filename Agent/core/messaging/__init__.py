"""
Maya messaging layer using AgentScope MsgHub.
Replaces the planned custom bus.py + progress_stream.py.
"""

from typing import Any, Dict, List, Optional, Callable
import asyncio
from agentscope.pipeline import MsgHub
from agentscope.message import Msg


class MayaMsgHub:
    """
    Thin Maya wrapper around AgentScope MsgHub.
    Provides inter-agent communication for subagents and teams.
    
    Phase 28: Infrastructure only — not yet used by orchestrator.
    Phase 29: SubAgentManager will use this for IPC.
    Phase 30: TeamCoordinator will use this for team communication.
    """
    
    def __init__(self):
        self._hub: Optional[MsgHub] = None
        self._participants: Dict[str, Any] = {}
        self._active = False
    
    async def __aenter__(self):
        """Context manager entry — opens hub with registered participants."""
        await self.open()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit — closes hub."""
        await self.close()
    
    async def open(self) -> "MayaMsgHub":
        """
        Open the message hub with current participants.
        Must be called before broadcast/send.
        """
        if self._active:
            return self
        
        participant_list = list(self._participants.values())
        if participant_list:
            self._hub = MsgHub(participants=participant_list)
        
        self._active = True
        return self
    
    async def close(self):
        """Close the message hub."""
        self._active = False
        self._hub = None
    
    def register(self, name: str, agent_obj: Any):
        """
        Register an agent as a participant.
        Must be called before open().
        
        Args:
            name: Agent identifier (e.g., "coder", "reviewer")
            agent_obj: Agent instance (must have reply() method for AgentScope)
        """
        self._participants[name] = agent_obj
    
    def unregister(self, name: str):
        """Remove an agent from participants."""
        self._participants.pop(name, None)
    
    async def broadcast(self, sender: str, content: str, role: str = "assistant"):
        """
        Broadcast message to all participants.
        
        Args:
            sender: Name of sending agent
            content: Message content
            role: Message role (user/assistant/system)
        """
        if not self._active or not self._hub:
            raise RuntimeError("MsgHub not open — call open() first")
        
        msg = Msg(name=sender, content=content, role=role)
        await self._hub.broadcast(msg)
    
    async def send(self, sender: str, recipient: str, content: str, role: str = "assistant"):
        """
        Send message to specific participant.
        
        Args:
            sender: Name of sending agent
            recipient: Name of recipient agent
            content: Message content
            role: Message role
        """
        if not self._active or not self._hub:
            raise RuntimeError("MsgHub not open — call open() first")
        
        if recipient not in self._participants:
            raise ValueError(f"Recipient '{recipient}' not registered")
        
        msg = Msg(name=sender, content=content, role=role)
        recipient_agent = self._participants[recipient]
        
        # AgentScope MsgHub doesn't have direct send — use participant's reply
        # For now, store in a queue that recipient can poll
        if not hasattr(self, '_message_queues'):
            self._message_queues: Dict[str, asyncio.Queue] = {}
        
        if recipient not in self._message_queues:
            self._message_queues[recipient] = asyncio.Queue()
        
        await self._message_queues[recipient].put(msg)
    
    async def receive(self, recipient: str, timeout: Optional[float] = None) -> Optional[Msg]:
        """
        Receive a message sent to this recipient.
        
        Args:
            recipient: Name of recipient agent
            timeout: Optional timeout in seconds
            
        Returns:
            Message or None if timeout
        """
        if not hasattr(self, '_message_queues'):
            return None
        
        queue = self._message_queues.get(recipient)
        if not queue:
            return None
        
        try:
            if timeout:
                return await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                return await queue.get()
        except asyncio.TimeoutError:
            return None
    
    def get_participants(self) -> List[str]:
        """Get list of registered participant names."""
        return list(self._participants.keys())
    
    @property
    def is_active(self) -> bool:
        """Check if hub is currently open."""
        return self._active


__all__ = ["MayaMsgHub", "Msg"]
