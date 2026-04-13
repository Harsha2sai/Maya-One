from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Google Drive")

@mcp.tool()
async def search_drive(query: str) -> str:
    return f"Results for {query}..."

if __name__ == "__main__":
    mcp.run()
