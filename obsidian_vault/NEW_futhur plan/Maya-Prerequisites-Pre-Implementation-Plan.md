# Maya Prerequisites & Pre-Implementation Plan

**Date:** April 5, 2025  
**Status:** Critical - Must Complete Before Main Plan  
**Version:** 1.0  
**Related:** P23 Plan, Multi-Agent Architecture, Extended Integration Plan

---

## Executive Summary

This document outlines **critical blockers and prerequisites** that must be resolved before implementing the Maya Multi-Agent Architecture Plan. Based on comprehensive analysis of the current codebase, attempting to implement subagents, A2A protocol, and background tasks without first addressing these issues will result in:

- ❌ Architecture conflicts and circular dependencies
- ❌ Excessive orchestrator bloat (>4,000 lines)
- ❌ Failed background task recovery
- ❌ Broken backward compatibility
- ❌ Unmaintainable testing surface

**Timeline:** 1-2 weeks preparation before Phase 1 can begin.

---

## Part 1: Current Architecture Analysis

### 1.1 Codebase Statistics

| Component | Lines | Status | Risk Level |
|-----------|-------|--------|------------|
| `agent_orchestrator.py` | **3,776** | ⚠️ Overweight | **CRITICAL** |
| `agent_router.py` | 329 | ✅ Good | Low |
| `chat_mixin.py` | 911 | ✅ Good | Low |
| `handoff_manager.py` | 133 | ⚠️ Limited | **HIGH** |
| `task_worker.py` | ~600 | ✅ Functional | Medium |
| `task_store.py` | ~800 | ✅ Good | Low |
| `planning_engine.py` | ~600 | ✅ Good | Low |
| **Total Core** | ~7,000 | ⚠️ Needs restructure | **HIGH** |

### 1.2 Directory Structure

```
Agent/core/
├── agents/              # 12 files - Basic but functional
├── orchestrator/        # 10 files - Monolithic central hub
├── tasks/               # 15 files - Task system exists
├── memory/              # 20 files - Hybrid memory working
├── tools/               # 10 files - ~20 tools currently
├── context/             # Complex but stable
├── security/            # Solid foundation
├── llm/                 # Role-based LLM system
├── runtime/             # Session management
├── routing/             # Intent routing
├── registry/            # Tool registry
└── skills/              # Minimal framework only
```

---

## Part 2: Critical Blockers (Must Fix)

### Blocker #1: Orchestrator Monolith (SEVERITY: CRITICAL)

**Current State:**
```
File: core/orchestrator/agent_orchestrator.py
Size: 3,776 lines (149KB)
Problem: Directly handles routing, delegation, memory, research, media, scheduling
```

**Why This Blocks Implementation:**

The comprehensive plan requires adding:
- SubAgentManager (200+ lines)
- TeamCoordinator (150+ lines)
- ProjectManager (300+ lines)
- BackgroundExecutor (200+ lines)
- A2A integration (400+ lines)

**Result would be: 3,776 + 1,250 = 5,026 lines** ❌

**Required Fix:**

Complete **P23 Plan - Delegation Conversion** BEFORE starting main plan:

```python
# BEFORE (Current - Direct Implementation):
class AgentOrchestrator:
    async def handle_research(self, request):
        # 200 lines of research logic here
        pass
    
    async def handle_media(self, request):
        # 150 lines of media logic here
        pass
    
    async def _extract_subject_from_text(self, text):
        # 100 lines of extraction logic
        pass

# AFTER (Target - Thin Delegation):
class AgentOrchestrator:
    def __init__(self):
        self._research_handler = ResearchHandler()
        self._media_handler = MediaHandler()
    
    async def handle_research(self, request):
        """Backward-compat wrapper; logic lives in handler"""
        return await self._research_handler.handle(request)
    
    async def _extract_subject_from_text(self, text):
        """Delegated to handler"""
        return await self._research_handler.extract_subject(text)
```

