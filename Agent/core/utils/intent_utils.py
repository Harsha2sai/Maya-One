def normalize_intent(intent):
    if intent is None:
        return None
    if hasattr(intent, "value"):
        return intent.value
    return str(intent)
