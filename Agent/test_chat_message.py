from livekit.agents.llm import ChatMessage, ChatContent
import inspect
import pydantic

print(f"ChatMessage signature: {inspect.signature(ChatMessage)}")
try:
    msg = ChatMessage(role="system", content="test")
    print("Success with string")
except Exception as e:
    print(f"Failed with string: {e}")

try:
    msg = ChatMessage(role="system", content=["test"])
    print("Success with list of strings")
except Exception as e:
    print(f"Failed with list of strings: {e}")

try:
    content = ChatContent(text="test")
    msg = ChatMessage(role="system", content=[content])
    print("Success with list of ChatContent")
except Exception as e:
    print(f"Failed with list of ChatContent: {e}")
