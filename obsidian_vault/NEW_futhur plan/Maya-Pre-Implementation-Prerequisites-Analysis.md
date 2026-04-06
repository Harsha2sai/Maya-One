# Maya Pre-Implementation Prerequisites Analysis

**Date:** April 5, 2025  
**Status:** Critical Assessment - Must Read Before Implementation  
**Version:** 1.0  
**Purpose:** Identify blockers and prerequisites before implementing the Maya Multi-Agent Architecture Plan

---

## Executive Summary

**⚠️ WARNING:** The comprehensive Maya Multi-Agent Architecture Plan (v2.1) **CANNOT** be implemented until the following critical prerequisites are resolved. Attempting implementation without addressing these blockers will result in:

- ❌ Circular dependencies
- ❌ Orchestrator exceeding size limits (currently 3,776 lines, target <4K)
- ❌ No background task persistence
- ❌ No inter-agent communication
- ❌ Failed regression tests

**Estimated Pre-Implementation Work:** 1-2 weeks  
**Estimated Risk Reduction:** 70%

---

## Part 1: Current Architecture Analysis

### 1.1 File Size & Complexity Assessment

| File | Lines | Status | Max Safe | Risk Level |
|------|-------|--------|----------|------------|
| `core/orchestrator/agent_orchestrator.py` | **3,776** | 🔴 CRITICAL | 4,000 | **High** |
| `core/orchestrator/chat_mixin.py` | 911 | 🟡 Warning | 1,000 | Medium |
| `core/orchestrator/research_handler.py` | 788 | ✅ OK | 1,000 | Low |
| `core/tasks/task_worker.py` | ~2,400 | 🟡 Warning | 3,000 | Medium |
| `core/memory/hybrid_memory_manager.py` | ~800 | ✅ OK | 1,000 | Low |
| `core/agents/handoff_manager.py` | **133** | 🟡 Limited | N/A | Medium |
| **Total Core Files** | **~200+** | - | - | - |

### 1.2 Module Dependencies Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT DEPENDENCIES                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐                                         │
│  │   Main Entry     │                                         │
│  │   (agent.py)     │                                         │
│  └────────┬─────────┘                                         │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐     ┌──────────────────┐                │
│  │ AgentOrchestrator│◄────┤  HandoffManager  │                │
│  │   (3,776 lines)  │     │   (MAX_DEPTH=1)  │                │
│  └────────┬─────────┘     └──────────────────┘                │
│           │                                                     │
│     ┌─────┴─────┬─────────────┬──────────────┐               │
│     ▼           ▼             ▼              ▼                 │
│ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐         │
│ │ Router │ │ Research │ │  Media   │ │ Scheduling  │         │
│ │(329)   │ │ Handler  │ │ Handler  │ │  Handler    │         │
│ └────────┘ └──────────┘ └──────────┘ └─────────────┘         │
│                                                                 │
│  ┌──────────────────┐                                         │
│  │   Task System    │                                         │
│  │ ┌─────────────┐ │     ┌──────────────────┐               │
│  │ │ Task Models │ │◄────┤   Task Worker    │               │
│  │ │ Task Store  │ │     │  (No Recovery)   │               │
│  │ └─────────────┘ │     └──────────────────┘               │
│  └──────────────────┘                                         │
│                                                                 │
│  ┌──────────────────┐                                         │
│  │   Agent Base     │                                         │
│  │  SpecializedAgent│◄──── NO SUBAGENT SUPPORT               │
│  │   MAX_DEPTH=1    │                                         │
│  └──────────────────┘                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Existing Agent Types

| Agent | File | Can Spawn Subagents | Can Communicate | Worktree Isolation |
|-------|------|---------------------|-----------------|-------------------|
| ResearchAgent | `research_agent.py` | ❌ No | ❌ No | ❌ No |
| PlannerAgent | `planner_agent.py` | ❌ No | ❌ No | ❌ No |
| SystemOperator | `system_operator_agent.py` | ❌ No | ❌ No | ❌ No |
| MediaAgent | `media_agent_handler.py` | ❌ No | ❌ No | ❌ No |
| SchedulingAgent | `scheduling_agent_handler.py` | ❌ No | ❌ No | ❌ No |

**Total Subagent Support:** 0/5 agents  
**Total Inter-Agent Communication:** None  
**Total Worktree Isolation:** None

---

## Part 2: Critical Blockers (MUST FIX)

### 2.1 Blocker #1: Orchestrator Monolith (CRITICAL)

**Problem:**
```python
# File: core/orchestrator/agent_orchestrator.py
# Lines: 3,776 (94% of 4,000 line limit)
# Size: ~149 KB

class AgentOrchestrator:
    """Currently handles:"""
    - Routing decisions (inline)
    - Research delegation (inline, not in handler)
    - Pronoun rewriting (inline, not fully delegated)
    - Media handling (partially in handler)
    - Scheduling (partially in handler)
    - Memory management (inline)
    - Chat responses (via mixin)
    - Tool execution (inline)
    - Context building (inline)
    - Error handling (inline)
```

