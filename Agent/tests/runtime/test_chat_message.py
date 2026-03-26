from livekit.agents.llm import ChatMessage
try:
    msg = ChatMessage(role="user", content="hello")
    print("✅ String content accepted")
except Exception as e:
    print(f"❌ String content rejected: {e}")

try:
    msg = ChatMessage(role="user", content=["hello"])
    print("✅ List[str] content accepted")
except Exception as e:
    print(f"❌ List[str] content rejected: {e}")

try:
    msg = ChatMessage(role="user", content=[{"type": "text", "text": "hello"}])
    print("✅ List[dict] content accepted")
except Exception as e:
    print(f"❌ List[dict] content rejected: {e}")
