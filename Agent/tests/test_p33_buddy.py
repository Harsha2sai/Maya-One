import pytest
from unittest.mock import AsyncMock, MagicMock

from core.buddy.memory import BuddyMemory, BuddyState
from core.buddy.evolution import BuddyEvolution, XP_REWARDS
from core.buddy.terminal_ui import render_buddy, render_stage_up


# --- Memory ---

def test_buddy_initial_state_is_stage_1(tmp_path):
    m = BuddyMemory(str(tmp_path / "buddy.db"))
    s = m.load()
    assert s.stage == 1
    assert s.xp == 0
    assert s.level == 1


def test_buddy_state_persists_across_instances(tmp_path):
    db = str(tmp_path / "buddy.db")
    m1 = BuddyMemory(db)
    s = m1.load()
    s.xp = 250
    s.stage = 2
    m1.save(s)

    m2 = BuddyMemory(db)
    s2 = m2.load()
    assert s2.xp == 250
    assert s2.stage == 2


# --- Evolution ---

def test_xp_award_on_task_complete(tmp_path):
    m = BuddyMemory(str(tmp_path / "buddy.db"))
    e = BuddyEvolution(m)
    xp, staged = e.award_xp("task_completed")
    assert xp == XP_REWARDS["task_completed"]
    assert staged is False


def test_xp_award_on_task_failed_is_smaller(tmp_path):
    m = BuddyMemory(str(tmp_path / "buddy.db"))
    e = BuddyEvolution(m)
    xp_fail, _ = e.award_xp("task_failed")
    xp_ok, _ = e.award_xp("task_completed")
    assert xp_ok > xp_fail


def test_team_coordinated_awards_more_xp_than_task(tmp_path):
    m = BuddyMemory(str(tmp_path / "buddy.db"))
    e = BuddyEvolution(m)
    assert XP_REWARDS["team_coordinated"] > XP_REWARDS["task_completed"]


def test_stage_progression_at_threshold(tmp_path):
    m = BuddyMemory(str(tmp_path / "buddy.db"))
    s = m.load()
    s.xp = 190
    m.save(s)
    e = BuddyEvolution(m)
    xp, staged = e.award_xp("team_coordinated")
    assert xp == 215
    assert staged is True
    assert m.load().stage == 2


def test_stage_up_returns_true_once_only(tmp_path):
    m = BuddyMemory(str(tmp_path / "buddy.db"))
    s = m.load()
    s.xp = 190
    m.save(s)
    e = BuddyEvolution(m)
    _, staged_first = e.award_xp("team_coordinated")
    _, staged_second = e.award_xp("task_completed")
    assert staged_first is True
    assert staged_second is False


# --- Terminal UI ---

def test_render_buddy_contains_xp_and_stage():
    s = BuddyState(xp=150, level=1, stage=2)
    out = render_buddy(s)
    assert "150" in out
    assert "2" in out


def test_render_stage_up_contains_stage_name():
    out = render_stage_up(2, "Apprentice")
    assert "Apprentice" in out
    assert "EVOLVED" in out


# --- BuddyTaskRouter ---

@pytest.mark.asyncio
async def test_route_task_calls_subagent_spawn():
    from core.buddy.task_router import BuddyTaskRouter

    mock_mgr = MagicMock()
    mock_instance = MagicMock()
    mock_instance.result = "research result"
    mock_instance.error = None
    mock_mgr.spawn = AsyncMock(return_value=mock_instance)

    router = BuddyTaskRouter(subagent_manager=mock_mgr)
    result = await router.route("explain asyncio", hint="research")

    mock_mgr.spawn.assert_called_once()
    call_kwargs = mock_mgr.spawn.call_args
    assert call_kwargs.kwargs.get("agent_type") == "researcher" or call_kwargs.args[0] == "researcher"
    assert result == "research result"
