import asyncio

import pytest

from core.governance.types import UserRole
from core.permissions.contracts import PermissionMode
from core.skills import (
    BaseSkill,
    CodeAnalysisSkill,
    FileOperationsSkill,
    SkillExecutor,
    SkillPermissionLevel,
    SkillRegistry,
    SkillResult,
    WebSearchSkill,
)


class _DummySkill(BaseSkill):
    def __init__(self, name="dummy", level=SkillPermissionLevel.SAFE, permission_tool_name=None):
        super().__init__(
            name=name,
            description="dummy skill",
            permission_level=level,
            permission_tool_name=permission_tool_name,
        )

    async def execute(self, params):
        return SkillResult(success=True, data={"echo": params.get("value")})


class _InvalidSkill(_DummySkill):
    def validate(self, params):
        return False


class _ExplodingSkill(_DummySkill):
    async def execute(self, params):
        raise RuntimeError("boom")


class _DenyChecker:
    def check(self, tool_name, user_role, context):
        class _Res:
            allowed = False
            reason = "blocked by policy"
            mode = PermissionMode.DEFAULT

        return _Res()


class _AllowChecker:
    def check(self, tool_name, user_role, context):
        class _Res:
            allowed = True
            reason = None
            mode = PermissionMode.DEFAULT

        return _Res()


class _FakeReport:
    def to_dict(self):
        return {
            "success": True,
            "summary": "ok",
            "findings": [],
            "unavailable_tools": [],
        }


class _FakeSecurityAgent:
    async def scan_code(self, file_path):
        return _FakeReport()


def test_registry_register_get_unregister_base_skill():
    registry = SkillRegistry()
    skill = _DummySkill(name="alpha")

    assert registry.register(skill) is True
    assert registry.get("alpha") is skill
    assert registry.unregister("alpha") is True
    assert registry.get("alpha") is None


def test_registry_register_rejects_duplicate_without_replace():
    registry = SkillRegistry()

    assert registry.register(_DummySkill(name="alpha")) is True
    assert registry.register(_DummySkill(name="alpha")) is False


def test_registry_register_replace_overwrites_existing():
    registry = SkillRegistry()
    first = _DummySkill(name="alpha")
    second = _DummySkill(name="alpha")

    assert registry.register(first) is True
    assert registry.register(second, replace=True) is True
    assert registry.get("alpha") is second


def test_registry_register_requires_base_skill_instance():
    registry = SkillRegistry()

    with pytest.raises(TypeError):
        registry.register("not-a-skill")


def test_registry_list_by_permission_and_names():
    registry = SkillRegistry()
    registry.register(_DummySkill(name="safe_one", level=SkillPermissionLevel.SAFE))
    registry.register(_DummySkill(name="sys_one", level=SkillPermissionLevel.SYSTEM))

    assert registry.list_skill_names() == ["safe_one", "sys_one"]
    assert registry.list_by_permission("safe") == ["safe_one"]
    assert registry.list_by_permission(SkillPermissionLevel.SYSTEM) == ["sys_one"]


@pytest.mark.asyncio
async def test_skill_executor_runs_registered_skill_successfully():
    registry = SkillRegistry()
    registry.register(_DummySkill(name="echo", permission_tool_name="web_search"))
    executor = SkillExecutor(registry=registry, permission_checker=_AllowChecker())

    result = await executor.execute("echo", {"value": 5}, user_role=UserRole.USER)

    assert result.success is True
    assert result.data["echo"] == 5


@pytest.mark.asyncio
async def test_skill_executor_returns_not_found_for_unknown_skill():
    executor = SkillExecutor(registry=SkillRegistry(), permission_checker=_AllowChecker())

    result = await executor.execute("missing", {}, user_role=UserRole.USER)

    assert result.success is False
    assert result.error == "skill_not_found:missing"


@pytest.mark.asyncio
async def test_skill_executor_rejects_invalid_params():
    registry = SkillRegistry()
    registry.register(_InvalidSkill(name="invalid", permission_tool_name="web_search"))
    executor = SkillExecutor(registry=registry, permission_checker=_AllowChecker())

    result = await executor.execute("invalid", {"value": 1}, user_role=UserRole.USER)

    assert result.success is False
    assert result.error == "invalid_skill_params:invalid"


@pytest.mark.asyncio
async def test_skill_executor_denies_by_permission_tier():
    registry = SkillRegistry()
    registry.register(_DummySkill(name="ops", level=SkillPermissionLevel.SYSTEM, permission_tool_name="open_app"))
    executor = SkillExecutor(registry=registry, permission_checker=_AllowChecker())

    result = await executor.execute("ops", {"value": 1}, user_role=UserRole.USER)

    assert result.success is False
    assert "role_tier_required:system" in str(result.error)


