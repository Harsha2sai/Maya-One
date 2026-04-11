from types import SimpleNamespace

from core.intent.classifier import IntentClassifier, IntentType


class _FakeRegistry:
    def get_best_match(self, text: str, min_confidence: float = 50.0):
        del min_confidence
        lowered = str(text or "").lower()
        if "reminder" in lowered:
            return "set_reminder"
        return None

    def match_tool(self, text: str, top_k: int = 3):
        del text, top_k
        return [("set_reminder", 60)]

    def get_tools_by_category(self, category: str):
        if category == "reminders":
            return [SimpleNamespace(name="set_reminder")]
        return []


def test_classify_with_context_promotes_ambiguous_followup_using_summary() -> None:
    classifier = IntentClassifier(registry=_FakeRegistry())

    without_context = classifier.classify("what's the reason")
    with_context = classifier.classify_with_context(
        "what's the reason",
        conversation_summary="We were setting a reminder for tomorrow morning at 9.",
    )

    assert without_context.intent_type != IntentType.TOOL_ACTION
    assert with_context.intent_type == IntentType.TOOL_ACTION


def test_classify_with_context_keeps_normal_path_for_non_ambiguous_input() -> None:
    classifier = IntentClassifier(registry=_FakeRegistry())

    base = classifier.classify("set a reminder for tomorrow morning")
    contextual = classifier.classify_with_context(
        "set a reminder for tomorrow morning",
        conversation_summary="We discussed reminders earlier.",
    )

    assert contextual.intent_type == base.intent_type
    assert contextual.matched_tool == base.matched_tool
