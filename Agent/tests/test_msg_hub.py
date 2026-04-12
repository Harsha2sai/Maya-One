"""
Tests for MayaMsgHub (P28 infrastructure).
"""

import pytest
from core.messaging import MayaMsgHub, Msg


class MockAgent:
    """Mock agent for testing MsgHub."""
    
    def __init__(self, name: str):
        self.name = name
        self.received_messages = []
    
    async def reply(self, message: Msg) -> Msg:
        """AgentScope agents need a reply method."""
        self.received_messages.append(message)
        return Msg(name=self.name, content=f"Reply from {self.name}", role="assistant")
    
    async def observe(self, message: Msg) -> None:
        """AgentScope agents need an observe method for broadcasts."""
        self.received_messages.append(message)


@pytest.mark.asyncio
async def test_msg_hub_register_and_open():
    """Test basic registration and opening."""
    hub = MayaMsgHub()
    
    agent1 = MockAgent("agent1")
    agent2 = MockAgent("agent2")
    
    hub.register("agent1", agent1)
    hub.register("agent2", agent2)
    
    assert hub.get_participants() == ["agent1", "agent2"]
    assert not hub.is_active
    
    await hub.open()
    assert hub.is_active
    
    await hub.close()
    assert not hub.is_active


@pytest.mark.asyncio
async def test_msg_hub_context_manager():
    """Test context manager usage."""
    hub = MayaMsgHub()
    agent = MockAgent("test_agent")
    hub.register("test_agent", agent)
    
    assert not hub.is_active
    
    async with hub:
        assert hub.is_active
    
    assert not hub.is_active


@pytest.mark.asyncio
async def test_msg_hub_send_and_receive():
    """Test direct message sending and receiving."""
    hub = MayaMsgHub()
    
    agent1 = MockAgent("agent1")
    agent2 = MockAgent("agent2")
    
    hub.register("agent1", agent1)
    hub.register("agent2", agent2)
    
    async with hub:
        # Send message from agent1 to agent2
        await hub.send("agent1", "agent2", "Hello agent2!")
        
        # Receive the message
        msg = await hub.receive("agent2", timeout=1.0)
        
        assert msg is not None
        assert msg.name == "agent1"
        assert msg.content == "Hello agent2!"


@pytest.mark.asyncio
async def test_msg_hub_broadcast():
    """Test broadcast to all participants."""
    hub = MayaMsgHub()
    
    agent1 = MockAgent("agent1")
    agent2 = MockAgent("agent2")
    agent3 = MockAgent("agent3")
    
    hub.register("agent1", agent1)
    hub.register("agent2", agent2)
    hub.register("agent3", agent3)
    
    async with hub:
        # Broadcast should work (AgentScope handles distribution)
        await hub.broadcast("coordinator", "Hello everyone!", role="system")
        # Note: In real AgentScope, broadcast triggers each agent's reply
        # Our mock doesn't implement that, so we just verify no errors


@pytest.mark.asyncio
async def test_msg_hub_unregister():
    """Test unregistering participants."""
    hub = MayaMsgHub()
    
    agent1 = MockAgent("agent1")
    agent2 = MockAgent("agent2")
    
    hub.register("agent1", agent1)
    hub.register("agent2", agent2)
    
    assert len(hub.get_participants()) == 2
    
    hub.unregister("agent1")
    
    assert hub.get_participants() == ["agent2"]


@pytest.mark.asyncio
async def test_msg_hub_error_when_not_open():
    """Broadcast auto-opens, send still requires open."""
    hub = MayaMsgHub()
    agent = MockAgent("agent")
    hub.register("agent", agent)

    await hub.broadcast("sender", "content")
    assert hub.is_active

    await hub.close()
    with pytest.raises(RuntimeError, match="MsgHub not open"):
        await hub.send("sender", "agent", "content")


@pytest.mark.asyncio
async def test_msg_hub_receive_timeout():
    """Test receive with timeout when no messages."""
    hub = MayaMsgHub()
    agent = MockAgent("agent")
    hub.register("agent", agent)
    
    async with hub:
        # No messages sent, should timeout
        msg = await hub.receive("agent", timeout=0.1)
        assert msg is None
