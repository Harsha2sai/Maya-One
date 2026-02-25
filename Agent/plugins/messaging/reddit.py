import os
import praw
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Reddit")

# Initialize Reddit client
reddit_client = None

def get_reddit():
    global reddit_client
    if reddit_client is None:
        reddit_client = praw.Reddit(
            client_id=os.environ.get("REDDIT_CLIENT_ID"),
            client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
            user_agent="Maya-One/0.1",
        )
    return reddit_client

@mcp.tool()
async def browse_subreddit(subreddit_name: str, limit: int = 10) -> str:
    """Browse a subreddit for hot posts."""
    try:
        r = get_reddit()
        subreddit = r.subreddit(subreddit_name)
        posts = []
        for submission in subreddit.hot(limit=limit):
            posts.append(f"Title: {submission.title}\nScore: {submission.score}\nURL: {submission.url}\nComments: {submission.num_comments}")
        return "\n---\n".join(posts) if posts else "No posts found."
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def search_reddit(query: str, limit: int = 10) -> str:
    """Search Reddit for posts."""
    try:
        r = get_reddit()
        posts = []
        for submission in r.subreddit("all").search(query, limit=limit):
            posts.append(f"Title: {submission.title}\nSubreddit: r/{submission.subreddit.display_name}\nScore: {submission.score}\nURL: {submission.url}")
        return "\n---\n".join(posts) if posts else "No posts found."
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()
