import os
from mcp.server.fastmcp import FastMCP
from youtube_transcript_api import YouTubeTranscriptApi
import re

mcp = FastMCP("YouTube")

def extract_video_id(url_or_id: str) -> str:
    if len(url_or_id) == 11:
        return url_or_id
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url_or_id)
    return match.group(1) if match else url_or_id

@mcp.tool()
async def get_video_transcript(video_url: str, language: str = 'en') -> str:
    """Extract transcript from a YouTube video."""
    try:
        video_id = extract_video_id(video_url)
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        text = " ".join([item['text'] for item in transcript_list])
        return text
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def youtube_video_qa(video_url: str, question: str) -> str:
    """Ask a question about a video's content (uses transcript for context)."""
    transcript = await get_video_transcript(video_url)
    if transcript.startswith("Error:"):
        return transcript

    return f"Transcript Context: {transcript[:5000]}...\n\nUser Question: {question}\n\nPlease analyze the transcript above to answer the question."

if __name__ == "__main__":
    mcp.run()
