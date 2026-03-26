# Testing Workflow

## Purpose
Comprehensive testing strategy to ensure changes maintain system stability and don't break existing functionality.

## Testing Strategy

### 1. Import Tests
**Verify basic imports work:**
```bash
cd Agent
python -c "import agent"
python -c "from core.runtime.global_agent import GlobalAgentContainer"
```

### 2. Configuration Validation
**Check settings load correctly:**
```bash
python config/settings.py
```

### 3. Console Mode Test
**Primary test environment - must ALWAYS work:**
```bash
# Quick test
timeout 10 python agent.py console <<< "hello"

# Full session
python agent.py console
# Then test interactive: ask about weather, memory, etc.
```

### 4. Unit Tests
**Run specific test files:**
```bash
# Agent orchestration
pytest tests/test_agent_orchestrator.py -v

# Planning engine
pytest tests/test_planning_engine.py -v

# Worker dispatch
pytest tests/test_worker_dispatch.py -v

# Phase-specific tests
pytest tests/test_phase6*.py tests/test_phase7*.py -v
```

**Run with different modes:**
```bash
# With asyncio
pytest tests/ -v --asyncio-mode=auto

# With coverage
pytest --cov=core --cov-report=term-missing tests/

# Pattern matching
pytest -k "test_tts" -v
```

### 5. Integration Tests
**System validation:**
```bash
# Full validation (backend + Flutter)
python scripts/system_validation.py

# Backend-only
python scripts/system_validation.py --backend-only

# Quick validation (15s stability)
python scripts/system_validation.py --stability-secs 15
```

### 6. Smoke Tests
**Quick verification:**
```bash
# Backend smoke test (30s)
./scripts/smoke_backend_ci.sh

# Flutter roundtrip (60s)
./scripts/smoke_flutter_roundtrip.sh

# Run integration tests
./scripts/run_integration_tests.sh
```

### 7. Manual Testing
**Interactive testing:**
```bash
# Start test backend
./scripts/start_test_backend.sh

# Run Flutter
flutter run -d linux
# Test voice and message flow

# Monitor logs
tail -f Agent/agent_run.log
```

## Test Categories

### Phase Tests
Each architecture phase has dedicated tests:
- Phase 6: `test_phase6_context_gating.py`
- Phase 7: `test_phase7_trace_propagation.py`, `test_tts_priority_queue.py`

### Feature Tests
- End-to-end: `test_end_to_end.py`
- Worker dispatch: `test_worker_dispatch.py`
- Planning engine: `test_planning_engine.py`

## Validation Success Criteria
1. ✅ Console mode is runnable
2. ✅ All imports succeed
3. ✅ Configuration loads
4. ✅ Unit tests pass
5. ✅ Integration tests pass
6. ✅ No new errors in logs

## Related
- [[Development Workflow]]
- [[System Validation]]
- [[Debugging Protocol]]
- [[Common Issues]]
