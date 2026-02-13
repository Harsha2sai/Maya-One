from livekit.agents.llm import ChatChunk, Choice, Delta
import inspect

print(f"ChatChunk attributes: {dir(ChatChunk)}")
print(f"ChatChunk signature: {inspect.signature(ChatChunk)}")

try:
    chunk = ChatChunk(choices=[Choice(delta=Delta(content="test"))])
    print("Successfully created ChatChunk with choices")
except Exception as e:
    print(f"Failed to create ChatChunk with choices: {e}")