**P23 Tasks Required:**
1. [ ] Move research logic → `research_handler.py`
2. [ ] Move pronoun logic → `pronoun_rewriter.py`
3. [ ] Move media logic → `media_handler.py`
4. [ ] Move scheduling logic → `scheduling_handler.py`
5. [ ] Create thin wrapper methods with backward-compatible names
6. [ ] Verify line count < 4,000
7. [ ] Run full regression tests

**Success Criteria:**
- `agent_orchestrator.py` < 4,000 lines
- All existing tests pass
- No behavior changes
- Delegation verified via code review

---

### Blocker #2: Handoff System Limitations (SEVERITY: HIGH)

**Current State:**
```python
# core/agents/handoff_manager.py
class HandoffManager:
    MAX_DEPTH = 1  # ← CRITICAL LIMITATION
    ALLOWED_TARGETS = {
        "research", 
        "system_operator", 
        "planner", 
        "media", 
        "scheduling"
    }
```

**Why This Blocks Implementation:**

The multi-agent plan requires:
- Maya → Coder Agent → Subagent (depth 2)
- Maya → Team (parallel agents)
- Background handoffs with task tracking

**Current MAX_DEPTH=1 prevents:**
- Subagent chains
- Team coordination
- Background task delegation

**Required Fix:**

```python
# UPDATED: core/agents/handoff_manager.py

class HandoffManager:
    """Extended for multi-agent support"""
    
    # INCREASED from 1 to 3
    MAX_DEPTH = 3  # Maya → Specialist → Subagent → Micro-task
    
    # EXPANDED targets
    ALLOWED_TARGETS = {
        # Existing (backward compatible)
        "research", 
        "system_operator", 
        "planner", 
        "media", 
        "scheduling",
        
        # NEW: Subagent types
        "subagent_coder",
        "subagent_reviewer", 
        "subagent_architect",
        "subagent_researcher",
        "subagent_tester",
        
        # NEW: Team coordination
        "team_coding",
        "team_review",
        "team_research",
        
        # NEW: Project mode
        "project_manager",
        "prd_generator",
    }
    
    SIGNAL_TO_TARGET = {
        # Existing signals
        "transfer_to_research": "research",
        "transfer_to_system_operator": "system_operator",
        "transfer_to_planner": "planner",
        "transfer_to_media": "media",
        "transfer_to_scheduling": "scheduling",
        
        # NEW: Subagent signals
        "spawn_coder": "subagent_coder",
        "spawn_reviewer": "subagent_reviewer",
        "spawn_team": "team_coding",
    }
    
    def validate_request(self, request: AgentHandoffRequest):
        """Extended validation for subagent support"""
        # Existing checks...
        
        # NEW: Allow subagent delegation
        if request.target_agent.startswith("subagent_"):
            if request.delegation_depth >= self.MAX_DEPTH:
                raise HandoffValidationError("Max subagent depth exceeded")
        
        # NEW: Background task validation
        if request.execution_mode in {"background", "subagent"}:
            if not request.task_id:
                raise HandoffValidationError("task_id required for background/subagent")
```

**Migration Strategy:**
1. [ ] Extend `MAX_DEPTH` to 3
2. [ ] Add subagent targets to `ALLOWED_TARGETS`
3. [ ] Add subagent signals
4. [ ] Update validation logic
5. [ ] Test with existing agents (should work unchanged)
6. [ ] Add new tests for depth=2 and depth=3

---

### Blocker #3: No Task Persistence/Recovery (SEVERITY: HIGH)

**Current State:**
```python
# core/tasks/task_models.py
class Task(BaseModel):
    id: str
    status: TaskStatus  # PENDING, RUNNING, COMPLETED, FAILED
    # ...
    # NO persistence fields
    # NO cron scheduling
    # NO recovery capability
```

**Why This Blocks Implementation:**

The plan requires:
- `$ralph` mode: Persistent execution with recovery
- `CronCreateTool`: Scheduled recurring tasks
- Background tasks surviving restarts

