class SpotifyAdapter:
    def __init__(self, server):
        self.server = server

    async def play_music(self, query):
        if not self.server:
            return "Error: Spotify server not initialized"
        return await self.server.call_tool(
            tool_name="play",
            arguments={"query": query}
        )
