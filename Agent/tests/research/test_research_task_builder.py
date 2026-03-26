from __future__ import annotations

from core.research.research_task_builder import build_research_tasks


def _providers(tasks):
    return [task.provider for task in tasks]


def test_build_tasks_weather_query() -> None:
    tasks, fallback = build_research_tasks("what is the weather in hyderabad")
    providers = _providers(tasks)
    assert "weather" in providers
    assert "tavily" in providers
    assert fallback == "what is the weather in hyderabad"


def test_build_tasks_finance_query() -> None:
    tasks, fallback = build_research_tasks("tesla stock price and latest news")
    providers = _providers(tasks)
    assert "finance" in providers
    assert "news" in providers
    assert fallback == "tesla stock price and latest news"


def test_build_tasks_news_freshness_query() -> None:
    tasks, _fallback = build_research_tasks("who is the ceo of openai")
    providers = _providers(tasks)
    assert "news" in providers
    assert "tavily" in providers


def test_build_tasks_general_factual_query() -> None:
    tasks, _fallback = build_research_tasks("tell me about machine learning history")
    providers = _providers(tasks)
    assert "wikipedia" in providers
    assert "tavily" in providers


def test_build_tasks_default_fallback_when_no_pattern() -> None:
    tasks, _fallback = build_research_tasks("explain zero shot learning")
    providers = _providers(tasks)
    assert providers == ["tavily", "wikipedia"]