**Current gap:** Tasks exist only in memory/SQLite but no recovery mechanism.

**Required Fix:**

```python
# EXTENDED: core/tasks/task_models.py

class Task(BaseModel):
    # ... existing fields ...
    
    # NEW: Persistence and scheduling
    persistent: bool = Field(default=False)
    """If True, survive application restart"""
    
    cron_expression: Optional[str] = Field(default=None)
    """Cron schedule for recurring tasks"""
    
    next_run: Optional[datetime] = Field(default=None)
    """Next scheduled execution time"""
    
    recovery_enabled: bool = Field(default=False)
    """Enable $ralph recovery mode"""
    
    checkpoint_data: Optional[Dict[str, Any]] = Field(default=None)
    """Serialized state for recovery"""
    
    parent_task_id: Optional[str] = Field(default=None)
    """For subtask tracking"""
    
    subagent_id: Optional[str] = Field(default=None)
    """If delegated to subagent"""


# NEW: core/tasks/background/persistence.py

class TaskPersistence:
    """
    Persistence layer for background tasks.
    Enables $ralph mode (recovery after restart).
    """
    
    def __init__(self, db_path: str = "~/.claude/tasks/persistent.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize persistence database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS persistent_tasks (
                task_id TEXT PRIMARY KEY,
                task_data JSON NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                next_run TIMESTAMP,
                recovery_count INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
    
    async def save_task(self, task: Task):
        """Save task to persistent storage"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO persistent_tasks 
            (task_id, task_data, status, next_run)
            VALUES (?, ?, ?, ?)
            """,
            (
                task.id,
                json.dumps(task.model_dump()),
                task.status.value,
                task.next_run.isoformat() if task.next_run else None
            )
        )
        conn.commit()
        conn.close()
    
    async def recover_tasks(self) -> List[Task]:
        """
        Recover tasks after restart.
        Core of $ralph mode.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            SELECT task_data FROM persistent_tasks 
            WHERE status IN ('PENDING', 'RUNNING', 'WAITING')
            AND (next_run IS NULL OR next_run <= datetime('now'))
            """
        )
        
        tasks = []
        for row in cursor.fetchall():
            task_data = json.loads(row[0])
            tasks.append(Task(**task_data))
        
        conn.close()
        return tasks
    
    async def update_checkpoint(self, task_id: str, checkpoint: Dict):
        """Save task checkpoint for recovery"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE persistent_tasks SET checkpoint_data = ? WHERE task_id = ?",
            (json.dumps(checkpoint), task_id)
        )
        conn.commit()
        conn.close()
```

**Database Migration:**

```sql
-- migration_001_add_task_persistence.sql

-- Add persistence columns to existing tasks table
ALTER TABLE tasks ADD COLUMN persistent BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN cron_expression VARCHAR(255);
ALTER TABLE tasks ADD COLUMN next_run TIMESTAMP;
ALTER TABLE tasks ADD COLUMN recovery_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN checkpoint_data JSON;
ALTER TABLE tasks ADD COLUMN parent_task_id VARCHAR(255);
ALTER TABLE tasks ADD COLUMN subagent_id VARCHAR(255);

-- Create index for recovery queries
CREATE INDEX idx_recoverable_tasks 
ON tasks(status, next_run) 
WHERE persistent = TRUE;
```

---

### Blocker #4: No Inter-Agent Communication Layer (SEVERITY: HIGH)

**Current State:**
- Agents do not communicate with each other
- No message bus
- No A2A protocol
- No progress streaming

**Why This Blocks Implementation:**

The plan requires:
- Subagents report progress to Maya
- Inter-agent messaging (`SendMessageTool`)
- Team coordination
- Real-time user updates

**Simplification Decision:**

**Option A: Full A2A Protocol (Complex)**
- Pros: Standard compliant, interoperable
- Cons: High complexity, 2-3 weeks implementation
- Status: ❌ Not recommended for Phase 1