**Why This Blocks Implementation:**
1. Adding subagent logic will exceed 4,000 lines
2. Cannot add A2A protocol handling (too complex)
3. Cannot add Buddy integration (no room)
4. Testing becomes impossible (file too large)

**Required Fix (P23 Plan):**
```python
# BEFORE (3,776 lines):
class AgentOrchestrator:
    async def _extract_subject_from_text(self, text): ...  # 50 lines
    async def _extract_summary_sentence(self, text): ...   # 30 lines
    async def _resolve_research_subject(self, ctx): ...    # 80 lines
    async def rewrite_research_query(self, query): ...     # 100 lines
    # ... 600+ lines of research/pronoun logic

# AFTER (target: <2,500 lines):
class AgentOrchestrator:
    # Thin wrappers only:
    async def _extract_subject_from_text(self, text):
        return await self._research_handler.extract_subject_from_text(text)
    
    # All logic moved to handlers
```

**Acceptance Criteria:**
- [ ] Line count < 4,000
- [ ] All research logic in `research_handler.py`
- [ ] All pronoun logic in `pronoun_rewriter.py`
- [ ] No inline duplication
- [ ] All tests passing

**Estimated Effort:** 2-3 days  
**Risk if Skipped:** Implementation will fail, circular dependencies

---

### 2.2 Blocker #2: Handoff System Limitations (CRITICAL)

**Current State:**
```python
# File: core/agents/handoff_manager.py
# Lines: 133 (too limited)

class HandoffManager:
    MAX_DEPTH = 1  # ← BLOCKS subagent chains
    
    ALLOWED_TARGETS = {
        "research",
        "system_operator",
        "planner",
        "media",
        "scheduling"
    }  # ← NO subagent targets
    
    SIGNAL_TO_TARGET = {
        "transfer_to_research": "research",
        "transfer_to_system_operator": "system_operator",
        # ... NO subagent signals
    }
```

**Why This Blocks Implementation:**
- Subagents require depth > 1 (Maya → Coder → Reviewer)
- No targets for subagent types (coder, reviewer, architect)
- No background execution tracking
- No inter-agent messaging support

**Required Fix:**
```python
# NEW: core/agents/handoff_manager.py

class HandoffManager:
    MAX_DEPTH = 3  # Maya → Specialist → Subagent → Micro-pet
    
    ALLOWED_TARGETS = {
        # Existing:
        "research", "system_operator", "planner", "media", "scheduling",
        # NEW - Subagents:
        "subagent_coder",
        "subagent_reviewer",
        "subagent_architect",
        "subagent_tester",
        "subagent_researcher",
        # NEW - Teams:
        "team_coding",
        "team_review",
        "team_project",
    }
    
    # NEW: Support for background execution
    async def delegate_background(
        self, 
        request: AgentHandoffRequest,
        callback: Optional[Callable] = None
    ) -> BackgroundTask:
        """Delegate to agent that runs in background"""
        ...
```

**Acceptance Criteria:**
- [ ] MAX_DEPTH increased to 3
- [ ] Subagent targets added
- [ ] Background delegation supported
- [ ] Callback system for progress
- [ ] All existing tests still pass

**Estimated Effort:** 1 day  
**Risk if Skipped:** Cannot spawn subagents, cannot do team mode

---

### 2.3 Blocker #3: Task System - No Background Persistence (CRITICAL)

**Current State:**
```python
# File: core/tasks/task_models.py

class Task(BaseModel):
    id: str
    user_id: str
    title: str
    status: TaskStatus  # PENDING, RUNNING, COMPLETED, etc.
    steps: List[TaskStep]
    # ❌ NO: persistent flag
    # ❌ NO: cron scheduling
    # ❌ NO: recovery after restart
    # ❌ NO: background execution tracking

# File: core/tasks/task_worker.py
class TaskWorker:
    async def execute(self, task):
        # Runs synchronously
        # ❌ No background mode
        # ❌ No persistence across sessions
        # ❌ No recovery
```

**Why This Blocks Implementation:**
- `$ralph` mode requires tasks surviving restart
- `CronCreateTool` requires scheduled execution
- Cannot track background task progress
- No TaskOutput retrieval

