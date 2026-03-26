# Development Workflow

## Purpose
Standardized workflow for making changes to the Maya Agent codebase while maintaining stability.

## Workflow Steps

### 1. Pre-Work: Understand Context
**Required Actions:**
- Read [[CLAUDE_PROJECT_CONTEXT.md]]
- Check [[Phase Architecture]] for current phase
- Identify runtime mode (console, voice, worker)
- Check git status for recent changes

### 2. Identify Issue Priority
**Priority Hierarchy:**
- P0 - CRITICAL: Runtime crashes, boot failures, DB corruption, tool failures
- P1 - HIGH: Console not runnable, provider issues, token violations
- P2 - MEDIUM: Deprecated APIs, missing error handling, test failures
- P3 - LOW: New features, refactoring, documentation, style changes

**Rule**: Never work on P2/P3 when P0/P1 issues exist.

### 3. Change Philosophy
**Minimal, Surgical Fixes:**
- ✅ GOOD: Small, targeted fix (< 20 lines)
- ❌ BAD: Large refactor > 100 lines (requires approval)

**Preserve Backward Compatibility:**
- Don't change function signatures without deprecation
- Keep console mode working
- Maintain existing environment variables

### 4. Implementation
**Testing Requirements:**
**Before Change:**
- `python -c "from core.runtime.global_agent import GlobalAgentContainer; print('Imports OK')"`
- `python config/settings.py`

**After Change:**
1. `python -c "import agent"`
2. `timeout 10 python agent.py console <<< "hello"`
3. `python config/settings.py`
4. `python scripts/system_validation.py`

**Console mode must ALWAYS remain runnable.** If console mode breaks, the change is invalid.

### 5. Verification
**Quick Validation Suite:**
- `python scripts/system_validation.py`
- `./scripts/smoke_backend_ci.sh`
- `./scripts/smoke_flutter_roundtrip.sh`
- `python config/settings.py`
- `python -c "import agent"`

**Testing:**
- Run specific tests: `pytest tests/test_agent_orchestrator.py::test_handle_message -v`
- Run pattern: `pytest -k "test_phase7" -v`
- Run with asyncio: `pytest tests/ -v --asyncio-mode=auto`

## Key Rules
- **ALWAYS test in console mode first**
- **ALWAYS keep console mode working**
- **ALWAYS add error handling**
- **Log appropriately** (debug/info/warning/error)
- **Use proper imports** (absolute for core, local in methods to avoid circular deps)

## Related
- [[Testing Workflow]]
- [[Debugging Protocol]]
- [[System Validation]]
- [[Code Change Philosophy]]
