from livekit.agents.llm import ChatContext, ChatMessage
import inspect

ctx = ChatContext()
print(f"Attributes: {dir(ctx)}")
print(f"Has add_message: {hasattr(ctx, 'add_message')}")
print(f"messages types: {type(ctx.messages)}")
try:
    print(f"messages content: {ctx.messages}")
except Exception as e:
    print(f"Error accessing messages: {e}")

if hasattr(ctx, 'messages'):
    if callable(ctx.messages):
        print("messages is callable")
    else:
        print("messages is property/attribute")