**Required Fix:**
```python
# EXTEND: core/tasks/task_models.py

class Task(BaseModel):
    # Existing fields...
    
    # NEW: Background execution support
    persistent: bool = Field(default=False)
    """If True, task survives agent restart"""
    
    cron_expression: Optional[str] = Field(default=None)
    """Cron schedule (e.g., '0 9 * * *') for CronCreateTool"""
    
    recovery_enabled: bool = Field(default=False)
    """$ralph mode: Auto-recover and continue"""
    
    background_task_id: Optional[str] = Field(default=None)
    """Reference to background task worker"""
    
    last_checkpoint: Optional[datetime] = Field(default=None)
    """For recovery: last known good state"""
    
    checkpoint_data: Optional[Dict] = Field(default=None)
    """Serializable state for recovery"""

# NEW: core/tasks/background_task.py

class BackgroundTaskManager:
    """Manages tasks that run in background with persistence"""
    
    async def schedule_task(
        self,
        task: Task,
        trigger: Union[CronTrigger, ImmediateTrigger],
        callback: Optional[Callable] = None
    ) -> ScheduledTask:
        """Schedule task for background execution"""
        ...
    
    async def persist_state(self, task_id: str, state: Dict):
        """Save task state to survive restarts"""
        ...
    
    async def recover_tasks(self) -> List[Task]:
        """Recover tasks after restart ($ralph mode)"""
        ...
```

**Database Migration Required:**
```sql
-- migrations/add_background_task_support.sql
ALTER TABLE tasks ADD COLUMN persistent BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN cron_expression VARCHAR(255);
ALTER TABLE tasks ADD COLUMN recovery_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN background_task_id VARCHAR(255);
ALTER TABLE tasks ADD COLUMN last_checkpoint TIMESTAMP;
ALTER TABLE tasks ADD COLUMN checkpoint_data JSON;

-- Index for recovery queries
CREATE INDEX idx_tasks_recovery ON tasks(recovery_enabled, status) 
WHERE recovery_enabled = TRUE;
```

**Acceptance Criteria:**
- [ ] Task model extended with background fields
- [ ] BackgroundTaskManager implemented
- [ ] Database migration applied
- [ ] Recovery test: start task, restart agent, task continues
- [ ] Cron scheduling test: task runs on schedule

**Estimated Effort:** 2-3 days  
**Risk if Skipped:** No background tasks, no $ralph mode, no CronCreateTool

---

### 2.4 Blocker #4: No IPC/Communication Layer (CRITICAL)

**Current State:**
```
Maya ──► ResearchAgent (synchronous return)
           ▲
           │
           ❌ No way to send messages back
           ❌ No way to check progress
           ❌ No way to stream updates
```

**Why This Blocks Implementation:**
- Subagents cannot communicate with each other
- Cannot stream progress to user
- Cannot do `$team` mode (parallel agents need to communicate)
- Cannot do Project Mode (voice updates need streaming)

**Two Solutions:**

**Option A: Full A2A Protocol (Google Standard)**
```python
# Implementation: core/a2a/

class A2AAgentServer:
    """Each subagent exposes HTTP + SSE endpoint"""
    async def get_agent_card(self): ...
    async def send_task(self, request): ...
    async def subscribe_to_updates(self, task_id): ...

class A2AClient:
    """Maya communicates with subagents via HTTP"""
    async def delegate_task(self, agent_url, task): ...
    async def send_message(self, agent_url, message): ...
```
- ✅ Standard compliant
- ✅ Interoperable
- ❌ Complex (needs FastAPI, SSE)
- ❌ 3-4 days implementation

**Option B: Internal Message Bus (Recommended)**
```python
# Implementation: core/messaging/

class MessageBus:
    """Internal ZeroMQ-based messaging"""
    async def publish(self, channel, message): ...
    async def subscribe(self, channel, callback): ...

class ProgressStreamer:
    """SSE to user terminal"""
    async def stream_progress(self, task_id, update): ...
```
- ✅ Faster to implement (1-2 days)
- ✅ Sufficient for Maya's needs
- ✅ Can migrate to A2A later
- ❌ Not standard compliant (for now)

**Recommendation:** Start with Option B, migrate to A2A in Phase 7.

**Acceptance Criteria:**
- [ ] Message bus implemented
- [ ] Subagents can send messages to parent
- [ ] Progress streaming works
- [ ] Parent can broadcast to team
- [ ] Latency <100ms

**Estimated Effort:** 1-2 days (Option B)  
**Risk if Skipped:** No subagent communication, no progress updates

---

## Part 3: Additional Prerequisites

### 3.1 Configuration Updates Required

**Current `config/settings.py` missing:**
```python
# MUST ADD:

# LiveKit credentials (for Phase 4)
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Feature flags
FEATURE_FLAGS = {
    "PROACTIVE": False,
    "KAIROS": False,
    "VOICE_MODE": False,
    "SUBAGENTS": False,  # Enable after Phase 1
}

# Plugin system
PLUGIN_DIRECTORIES = [
    "~/.claude/plugins/",
    "./plugins/",
]

# Worktree base path
WORKTREE_BASE_PATH = "~/.claude/worktrees/"

# Background task settings
BACKGROUND_TASK_DB = "~/.claude/background_tasks.db"
TASK_RECOVERY_INTERVAL = 60  # seconds
```

**Estimated Effort:** 2 hours

---

### 3.2 Dependencies to Add

