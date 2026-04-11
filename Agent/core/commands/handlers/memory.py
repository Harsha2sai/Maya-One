from __future__ import annotations


def _memory_bucket(context: dict) -> dict:
    bucket = context.get("_command_memory")
    if isinstance(bucket, dict):
        return bucket
    bucket = {}
    context["_command_memory"] = bucket
    return bucket


async def handle_remember(args: str, context: dict) -> str:
    parts = str(args or "").split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /remember <key> <value>"
    key, value = parts[0], parts[1]

    memory = context.get("memory")
    if memory and hasattr(memory, "remember"):
        await memory.remember(key, value)
    else:
        _memory_bucket(context)[key] = value
    return f"Remembered '{key}'."


async def handle_forget(args: str, context: dict) -> str:
    key = str(args or "").strip()
    if not key:
        return "Usage: /forget <key>"

    memory = context.get("memory")
    if memory and hasattr(memory, "forget"):
        await memory.forget(key)
        return f"Forgot '{key}'."

    bucket = _memory_bucket(context)
    bucket.pop(key, None)
    return f"Forgot '{key}'."


async def handle_recall(args: str, context: dict) -> str:
    key = str(args or "").strip()
    if not key:
        return "Usage: /recall <key>"

    memory = context.get("memory")
    if memory and hasattr(memory, "recall"):
        value = await memory.recall(key)
    else:
        value = _memory_bucket(context).get(key)

    if value is None:
        return f"No memory for '{key}'."
    return f"{key}: {value}"

