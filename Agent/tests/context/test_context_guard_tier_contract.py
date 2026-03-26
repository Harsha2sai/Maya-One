import logging

from core.context.context_guard import ContextGuard


def _message(role: str, content: str, source: str, **extra):
    data = {"role": role, "content": content, "source": source}
    data.update(extra)
    return data


def test_tier_contract_normal_turn_no_trimming(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "12000")
    monkeypatch.setenv("CONTEXT_HARD_LIMIT", "12000")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "2000")
    guard = ContextGuard()

    messages = [
        _message("system", "sys", "system_prompt"),
        _message("assistant", "step", "task_step"),
        _message("assistant", "previous user asked about weather", "history"),
        _message("assistant", "assistant answered weather", "history"),
        _message("assistant", "memory snippet", "memory", score=0.8),
        _message("user", "what is the time", "current_user"),
    ]

    with caplog.at_level(logging.INFO):
        guarded = guard.enforce(messages, origin="chat")

    assert len(guarded) == len(messages)
    assert "context_guard_truncated=False" in caplog.text
    assert "context_guard_hard_limit_reached" not in caplog.text


def test_tier_contract_long_conversation_summarizes_tier3_preserves_recent_tier2(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "12000")
    monkeypatch.setenv("CONTEXT_TIER3_SUMMARIZE_MIN_TOKENS", "10")
    monkeypatch.setenv("CONTEXT_TIER2_RECENT_TURNS", "5")
    guard = ContextGuard()

    history = [
        _message("user" if i % 2 == 0 else "assistant", f"history message {i} " * 20, "history")
        for i in range(10)
    ]
    messages = [_message("system", "sys", "system_prompt"), *history, _message("user", "latest", "current_user")]

    with caplog.at_level(logging.INFO):
        guarded = guard.enforce(messages, origin="voice")

    recent_contents = [m["content"] for m in history[-5:]]
    guarded_history_contents = [m["content"] for m in guarded if m.get("source") == "history"]
    for content in recent_contents:
        assert content in guarded_history_contents

    assert any(m.get("source") == "history_summary" for m in guarded)
    assert "context_guard_truncation_source=summary" in caplog.text


def test_tier_contract_tier1_overflow_logs_and_preserves_protected(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "12000")
    monkeypatch.setenv("MAX_PROTECTED_TOKENS", "40")
    guard = ContextGuard()

    messages = [
        _message("system", "sys", "system_prompt"),
        _message("assistant", "critical task state " * 30, "task_state"),
        _message("assistant", "critical tool output " * 30, "tool_output"),
        _message("assistant", "regular history", "history"),
        _message("user", "latest request", "current_user"),
    ]

    with caplog.at_level(logging.WARNING):
        guarded = guard.enforce(messages, origin="voice")

    assert "context_guard_tier1_overflow" in caplog.text
    assert any(m.get("source") == "task_state" for m in guarded)
    assert any(m.get("source") == "tool_output" for m in guarded)


def test_tier_contract_tier4_trim_drops_lowest_score_first(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "12000")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "40")
    guard = ContextGuard()

    messages = [
        _message("system", "sys", "system_prompt"),
        _message("assistant", "history", "history"),
        _message("assistant", "low score memory " * 10, "memory", score=0.1),
        _message("assistant", "high score memory " * 10, "memory", score=0.9),
        _message("assistant", "mid score memory " * 10, "memory", score=0.5),
        _message("user", "latest", "current_user"),
    ]

    with caplog.at_level(logging.INFO):
        guarded = guard.enforce(messages, origin="chat")

    memory_contents = [m["content"] for m in guarded if m.get("source") == "memory"]
    assert any("high score memory" in c for c in memory_contents)
    assert not any("low score memory" in c for c in memory_contents)
    assert "context_guard_tier4_trimmed dropped=" in caplog.text


def test_tier_contract_tier3_summarizer_failure_falls_back_to_recent_three(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "12000")
    monkeypatch.setenv("CONTEXT_TIER3_SUMMARIZE_MIN_TOKENS", "10")
    guard = ContextGuard()
    guard.rolling_summarizer.summarize_sync = lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timeout"))

    history = [
        _message("user" if i % 2 == 0 else "assistant", f"older history {i} " * 25, "history")
        for i in range(8)
    ]
    messages = [_message("system", "sys", "system_prompt"), *history, _message("user", "latest", "current_user")]

    with caplog.at_level(logging.INFO):
        guarded = guard.enforce(messages, origin="chat")

    older_kept = [m for m in guarded if m.get("source") == "history"]
    assert len(older_kept) == 8  # 5 recent + 3 fallback
    assert "context_guard_tier3_summarizer_fallback reason=timeout" in caplog.text


def test_tier_contract_hard_limit_safety_valve_trims_tier4_then_tier3_only(monkeypatch, caplog):
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "500")
    monkeypatch.setenv("CONTEXT_HARD_LIMIT", "160")
    monkeypatch.setenv("MAX_MEMORY_TOKENS", "500")
    monkeypatch.setenv("CONTEXT_TIER3_SUMMARIZE_MIN_TOKENS", "10")
    guard = ContextGuard()

    messages = [
        _message("system", "sys " * 20, "system_prompt"),
        _message("assistant", "protected step must stay " * 30, "task_step"),
        _message("assistant", "older history A " * 30, "history"),
        _message("assistant", "older history B " * 30, "history"),
        _message("assistant", "recent history C", "history"),
        _message("assistant", "recent history D", "history"),
        _message("assistant", "memory low " * 30, "memory", score=0.1),
        _message("assistant", "memory high " * 30, "memory", score=0.9),
        _message("user", "latest input", "current_user"),
    ]

    with caplog.at_level(logging.INFO):
        guarded = guard.enforce(messages, origin="voice")

    sources = [m.get("source") for m in guarded]
    assert "task_step" in sources
    assert "current_user" in sources
    assert "context_guard_hard_limit_reached" in caplog.text
    assert "context_guard_truncation_source=none" in caplog.text