**Current `pyproject.toml` needs:**
```toml
[tool.poetry.dependencies]
# NEW for subagents/worktrees:
gitpython = "^3.1"
pyzmq = "^25.0"  # For IPC

# NEW for scheduling:
APScheduler = "^3.10"

# NEW for LiveKit (Phase 4):
livekit = "^0.18"
livekit-agents = "^0.12"

# NEW for terminal UI:
rich = "^13.0"
blessed = "^1.20"

# NEW for notebooks:
nbformat = "^5.9"

# NEW for validation:
jsonschema = "^4.19"

# NEW for LSP:
python-lsp-jsonrpc = "^1.1"
```

**Estimated Effort:** 1 hour (update + install)

---

### 3.3 Additional Agent Types Prerequisites

**For 6 New Agent Types (Security, Documentation, Monitoring, Learning, Integration, Data):**

**New Dependencies:**
```toml
# For SecurityAgent:
bandit = "^1.7"                    # Python security linter
safety = "^3.0"                    # Dependency vulnerability checker
detect-secrets = "^1.5"            # Secret scanning
semgrep = "^1.0"                   # Static analysis

# For DocumentationAgent:
ast-decompiler = "^0.7"            # AST parsing
markdown-builder = "^0.2"          # README generation
plantuml = "^0.3"                # Diagram generation

# For MonitoringAgent:
psutil = "^5.9"                    # System metrics
watchdog = "^3.0"                  # File watching
httpx = "^0.25"                    # API health checks

# For LearningAgent:
scikit-learn = "^1.3"              # Pattern recognition
pandas = "^2.0"                    # Data analysis

# For IntegrationAgent:
github3-py = "^4.0"                # GitHub API
slack-sdk = "^3.0"                 # Slack integration
google-api-python-client = "^2.0"  # Google APIs

# For DataAgent:
pandas = "^2.0"                    # Data manipulation
numpy = "^1.24"                    # Numerical computing
matplotlib = "^3.7"                # Visualization
openpyxl = "^3.1"                  # Excel support
```

**New Configuration:**
```python
# config/settings.py additions

# SecurityAgent settings
SECURITY_SCAN_ENABLED = True
SECURITY_SCAN_ON_SAVE = True
SECURITY_FAIL_ON_HIGH_SEVERITY = True

# DocumentationAgent settings
AUTO_GENERATE_README = True
AUTO_UPDATE_CHANGELOG = True
DOCS_GENERATION_STYLE = "google"  # google | numpy

# MonitoringAgent settings
SYSTEM_METRICS_INTERVAL = 60  # seconds
FILE_WATCH_PATTERNS = ["*.py", "*.md", "config.yaml"]
ALERT_THRESHOLDS = {
    "cpu_percent": 80,
    "memory_percent": 90,
    "disk_percent": 95,
}

# LearningAgent settings
LEARNING_ENABLED = True
PATTERN_THRESHOLD = 0.8  # Confidence to learn
SHORTCUT_SUGGESTION_ENABLED = True

# IntegrationAgent settings
INTEGRATIONS_ENABLED = ["github", "slack", "notion"]
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# DataAgent settings
DEFAULT_DATA_FORMAT = "pandas"
MAX_DATASET_SIZE_MB = 100
```

**Estimated Effort:** 2 hours (additional deps + config)

---

### 3.4 Test Infrastructure

**Must create before implementation:**

```python
# tests/agents/subagent/__init__.py
# tests/agents/subagent/conftest.py

# tests/agents/subagent/test_lifecycle.py
async def test_subagent_spawn_and_complete():
    """Test basic subagent lifecycle"""
    ...

async def test_subagent_background_execution():
    """Test wait=False mode"""
    ...

async def test_worktree_isolation():
    """Test git worktree creates isolated context"""
    ...

# tests/tasks/background/__init__.py

# tests/tasks/background/test_persistence.py
async def test_task_survives_restart():
    """Critical: task continues after agent restart"""
    ...

async def test_cron_scheduling():
    """Test CronCreateTool"""
    ...

# tests/messaging/__init__.py

# tests/messaging/test_inter_agent.py
async def test_agents_can_communicate():
    """Test SendMessage between agents"""
    ...

async def test_progress_streaming():
    """Test SSE progress updates"""
    ...
```

### 3.4 New Agent Types Prerequisites

**Phase 1.5 Agent Extensions Require:**

| Agent | Prerequisites | Dependencies |
|-------|--------------|--------------|
| **SecurityAgent** | SubAgentManager, WorktreeManager | bandit, safety, semgrep, detect-secrets |
| **DocumentationAgent** | SubAgentManager | Sphinx, ast-docstring, plantuml |
| **MonitoringAgent** | SubAgentManager, MessageBus | psutil, watchdog, asyncpg (metrics db) |
| **LearningAgent** | SubAgentManager, Memory system | scikit-learn (pattern detection), redis (caching) |
| **IntegrationAgent** | SubAgentManager, A2A/HTTP | httpx, websockets, pydantic-oauth |
| **DataAgent** | SubAgentManager | pandas, sqlalchemy, matplotlib, pyarrow |