**Option B: Internal Messaging (Recommended)**
- Pros: Faster to implement (3-5 days), sufficient for Maya
- Cons: Not standard compliant (can migrate later)
- Status: ✅ **RECOMMENDED for Phase 1**

**Required Fix (Option B - Simplified):**

```python
# NEW: core/messaging/bus.py

class MessageBus:
    """
    Internal message bus for inter-agent communication.
    Simpler than A2A, can migrate later.
    """
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
    
    async def subscribe(self, agent_id: str, callback: Callable):
        """Agent subscribes to messages"""
        if agent_id not in self.subscribers:
            self.subscribers[agent_id] = []
        self.subscribers[agent_id].append(callback)
    
    async def send_message(
        self, 
        from_agent: str, 
        to_agent: str, 
        message: dict
    ):
        """Send message to specific agent"""
        msg = {
            "from": from_agent,
            "to": to_agent,
            "content": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_id": str(uuid.uuid4())
        }
        
        if to_agent in self.subscribers:
            for callback in self.subscribers[to_agent]:
                await callback(msg)
        else:
            # Queue for later
            await self.message_queue.put(msg)
    
    async def broadcast(self, from_agent: str, message: dict):
        """Broadcast to all agents"""
        for agent_id in self.subscribers:
            await self.send_message(from_agent, agent_id, message)


# NEW: core/messaging/progress_stream.py

class ProgressStream:
    """
    Stream progress updates from background tasks to user.
    Uses Server-Sent Events (SSE) pattern.
    """
    
    def __init__(self):
        self.subscribers: List[asyncio.Queue] = []
    
    async def subscribe(self) -> asyncio.Queue:
        """User interface subscribes to progress"""
        queue = asyncio.Queue()
        self.subscribers.append(queue)
        return queue
    
    async def publish(self, task_id: str, update: TaskProgressUpdate):
        """Publish progress update"""
        for queue in self.subscribers:
            await queue.put({
                "task_id": task_id,
                "update": update.model_dump(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    async def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from updates"""
        if queue in self.subscribers:
            self.subscribers.remove(queue)


class TaskProgressUpdate(BaseModel):
    """Progress update from background task"""
    stage: str  # "planning", "coding", "testing", "completed"
    percent: int  # 0-100
    message: str
    artifacts: Optional[List[str]] = None
    requires_attention: bool = False
```

**Migration to A2A Later:**

```python
# Future: Can wrap MessageBus with A2A protocol
class A2AAdapter:
    """Adapt internal MessageBus to A2A protocol"""
    
    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus
    
    async def send_a2a_message(self, a2a_request: A2ARequest):
        """Convert A2A to internal format"""
        await self.bus.send_message(
            from_agent=a2a_request.from_agent,
            to_agent=a2a_request.to_agent,
            message=a2a_request.content
        )
```

---

### Blocker #5: Limited Skill System (SEVERITY: MEDIUM)

**Current State:**
```python
# core/skills/registry.py - Minimal implementation
class SkillRegistry:
    """Basic skill registration"""
    
    def __init__(self):
        self.skills = {}
    
    def register(self, name: str, skill: Callable):
        self.skills[name] = skill
```

**Why This Blocks Implementation:**

The plan requires full `SkillTool` with:
- Skill discovery
- Parameter schemas
- Execution context
- Error handling
- Result formatting

**Required Fix:**

