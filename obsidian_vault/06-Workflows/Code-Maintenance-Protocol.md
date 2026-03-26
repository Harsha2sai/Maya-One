# Code Maintenance Protocol

**Protocol Version:** 1.0
**Last Updated:** 2026-03-17
**Status:** Active

## 🎯 Purpose
Standardized workflow for maintaining code quality, addressing issues, and preventing regressions in the Maya Agent codebase.

## 📋 Pre-Maintenance Checklist

Before starting maintenance:
- [ ] Review [[Analysis-Report]] for current issues
- [ ] Check [Obsidian Bug Reports](#) for active bugs
- [ ] Prioritize P0/P1 issues before P2/P3
- [ ] Plan testing approach
- [ ] Identify rollback strategy

## 🔧 Maintenance Categories

### 1. **Bug Fixes** (Priority: P0/P1)

**For reported bugs:**
1. Reproduce issue locally
2. Add failing test case
3. Fix bug with minimal changes
4. Verify test passes
5. Run full test suite
6. Update `Analysis-Bugs.md`

**Required verification:**
```bash
# Unit tests
pytest tests/test_*.py -v

# Integration tests
python scripts/system_validation.py

# Console mode (critical)
timeout 10 python agent.py console <<< "test"
```

### 2. **Code Quality Refactoring** (Priority: P2)

**Print → logger refactoring:**
```bash
# Find all print statements
grep -rn "^\s*print(" --include="*.py" core/

# Refactor to logger
# Before: print(f"Debug: {var}")
# After: logger.debug(f"Debug: {var}")
```

**Empty except blocks:**
```bash
# Find empty except blocks
grep -rn "except.*:\n\s*\(pass\|pass\)" --include="*.py" core/

# Add proper error handling
# Before:
# try:
#     operation()
# except:
#     pass

# After:
# try:
#     operation()
# except Exception as e:
#     logger.error(f"Operation failed: {e}", exc_info=True)
#     raise
```

**Type hints:**
```bash
# Check type coverage
mypy core/ --ignore-missing-imports

# Add missing hints
def function(x: int) -> int:
    ...
```

### 3. **Architecture Improvements** (Priority: P1)

**Tool schema standardization:**
1. Create issue in Analysis-Decisions.md
2. Design schema standard
3. Update SmartLLM, adapters, Worker
4. Remove `strict_tool_schema = False`
5. Add schema validation tests
6. Update Analysis-Report.md

**Schema alignment:**
```python
# Standard schema: tools must have proper format
# For functions with no args:
tool_schema = { "properties": {}, "required": [] }

# For functions with args:
tool_schema = { "properties": {"arg1": {...}, "arg2": {...}}, "required": ["arg1"] }
```

### 4. **Performance Optimization** (Priority: P2)

**Token pruning optimization:**
```python
# More aggressive context pruning
def optimize_context(builder, max_tokens=2000):
    tokens = count_tokens(builder.context)
    while tokens > max_tokens:
        # Remove oldest memory first
        oldest = builder.memory.pop(0)
        logger.warning(f"Pruned memory: {oldest}")
        tokens = count_tokens(builder.context)
    return builder
```

**File splitting:**
```bash
# Identify large files
find core/ -name "*.py" -type f -exec wc -l {} + | sort -nr | head -10

# Split logic:
# supabase.py → auth.py, data.py, rpc.py, storage.py
# provider_supervisor.py → by_provider_type.py
```

### 5. **Dependency Management** (Priority: P3)

**Audit dependencies:**
```bash
# Check for unused packages
pip install pip-check-reqs
pip-check-reqs --ignore-requirements=Agent/

# Update packages
pip list --outdated
pip install --upgrade package_name

# Pin versions
pip freeze > requirements.txt
```

**Security audit:**
```bash
# Check for vulnerabilities
pip install safety
safety check --json
```

### 6. **Documentation** (Priority: P3)

**Add docstrings:**
```python
def function(*args, **kwargs):
    """
    Brief description of what the function does.

    Args:
        arg1: Description of arg1
        arg2: Description of arg2

    Returns:
        Description of return value

    Raises:
        ValueError: When validation fails
    """
```

**Update vault:**
- Refactor notes in Obsidian vault
- Update component descriptions
- Add new decision records
- Link to updated code locations

## 🧪 Testing Requirements

### For Any Change
**Must pass:**
1. Import tests
```bash
python -c "import agent"
python -c "from core.runtime.global_agent import GlobalAgentContainer"
```

2. Configuration test
```bash
python config/settings.py
```

3. Console mode test (CRITICAL)
```bash
timeout 10 python agent.py console <<< "hello"
```

4. Full validation
```bash
python scripts/system_validation.py
```

### For Bug Fixes
```bash
# Add test that fails before fix
pytest tests/test_bug_reproduction.py -v

# Fix bug
# ... make changes ...

# Verify test passes
pytest tests/test_bug_reproduction.py -v
```

### For Refactoring
```bash
# Baseline benchmarks
python verification/run_benchmarks.py --save-baseline

# After refactoring
python verification/run_benchmarks.py --compare-baseline

# Performance must not regress > 5%
```

### For Architecture Changes
```bash
# Regression tests
pytest tests/ -v --asyncio-mode=auto

# Phase-specific tests
pytest tests/test_phase*.py -v

# Integration tests
./scripts/run_integration_tests.sh
```

## 📝 Documentation Updates

### For Code Changes
Update these Obsidian vault files:
1. **Bug fixes:** Update `Analysis-Bugs.md`
2. **New features:** Update `Analysis-Components.md`
3. **Architecture:** Update `Analysis-Architecture.md`
4. **Decisions:** Update `Analysis-Decisions.md`
5. **Workflows:** Update `Code-Maintenance-Protocol.md`

### Example Bug Fix Entry
```md
## Bug: [ID]

**Description:** [Description]

**Root Cause:** [Root cause]

**Fix Applied:** [Fix description]

**Date Fixed:** [Date]

**Status:** ✅ Fixed in commit [hash]

**Related Components:**
- [[Component A]]
- [[Component B]]

**Tests:**
- [Test file and case]
```

## 🚨 Emergency Procedures

### Critical Bug (P0)
1. Immediate triage
2. Revert if necessary (never push without approval)
3. Debug in isolation
4. Add comprehensive tests
5. Fix with PR
6. Deploy only after approval + tests

### Performance Regression
1. Identify cause
2. Rollback if > 10% impact
3. Profile to find bottlenecks
4. Optimize
5. Re-benchmark

### Security Vulnerability
1. Immediate assessment
2. Isolate affected code
3. Fix in secure branch
4. Security review
5. Deploy with urgency
6. Update security audit log

## 📊 Metrics

### Code Quality
- **TODO comments:** < 5 per commit
- **Empty except blocks:** 0 target
- **Print statements:** 0 target
- **Type coverage:** > 80%
- **Docstring coverage:** > 90% of public APIs

### Architecture
- **7-layer violations:** 0
- **Circular dependencies:** 0
- **Schema mismatches:** 0

### Testing
- **Test coverage:** Target > 85%
- **CI pass rate:** 100% on main
- **Console mode:** Always runnable

## 🔄 Review Schedule

### Daily
- Check logs for errors
- Monitor memory usage
- Review performance metrics

### Weekly
- Run full test suite
- Check for dependency updates
- Review vault notes accuracy

### Monthly
- Architecture compliance review
- Performance benchmarking
- Security audit

### Quarterly
- Full codebase review
- Technical debt assessment
- Architecture evolution plan

## ✅ Maintenance Checklist

**Before Commit:**
- [ ] Type check (`mypy core/`)
- [ ] Lint check (`flake8` or `ruff`)
- [ ] Import tests pass
- [ ] Configuration test passes
- [ ] Console mode test passes

**Before Merge:**
- [ ] Full test suite passes
- [ ] Performance benchmark
- [ ] Vault docs updated
- [ ] Analysis report updated

**After Deploy:**
- [ ] Monitor metrics
- [ ] Check error rates
- [ ] Verify console mode
- [ ] Update deployment log

---

**Next Review:** 2026-03-24 (weekly)
**QA Contact:** Code review team
**On-Call:** Check PagerDuty roster