**Additional Dependencies:**
```toml
# Security tools
bandit = "^1.7"
safety = "^3.0"
semgrep = "^1.70"
detect-secrets = "^1.4"

# Documentation
sphinx = "^7.0"
ast-docstring = "^0.3"
plantuml = "^0.3"

# Monitoring
psutil = "^5.9"
watchdog = "^3.0"
asyncpg = "^0.29"

# Learning
scikit-learn = "^1.4"
redis = "^5.0"

# Data
pandas = "^2.0"
pyarrow = "^15.0"
matplotlib = "^3.8"
seaborn = "^0.13"
```

**Additional Configuration:**
```python
# Security agent settings
SECURITY_SCAN_DEPTH = "standard"  # or "deep"
SECURITY_FAIL_ON_HIGH = True
SECURITY_AUTO_BLOCK = True

# Documentation settings
DOC_STYLE = "google"  # or "numpy", "sphinx"
DOC_AUTO_COMMIT = True
DOC_BRANCH = "docs/auto-update"

# Monitoring settings
METRICS_RETENTION_DAYS = 30
ALERT_CHANNELS = ["console", "slack"]  # webhook URLs
WATCH_IGNORE_PATTERNS = ["*.tmp", "*.log"]

# Learning settings
LEARNING_ENABLED = True
PRIVACY_LEVEL = "local_only"  # or "cloud_anonymized"
PATTERN_MIN_CONFIDENCE = 0.7
```

**Estimated Effort:** 1 day (additional deps + config)

---

### 3.5 Enhanced Buddy Prerequisites

**Buddy Enhancement Requires:**

```python
# Memory system for Buddy learning
BUDDY_MEMORY_DB = "~/.claude/buddy_memory.db"
BUDDY_LEARNING_ENABLED = True

# Agent registry for routing
AGENT_REGISTRY_CACHE_TTL = 300  # seconds

# Trust scoring
TRUST_DECAY_RATE = 0.95  # per week
TRUST_BOOST_ON_SUCCESS = 0.05
TRUST_PENALTY_ON_FAILURE = 0.10

# Suggestion system
SUGGESTION_COOLDOWN = 3600  # seconds between same suggestion
MIN_CONFIDENCE_FOR_SUGGESTION = 0.6
```

**Estimated Effort:** 2 hours

---

## Part 4: Migration Strategy

### 4.1 Backward Compatibility

**All changes must maintain existing behavior:**

```python
# Pattern: Bridge/Facade

class HandoffManager:
    def __init__(self):
        self.use_subagents = False  # Toggle
    
    async def delegate(self, request):
        if self.use_subagents and self._can_use_subagents(request):
            return await self._new_subagent_path(request)
        else:
            # Legacy path - MUST keep working
            return await self._legacy_path(request)
```

**Feature Flags:**
```python
# Use feature flags to gradually enable:

if feature_flags.is_enabled("SUBAGENTS"):
    # Use new subagent system
else:
    # Use existing handoff
```

### 4.2 Database Migration Path

**Step-by-step:**
1. Create migration script (add columns)
2. Run migration on dev database
3. Test with existing data
4. Deploy to production
5. Verify existing tasks still work

**Rollback Plan:**
```sql
-- If needed, can rollback:
ALTER TABLE tasks DROP COLUMN persistent;
ALTER TABLE tasks DROP COLUMN cron_expression;
-- etc.
```

---

## Part 5: Risk Assessment Matrix

| Blocker | Probability | Impact | Mitigation | Status |
|---------|-------------|--------|------------|--------|
| Orchestrator bloat | 95% | 🔴 Critical | Complete P23 first | ⏳ Pending |
| Handoff depth limit | 100% | 🔴 Critical | Extend HandoffManager | ⏳ Pending |
| No task persistence | 100% | 🔴 Critical | Add BackgroundTaskManager | ⏳ Pending |
| No IPC layer | 100% | 🔴 Critical | Build MessageBus | ⏳ Pending |
| Circular dependencies | 60% | 🟡 High | Dependency injection | ⏳ Pending |
| Database migration failure | 20% | 🟡 High | Backup + rollback plan | ⏳ Pending |
| Test coverage gaps | 70% | 🟡 High | Write tests first | ⏳ Pending |
| Performance regression | 40% | 🟡 High | Benchmark at each phase | ⏳ Pending |
| New agent dependencies | 80% | 🟡 High | Install security/data libs first | ⏳ Pending |
| Agent registry bloat | 60% | 🟡 High | Design modular registry | ⏳ Pending |
| **New Agent Complexity** | **70%** | 🟡 **High** | **Staged rollout, Security first** | ⏳ **Pending** |
| **Additional Dependencies** | **50%** | 🟡 **High** | **Test each dep before commit** | ⏳ **Pending** |
| **Enhanced Buddy Scope** | **60%** | 🟡 **High** | **Extend basic Buddy, don't rewrite** | ⏳ **Pending** |