```python
# EXTENDED: core/skills/registry.py

class Skill(BaseModel):
    """Skill definition"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON schema
    handler: Callable
    examples: List[str] = []
    category: str = "general"


class SkillRegistry:
    """Full skill registry for SkillTool"""
    
    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self.categories: Dict[str, List[str]] = {}
    
    def register(self, skill: Skill):
        """Register a skill"""
        self.skills[skill.name] = skill
        
        if skill.category not in self.categories:
            self.categories[skill.category] = []
        self.categories[skill.category].append(skill.name)
    
    async def execute(
        self, 
        skill_name: str, 
        params: Dict[str, Any],
        context: SkillContext
    ) -> SkillResult:
        """Execute a skill"""
        if skill_name not in self.skills:
            raise SkillNotFoundError(f"Skill {skill_name} not found")
        
        skill = self.skills[skill_name]
        
        # Validate parameters
        self._validate_params(skill, params)
        
        # Execute with context
        try:
            result = await skill.handler(params, context)
            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
    
    def list_skills(self, category: Optional[str] = None) -> List[Skill]:
        """List available skills"""
        if category:
            return [self.skills[name] for name in self.categories.get(category, [])]
        return list(self.skills.values())
```

---

## Part 3: Pre-Implementation Checklist

### Phase 0: Preparation (REQUIRED)

**Must complete these BEFORE starting Phase 1 of main plan:**

#### 0.1 P23 Completion (CRITICAL)
- [ ] Reduce `agent_orchestrator.py` to < 4,000 lines
- [ ] Move research logic → `research_handler.py`
- [ ] Move pronoun logic → `pronoun_rewriter.py`
- [ ] Move media logic → `media_handler.py`
- [ ] Move scheduling logic → `scheduling_handler.py`
- [ ] Create thin wrapper methods
- [ ] Verify backward compatibility
- [ ] Run full regression: `pytest tests/test_agent_orchestrator.py -v`
- [ ] Verify line count: `wc -l core/orchestrator/agent_orchestrator.py`

**Success Criteria:**
```bash
$ wc -l core/orchestrator/agent_orchestrator.py
  3800 core/orchestrator/agent_orchestrator.py  # ✅ Under 4,000
```

#### 0.2 Handoff Manager Extension (CRITICAL)
- [ ] Extend `MAX_DEPTH` from 1 to 3
- [ ] Add subagent targets to `ALLOWED_TARGETS`
- [ ] Add subagent signals to `SIGNAL_TO_TARGET`
- [ ] Update `validate_request()` for subagent support
- [ ] Update `delegate()` for depth > 1
- [ ] Test existing agents (should work unchanged)
- [ ] Add new tests for depth=2, depth=3
- [ ] Verify MAX_DEPTH guard works

**Success Criteria:**
```python
# Test passes:
async def test_subagent_chain_depth_3():
    manager = HandoffManager(registry)
    result = await manager.delegate(
        AgentHandoffRequest(
            parent_agent="maya",
            target_agent="subagent_coder",  # NEW target
            delegation_depth=2,  # Previously would fail
            max_depth=3
        )
    )
    assert result.status != "failed"
```

#### 0.3 Task Persistence Layer (CRITICAL)
- [ ] Add persistence fields to `Task` model
- [ ] Create `TaskPersistence` class
- [ ] Implement `save_task()` method
- [ ] Implement `recover_tasks()` method
- [ ] Implement `update_checkpoint()` method
- [ ] Create database migration script
- [ ] Run migration on existing database
- [ ] Test recovery after simulated restart
- [ ] Add tests for persistence

**Success Criteria:**
```python
# Test passes:
async def test_task_survives_restart():
    task = Task(persistent=True, status=TaskStatus.RUNNING)
    await persistence.save_task(task)
    
    # Simulate restart (new persistence instance)
    new_persistence = TaskPersistence()
    recovered = await new_persistence.recover_tasks()
    
    assert len(recovered) == 1
    assert recovered[0].id == task.id
```

#### 0.4 Messaging Layer (CRITICAL)
- [ ] Create `MessageBus` class
- [ ] Implement `subscribe()` method
- [ ] Implement `send_message()` method
- [ ] Implement `broadcast()` method
- [ ] Create `ProgressStream` class
- [ ] Implement progress streaming
- [ ] Test agent-to-agent messaging
- [ ] Test progress streaming

