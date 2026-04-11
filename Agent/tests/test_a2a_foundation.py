import pytest

from core.a2a import MayaA2AServer


@pytest.mark.asyncio
async def test_maya_a2a_server_stub_lifecycle():
    server = MayaA2AServer(agent_name="maya", host="localhost", port=13000)
    started = await server.start()
    stopped = await server.stop()

    assert isinstance(server.available, bool)
    assert isinstance(started, bool)
    assert isinstance(stopped, bool)