**New Agent Risks (Security, Documentation, Monitoring, Learning, Integration, Data):**

| Risk | Description | Mitigation |
|------|-------------|------------|
| Dependency conflicts | New security tools may conflict with existing packages | Pin versions, use virtualenvs |
| Security tool false positives | Bandit/secrets may flag legitimate code | Tune thresholds, user overrides |
| Documentation overhead | Auto-generated docs may be low quality | Human review gates |
| Monitoring noise | Too many alerts desensitize users | Smart alerting, ML-based threshold |
| Learning privacy | User patterns contain sensitive info | Local-only, no cloud, encrypt |
| Integration security | OAuth tokens need protection | Secure storage, rotation |
| DataAgent resource usage | Large datasets can OOM | Size limits, streaming |

---

## Part 6: Additional Agent Types Prerequisites

### 6.1 SecurityAgent Prerequisites 🔴 HIGH

**Critical for safe code execution.**

**Required Tools:**
```bash
pip install bandit safety detect-secrets semgrep
```

**Configuration Needed:**
```yaml
# .bandit.yaml
skips: ['B101']  # Skip assert checks in test files
severity: HIGH
confidence: MEDIUM
```

**Integration Points:**
- Must run BEFORE `bypassPermissions` mode
- Can block dangerous operations
- Reports to main orchestrator

**Estimated Additional Time:** 1 day

---

### 6.2 DocumentationAgent Prerequisites 🟡 MEDIUM

**Auto-documentation capabilities.**

**Required Tools:**
```bash
pip install ast-decompiler markdown-builder plantuml
```

**Configuration Needed:**
```python
DOCS_STYLE = "google"  # or "numpy"
AUTO_README = True
AUTO_CHANGELOG = True
```

**Estimated Additional Time:** 0.5 days

---

### 6.3 MonitoringAgent Prerequisites 🟡 MEDIUM

**System and file monitoring.**

**Required Tools:**
```bash
pip install psutil watchdog
```

**Configuration Needed:**
```python
MONITORING_ENABLED = True
METRICS_INTERVAL = 60  # seconds
FILE_WATCH_PATTERNS = ["*.py", "*.md"]
ALERT_THRESHOLDS = {
    "cpu": 80,
    "memory": 90,
    "disk": 95,
}
```

**Estimated Additional Time:** 0.5 days

---

### 6.4 LearningAgent Prerequisites 🟡 MEDIUM

**Pattern recognition and personalization.**

**Required Tools:**
```bash
pip install scikit-learn pandas
```

**Configuration Needed:**
```python
LEARNING_ENABLED = True
PATTERN_THRESHOLD = 0.8
PRIVACY_MODE = "local_only"  # Never send to cloud
```

**Privacy Considerations:**
- All patterns stored locally
- No cloud analytics
- User can delete learned data
- Encrypted at rest

**Estimated Additional Time:** 1 day

---

### 6.5 IntegrationAgent Prerequisites 🟢 LOW

**Third-party service integrations.**

**Required Tools:**
```bash
pip install github3-py slack-sdk google-api-python-client
```

**Configuration Needed:**
```python
INTEGRATIONS = {
    "github": {"enabled": True, "token": os.getenv("GITHUB_TOKEN")},
    "slack": {"enabled": False, "token": None},
    "notion": {"enabled": False, "token": None},
}
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
```

**Security Considerations:**
- Tokens in environment variables
- Encrypt stored credentials
- Regular token rotation
- OAuth refresh handling

**Estimated Additional Time:** 1 day

---

### 6.6 DataAgent Prerequisites 🟢 LOW

**Data processing and analysis.**

**Required Tools:**
```bash
pip install pandas numpy matplotlib openpyxl
```

**Configuration Needed:**
```python
MAX_DATASET_SIZE_MB = 100
DEFAULT_FORMAT = "pandas"
VISUALIZATION_BACKEND = "matplotlib"
```

**Resource Limits:**
- Max dataset size: 100MB
- Timeout: 60 seconds
- Memory limit: 2GB

**Estimated Additional Time:** 0.5 days

---

### 6.7 Enhanced Buddy Prerequisites 🟡 MEDIUM

**Buddy as system integration layer.**

**Dependencies:**
- Phase 1: Basic Buddy (Tamagotchi)
- Phase 1.5: Enhanced Buddy features

**New Capabilities:**
- Agent selection logic
- Task routing intelligence
- User preference memory
- System state awareness

**Extension Strategy:**
```python
# Instead of rewriting, extend existing:

class EnhancedBuddy(BuddySystem):
    """Extend basic Buddy with system integration"""
    
    def __init__(self):
        super().__init__()  # Keep Tamagotchi features
        self.agent_selector = AgentSelector()
        self.task_router = TaskRouter()
        self.memory = BuddyMemory()
```

**Estimated Additional Time:** 1 day

---

