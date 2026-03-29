from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Video Agent")

@mcp.tool()
async def generate_video_script(topic: str) -> str:
    return f"Script for {topic}..."

if __name__ == "__main__":
    mcp.run()