@pytest.mark.asyncio
async def test_skill_executor_denies_when_permission_checker_blocks():
    registry = SkillRegistry()
    registry.register(_DummySkill(name="echo", permission_tool_name="web_search"))
    executor = SkillExecutor(registry=registry, permission_checker=_DenyChecker())

    result = await executor.execute("echo", {"value": 3}, user_role=UserRole.ADMIN)

    assert result.success is False
    assert "permission_denied" in str(result.error)


@pytest.mark.asyncio
async def test_skill_executor_handles_skill_exception():
    registry = SkillRegistry()
    registry.register(_ExplodingSkill(name="explode", permission_tool_name="web_search"))
    executor = SkillExecutor(registry=registry, permission_checker=_AllowChecker())

    result = await executor.execute("explode", {"x": 1}, user_role=UserRole.ADMIN)

    assert result.success is False
    assert "skill_execution_failed" in str(result.error)


@pytest.mark.asyncio
async def test_web_search_skill_validate_and_execute():
    calls = []

    async def _search_fn(*, query, max_results):
        calls.append((query, max_results))
        return {"success": True, "results": [{"title": "A"}], "result_count": 1}

    skill = WebSearchSkill(search_fn=_search_fn)

    assert skill.validate({"query": "python"}) is True
    assert skill.validate({"query": "   "}) is False

    result = await skill.execute({"query": "python", "max_results": 2})
    assert result.success is True
    assert calls == [("python", 2)]
    assert result.data["result_count"] == 1


@pytest.mark.asyncio
async def test_code_analysis_skill_validate_and_execute_with_fake_agent():
    skill = CodeAnalysisSkill(security_agent=_FakeSecurityAgent())

    assert skill.validate({"file_path": "src/app.py"}) is True
    assert skill.validate({"file_path": ""}) is False

    result = await skill.execute({"file_path": "src/app.py"})
    assert result.success is True
    assert result.data["report"]["summary"] == "ok"


@pytest.mark.asyncio
async def test_file_operations_skill_list_read_write(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")

    skill = FileOperationsSkill(base_path=str(root), allow_write=True)

    listed = await skill.execute({"operation": "list", "path": "."})
    read = await skill.execute({"operation": "read", "path": "a.txt"})
    write = await skill.execute({"operation": "write", "path": "b.txt", "content": "world"})

    assert listed.success is True
    assert "a.txt" in listed.data["entries"]
    assert read.success is True
    assert read.data["content"] == "hello"
    assert write.success is True
    assert (root / "b.txt").read_text(encoding="utf-8") == "world"


@pytest.mark.asyncio
async def test_file_operations_skill_denies_write_when_disabled(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    skill = FileOperationsSkill(base_path=str(root), allow_write=False)

    result = await skill.execute({"operation": "write", "path": "x.txt", "content": "x"})

    assert result.success is False
    assert result.error == "write_not_allowed"


@pytest.mark.asyncio
async def test_file_operations_skill_blocks_path_escape(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    skill = FileOperationsSkill(base_path=str(root), allow_write=True)

    result = await skill.execute({"operation": "read", "path": "../outside.txt"})

    assert result.success is False
    assert "invalid_path" in str(result.error)


@pytest.mark.asyncio
async def test_file_operations_validate_rejects_bad_operation():
    skill = FileOperationsSkill()
    assert skill.validate({"operation": "delete", "path": "x"}) is False


@pytest.mark.asyncio
async def test_executor_with_built_in_web_search_skill():
    registry = SkillRegistry()

    async def _search_fn(*, query, max_results):
        return {"success": True, "result_count": 0, "results": []}

    registry.register(WebSearchSkill(search_fn=_search_fn))
    executor = SkillExecutor(registry=registry, permission_checker=_AllowChecker())

    result = await executor.execute("web_search", {"query": "maya"}, user_role=UserRole.USER)
    assert result.success is True
    assert result.data["result_count"] == 0


@pytest.mark.asyncio
async def test_executor_with_built_in_file_operations_skill_needs_trusted(tmp_path):
    registry = SkillRegistry()
    registry.register(FileOperationsSkill(base_path=str(tmp_path), allow_write=True))
    executor = SkillExecutor(registry=registry, permission_checker=_AllowChecker())

    denied = await executor.execute("file_operations", {"operation": "list", "path": "."}, user_role=UserRole.USER)
    allowed = await executor.execute("file_operations", {"operation": "list", "path": "."}, user_role=UserRole.TRUSTED)

    assert denied.success is False
    assert allowed.success is True