## Part 7: Go/No-Go Checklist

### Phase 0: Pre-Implementation (MUST COMPLETE)

**P23 Completion:**
- [ ] `agent_orchestrator.py` < 4,000 lines
- [ ] Research logic in `research_handler.py`
- [ ] Pronoun logic in `pronoun_rewriter.py`
- [ ] All P23 tests passing
- [ ] Baseline performance established

**Handoff System:**
- [ ] `MAX_DEPTH` increased to 3
- [ ] Subagent targets added
- [ ] Background delegation supported
- [ ] Callback system implemented

**Task System:**
- [ ] Task model extended (persistent, cron, recovery)
- [ ] Database migration applied
- [ ] BackgroundTaskManager implemented
- [ ] Recovery test passing

**Communication:**
- [ ] MessageBus implemented (or A2A)
- [ ] Progress streaming working
- [ ] Inter-agent messaging tested
- [ ] Latency <100ms

**Configuration:**
- [ ] Settings updated (LiveKit, feature flags, plugins)
- [ ] Dependencies installed
- [ ] Environment variables documented

**Testing:**
- [ ] Subagent lifecycle tests
- [ ] Background persistence tests
- [ ] Inter-agent communication tests
- [ ] All existing tests still passing

**Documentation:**
- [ ] Migration guide written
- [ ] Rollback procedure documented
- [ ] New architecture diagrams created

**Phase 1.5 Extensions (Security, Documentation, Monitoring, Learning, Integration, Data Agents):**
- [ ] Security scanning dependencies installed (bandit, safety, semgrep)
- [ ] Documentation dependencies installed (ast-decompiler, markdown-builder)
- [ ] Monitoring dependencies installed (psutil, watchdog)
- [ ] Learning dependencies installed (scikit-learn, pandas)
- [ ] New agent configuration added
- [ ] SecurityAgent base implementation
- [ ] DocumentationAgent base implementation

---

### Go/No-Go Decision Gate

**Ready to proceed to Phase 1 ONLY when:**

```
┌────────────────────────────────────────────────────────┐
│  GO/NO-GO REVIEW                                       │
├────────────────────────────────────────────────────────┤
│                                                        │
│  [ ] P23 Complete                                      │
│      └─ Orchestrator < 4K lines                       │
│                                                        │
│  [ ] Handoff Extended                                  │
│      └─ MAX_DEPTH=3, background support               │
│                                                        │
│  [ ] Task Persistence                                  │
│      └─ Recovery working, cron scheduling            │
│                                                        │
│  [ ] Communication Layer                               │
│      └─ MessageBus or A2A working                    │
│                                                        │
│  [ ] All Tests Green                                   │
│      └─ New tests + existing tests passing           │
│                                                        │
│  [ ] Risk Assessment Complete                          │
│      └─ All critical risks mitigated                 │
│                                                        │
│  DECISION: [ GO ] [ NO-GO ] [ DEFER ]                 │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## Part 7: Implementation Sequence

### Correct Order (Critical Path):

```
Week 1: Prerequisites
├── Day 1-2: Complete P23 (orchestrator reduction)
├── Day 3: Extend HandoffManager
├── Day 4: Add task persistence
├── Day 5: Build MessageBus (simplified)
└── End of Week: Go/No-Go Review

Week 2+: Phase 1 (Subagents) - ONLY IF GO
├── Day 1-2: SubAgentManager + WorktreeManager
├── Day 3-4: Basic spawning + lifecycle
├── Day 5: Integration + testing
└── End of Week: Phase 1 Review

Week 3+: Phase 2+ - Continue...
```

### Wrong Order (DO NOT DO):

```
❌ Start Phase 1 without P23
   └─ Will hit line limit, circular deps

❌ Add subagents without IPC layer
   └─ Can't communicate, can't get progress

❌ Skip task persistence
   └─ No background tasks, no $ralph

❌ Skip handoff extension
   └─ MAX_DEPTH=1 blocks all subagent chains
