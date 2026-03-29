class WhatsAppAdapter:
    def __init__(self, server):
        self.server = server

    async def send_message(self, to, message):
        return await self.server.call_tool(
            tool_name="send_message",
            arguments={"to": to, "text": message}
        )