**Success Criteria:**
```python
# Test passes:
async def test_inter_agent_messaging():
    bus = MessageBus()
    
    received = []
    await bus.subscribe("agent_b", lambda msg: received.append(msg))
    
    await bus.send_message("agent_a", "agent_b", {"content": "hello"})
    
    assert len(received) == 1
    assert received[0]["content"] == {"content": "hello"}
```

#### 0.5 Skill System Enhancement (MEDIUM)
- [ ] Create `Skill` model with schema
- [ ] Extend `SkillRegistry` with full capabilities
- [ ] Implement `execute()` with validation
- [ ] Implement `list_skills()` with filtering
- [ ] Create example skills (3-5 built-in)
- [ ] Test skill execution
- [ ] Test parameter validation

#### 0.6 Configuration Updates (MEDIUM)
- [ ] Update `settings.py` with new dependencies
- [ ] Add LiveKit configuration (placeholder)
- [ ] Add feature flag configuration
- [ ] Create `~/.claude/` directory structure
- [ ] Verify all imports work

#### 0.7 Dependency Installation (MEDIUM)
- [ ] Add to `pyproject.toml`:
  ```toml
  livekit = "^0.18"
  livekit-agents = "^0.12"
  APScheduler = "^3.10"
  gitpython = "^3.1"
  pyzmq = "^25.0"
  ```
- [ ] Run `poetry install` or `pip install`
- [ ] Verify imports in Python
- [ ] Update requirements.txt if exists

---

## Part 4: Testing Infrastructure

### 4.1 New Test Files Required

Before implementation, create test infrastructure:

```
tests/
├── agents/
│   └── subagent/                    # NEW
│       ├── __init__.py
│       ├── test_subagent_lifecycle.py
│       ├── test_worktree_isolation.py
│       └── test_inter_agent_messaging.py
├── tasks/
│   └── background/                   # NEW
│       ├── __init__.py
│       ├── test_task_persistence.py
│       ├── test_recovery_after_restart.py
│       ├── test_cron_scheduling.py
│       └── test_background_executor.py
├── messaging/                        # NEW
│   ├── __init__.py
│   ├── test_message_bus.py
│   └── test_progress_stream.py
└── skills/                           # NEW
    ├── __init__.py
    ├── test_skill_registry.py
    └── test_skill_execution.py
```

### 4.2 Test Fixtures Required

```python
# tests/conftest.py additions

@pytest.fixture
async def message_bus():
    """Message bus for testing"""
    bus = MessageBus()
    yield bus
    # Cleanup

@pytest.fixture
async def task_persistence(tmp_path):
    """Task persistence with temp database"""
    db_path = tmp_path / "test_tasks.db"
    persistence = TaskPersistence(db_path=str(db_path))
    yield persistence
    # Cleanup

@pytest.fixture
async def mock_subagent():
    """Mock subagent for testing"""
    return MockSubAgent(name="test_agent")
```

---

## Part 5: Migration Strategy

### 5.1 Backward Compatibility Plan

**Critical:** All changes must maintain existing behavior

```python
# handoff_manager.py - Bridge pattern
class HandoffManager:
    def __init__(self):
        self.use_subagents = False  # Feature flag
    
    async def delegate(self, request):
        if self.use_subagents and request.target_agent.startswith("subagent_"):
            return await self._delegate_to_subagent(request)
        else:
            return await self._legacy_delegate(request)  # Keep working
```

### 5.2 Database Migration

```python
# migrations/001_add_task_persistence.py

async def migrate():
    """Add persistence columns to tasks table"""
    conn = sqlite3.connect(settings.task_db_path)
    
    # Check if columns exist
    cursor = conn.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "persistent" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN persistent BOOLEAN DEFAULT FALSE")
    
    if "cron_expression" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN cron_expression VARCHAR(255)")
    
    # ... more columns
    
    conn.commit()
    conn.close()
```

### 5.3 Feature Flags