```

---

## Part 8: Quick Reference

### Critical Files to Monitor

| File | Current Lines | Target | Status |
|------|---------------|--------|--------|
| `agent_orchestrator.py` | 3,776 | < 4,000 | 🔴 BLOCKING |
| `handoff_manager.py` | 133 | +100 lines | 🔴 BLOCKING |
| `task_models.py` | ~200 | +50 lines | 🔴 BLOCKING |
| `requirements.txt` | - | +10 deps | 🟡 NEEDS UPDATE |
| `settings.py` | ~400 | +100 lines | 🟡 NEEDS UPDATE |

### Must Have Before Phase 1

1. ✅ P23 complete (orchestrator < 4K lines)
2. ✅ HandoffManager extended (depth > 1)
3. ✅ Task persistence layer
4. ✅ IPC/MessageBus working
5. ✅ All tests green

### Must Have Before Phase 1.5 (New Agent Types)

6. ✅ SecurityAgent dependencies (bandit, safety, semgrep)
7. ✅ DocumentationAgent dependencies (AST parsing, markdown)
8. ✅ MonitoringAgent dependencies (psutil, watchdog)
9. ✅ LearningAgent dependencies (scikit-learn)
10. ✅ IntegrationAgent dependencies (API clients)
11. ✅ DataAgent dependencies (pandas, numpy, matplotlib)
12. ✅ Agent registry supports dynamic registration

### Can Wait Until Later

- ❌ Full A2A protocol (Phase 7)
- ❌ LiveKit integration (Phase 4)
- ❌ All 40+ tools (Phases 2-3)
- ❌ Plugin system (Phase 6)
- ❌ Complete Buddy system (Phases 5-6)
- ❌ Agent Pet System (Post Phase 7)

---

## Summary

**Current State:** Maya has solid foundations but **4 critical blockers** must be resolved before implementing the Multi-Agent Plan.

**Critical Path:**
1. **P23** → Reduce orchestrator (2-3 days)
2. **Handoff** → Extend depth (1 day)
3. **Tasks** → Add persistence (2-3 days)
4. **IPC** → Build MessageBus (1-2 days)
5. **Go/No-Go Review** → Decision gate

**Total Pre-Implementation:** 6-9 days  
**Risk Reduction:** 70%  
**Confidence Level After:** High

**Recommendation:** Do not start Phase 1 until all prerequisites are complete and Go/No-Go review passes.

---

## Part 9: New Agent Types - Prerequisites

### 9.1 SecurityAgent Prerequisites

**Dependencies:**
- bandit (Python security linter)
- safety (dependency vulnerability checker)
- detect-secrets (credential scanning)
- semgrep (static analysis patterns)

**Configuration:**
```python
SECURITY_SCAN_ENABLED = True
SECURITY_SCAN_ON_SAVE = True
SECURITY_FAIL_ON_HIGH_SEVERITY = True
SECURITY_IGNORED_PATHS = [".venv/", "node_modules/"]
```

**Database:**
- Security scan results table
- Vulnerability tracking

**Estimated Additional Effort:** +1 day

---

### 9.2 DocumentationAgent Prerequisites

**Dependencies:**
- ast-decompiler (AST parsing)
- markdown-builder
- plantuml (diagrams)

**Configuration:**
```python
AUTO_GENERATE_README = True
AUTO_UPDATE_CHANGELOG = True
DOCS_GENERATION_STYLE = "google"
```

**Estimated Additional Effort:** +0.5 days

---

### 9.3 MonitoringAgent Prerequisites

**Dependencies:**
- psutil (system metrics)
- watchdog (file watching)

**Configuration:**
```python
SYSTEM_METRICS_INTERVAL = 60
FILE_WATCH_PATTERNS = ["*.py", "*.md"]
ALERT_THRESHOLDS = {"cpu": 80, "memory": 90}
```

**Estimated Additional Effort:** +0.5 days

---

### 9.4 LearningAgent Prerequisites

**Dependencies:**
- scikit-learn (pattern recognition)
- pandas (data analysis)

**Configuration:**
```python
LEARNING_ENABLED = True
PATTERN_THRESHOLD = 0.8
SHORTCUT_SUGGESTION_ENABLED = True
```

**Storage:**
- Pattern database
- User preference store

**Estimated Additional Effort:** +1 day

---

### 9.5 IntegrationAgent Prerequisites

**Dependencies:**
- github3-py (GitHub API)
- slack-sdk (Slack)
- google-api-python-client (Google)

**Configuration:**
```python
INTEGRATIONS_ENABLED = ["github", "slack"]
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
```

**Estimated Additional Effort:** +1 day

---

### 9.6 DataAgent Prerequisites

**Dependencies:**
- pandas, numpy
- matplotlib (visualization)
- openpyxl (Excel)

**Configuration:**
```python
DEFAULT_DATA_FORMAT = "pandas"
MAX_DATASET_SIZE_MB = 100
```

**Estimated Additional Effort:** +0.5 days

---

### Total Additional Prerequisites for New Agents

| Agent | Effort | Critical Path |
|-------|--------|---------------|
| SecurityAgent | +1 day | 🔴 Yes (safety critical) |
| DocumentationAgent | +0.5 days | 🟡 No (can defer) |
| MonitoringAgent | +0.5 days | 🟡 No (can defer) |
| LearningAgent | +1 day | 🟡 No (can defer) |
| IntegrationAgent | +1 day | 🟡 No (can defer) |
| DataAgent | +0.5 days | 🟡 No (can defer) |

**Recommendation:** Install SecurityAgent dependencies during Phase 0. Others can be added incrementally.

---

**Document Location:** `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/NEW_futhur plan/Maya-Pre-Implementation-Prerequisites-Analysis.md`

**Version:** 1.1 (Updated with New Agent Types)  
**Last Updated:** April 5, 2025  
**Next Review:** Before Phase 1 kickoff