```python
# config/settings.py

class FeatureFlags:
    """Gradual rollout of new features"""
    
    SUBAGENT_SYSTEM = os.getenv("MAYA_SUBAGENTS", "false").lower() == "true"
    BACKGROUND_TASKS = os.getenv("MAYA_BACKGROUND", "false").lower() == "true"
    A2A_PROTOCOL = os.getenv("MAYA_A2A", "false").lower() == "true"
    LIVEKIT_MULTIMODAL = os.getenv("MAYA_LIVEKIT", "false").lower() == "true"
```

---

## Part 6: Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| P23 takes longer than expected | High | High | Start immediately; parallelize with other prep |
| Circular dependencies in messaging | Medium | High | Use dependency injection; test early |
| Task persistence corruption | Low | Critical | Backup before migration; transactional writes |
| Memory leaks with many agents | Medium | High | Limit concurrent agents; add monitoring |
| Test coverage gaps | Medium | Medium | Require tests for all new code |
| Breaking existing functionality | Medium | High | Full regression before each phase |

---

## Part 7: Timeline

### Pre-Implementation Timeline

| Day | Activity | Owner |
|-----|----------|-------|
| 1-2 | P23: Orchestrator reduction | Dev |
| 2-3 | HandoffManager extension | Dev |
| 3-4 | Task persistence layer | Dev |
| 4-5 | Messaging layer | Dev |
| 5-6 | Skill system enhancement | Dev |
| 6-7 | Testing & validation | QA |
| 7 | Final review & go/no-go | Lead |

**Total: 7 days preparation before Phase 1 can begin**

---

## Part 8: Go/No-Go Criteria

### Ready to Start Phase 1 When:

**Technical:**
- [ ] P23 complete (orchestrator < 4,000 lines)
- [ ] HandoffManager extended (MAX_DEPTH=3)
- [ ] Task persistence implemented
- [ ] Messaging layer working
- [ ] All existing tests pass
- [ ] New test infrastructure ready

**Documentation:**
- [ ] Database migration scripts tested
- [ ] Rollback procedures documented
- [ ] Feature flags configured

**Review:**
- [ ] Code review of all preparation work
- [ ] Architecture review approved
- [ ] Performance baseline recorded

---

## Summary

**Critical Path:**

1. **Complete P23** (orchestrator reduction) - BLOCKING
2. **Extend HandoffManager** - BLOCKING
3. **Add task persistence** - BLOCKING
4. **Build messaging layer** - BLOCKING
5. **Verify all tests pass** - BLOCKING
6. **Then** start Phase 1 of main plan

**Estimated Preparation:** 1-2 weeks

**Risk if skipped:**
- Architecture collapse
- Unmaintainable codebase
- Failed background tasks
- Broken backward compatibility

**Recommendation:** 
✅ **DO NOT start Phase 1 until all blockers resolved**

---

## Appendix: Quick Reference

### Critical Files to Modify

```
agent_orchestrator.py     # P23 reduction
handoff_manager.py        # MAX_DEPTH extension
task_models.py            # Persistence fields
NEW: messaging/bus.py     # Inter-agent communication
NEW: messaging/progress_stream.py  # Progress updates
NEW: tasks/background/persistence.py  # $ralph mode
```

### Critical Tests to Pass

```bash
# Existing tests must still pass
pytest tests/test_agent_orchestrator.py -v
pytest tests/test_handoff_manager.py -v
pytest tests/tasks/ -v

# New tests must be written
pytest tests/agents/subagent/ -v
pytest tests/tasks/background/ -v
pytest tests/messaging/ -v
```

### Success Metrics

- Orchestrator lines: < 4,000 ✅
- Handoff depth: MAX_DEPTH=3 ✅
- Task recovery: 100% after restart ✅
- Message latency: < 100ms ✅
- All existing tests: PASSING ✅

---

*Document Location: `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/NEW_futhur plan/Maya-Prerequisites-Pre-Implementation-Plan.md`*

*Version: 1.0*

*Last Updated: April 5, 2025*
