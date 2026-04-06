# Maya Agent Obsidian Vault

## Overview
Structured knowledge graph for the Maya Agent system containing architecture, components, decisions, bugs, workflows, and concepts.

**Vault Location:** `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/`

## Vault Statistics
- **Total Notes:** 48+
- **Architecture Notes:** 8
- **Component Notes:** 12
- **Flutter Notes:** 4 (NEW)
- **Decision Notes:** 4
- **Bug Notes:** 3
- **Workflow Notes:** 3
- **Memory Notes:** 4
- **Concept Notes:** 4
- **Templates:** 5
- **Canvas Files:** 5 visual diagrams

## Quick Navigation

### Architecture
- [[7-Layer Runtime Chain]] - The strict layered architecture
- [[Phase Architecture]] - Multi-phase rollout (currently Phase 11 active)
- [[Single-Brain Pattern]] - GlobalAgentContainer singleton
- [[Role-Based LLM System]] - CHAT/TOOL_ACTION/PLANNER/WORKER roles
- [[Intent-First Routing]] - Intent classification before LLM
- [[Hybrid Memory System]] - Vector + keyword hybrid search
- [[Task Worker System]] - Planning → Storage → Execution pipeline

### Critical Components
- [[GlobalAgentContainer]] - Singleton with shared resources
- [[AgentOrchestrator]] - Central decision hub/brain
- [[SmartLLM]] - LLM wrapper with role management
- [[PlanningEngine]] - Task decomposition (2-5 min tasks)
- [[HybridMemoryManager]] - Memory retrieval with small-talk bypass
- [[TaskStore]] - SQLite task persistence
- [[TaskWorker]] - Background task execution loop
- [[ExecutionRouter]] - Intent classification and routing
- [[ToolManager]] - Tool registry and execution coordination
- [[ContextBuilder]] - LLM context with intent-based filtering
- [[ExecutionManager]] - Task and step execution coordination
- [[Subagent-Driven Development]] - Pattern for specialist workers
- [[HandoffManager]] - Inter-agent handoff coordination

### Flutter Frontend (09-Flutter/)
- [[Flutter-Architecture-Overview]] - Cross-platform UI architecture
- [[State-Management]] - Provider pattern and reactive state
- [[Services-Overview]] - BackendSync, LiveKit, Settings services
- [[Widget-Catalog]] - UI widgets and design system

### External Integrations (Phase 9+)
- **MCP Integration** - Model Context Protocol for external tools
- **Skills Marketplace** - Dynamic skill installation/management
- **GSD Workflow** - Project planning and execution via GSD
- **Ralph Loop** - Autonomous execution engine with state persistence

### Current Issues (April 2026)
**Active Work (Phase 12):**
- 🔄 **Voice Turn Detection & Routing** - EOU model + context-aware routing
- 🔄 Settings dialog layout overflow (27px in desktop)

**New Analysis (2026-04-01):**
- 📋 **Implementation Plan:** `/home/harsha/.claude/plans/scalable-sprouting-gray.md`
- 📝 **Daily Log:** [[2026-04-01]] - Full architecture analysis

**Phase 11 Memory Work:**
- 🔄 [[Memory Recall - Session Scoped]] - Session-scoped retrieval in progress
- 🔄 [[Context Builder Token Bloat]] - Ongoing optimization

**Recently Fixed (Phase 11):**
- ✅ Memory write timing (await before resolve)
- ✅ user_id alignment (write/read consistency)
- ✅ Provider supervisor configuration (P11-01)

**Previously Resolved:**
- ✅ [[LLM Tool-Call Schema Mismatch]] - Working as designed (Groq API compatibility)
- ✅ [[FTS5 Memory Search Running Unnecessarily]] - Small-talk bypass confirmed
- ✅ Context token budget reduced to < 2000 (Phase 6)
- ✅ Tool gating and safety enforcement (Phase 6)
- ✅ Trace propagation across all layers (Phase 7)
- ✅ TTS priority queue for voice stability (Phase 7)
- ✅ Phase 9A-D: Handoff contracts, specialist agents, worker prompts (March 2026)
- ✅ External tool integrations: MCP, Skills, GSD, Ralph Loop (March 2026)

### Key Decisions
- [[Context Gating and Tool Safety]] (Phase 6) - Token budget reduction to < 2000
- [[TTS Priority Queue]] (Phase 7) - Voice stability improvements
- [[Trace Propagation]] (Phase 7) - Distributed tracing across layers
- [[Console Handler Using Old Orchestrator API]] (FIXED) - Single-brain alignment

### Phase Status
| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Global Resources & Provider Initialization | ✅ Complete |
| 2 | Orchestration & Single-Brain Execution | ✅ Complete |
| 3 | Tool Pipeline Integration | ✅ Complete |
| 4 | Intent, Planning & Worker Execution | ✅ Complete |
| 5 | Voice Pipeline (Audio Session Management) | ✅ Complete |
| 6 | Memory System & Context Integrity | ✅ Complete |
| 7 | Provider Resilience & Chaos Recovery | ✅ Complete |
| 8 | Frontend State Synchronization | ✅ Complete |
| 9A | Internal Multi-Agent Handoff Contract | ✅ Complete |
| 9B | Media Agent Specialization | ✅ Complete |
| 9C | Worker Prompt Authority Architecture | ✅ Complete |
| 9D | Scheduling Agent Specialization | ✅ Complete |
| 9E | Note CRUD Implementation | ✅ Complete |
| 10 | Baseline Validation & Release | ✅ Complete (v0.10.0) |
| 11 | Memory Stabilization | 🔄 Active |
| 12 | Voice Turn Detection & Routing | 🔄 Planning |

### Phase 11 Details
| Item | Description | Status |
|------|-------------|--------|
| P11-01 | Provider supervisor configuration | ✅ Resolved |
| P11-02 | Chroma vector path stabilization | 🔄 Active |
| P11-03 | Memory observability improvements | ⏳ Pending |
| P11-04 | Session-scoped recall implementation | ⏳ Pending |

### Phase 12 Planned (Voice Turn Detection)
| Item | Description | Priority |
|------|-------------|----------|
| P12-01 | Enable LiveKit EOU Model | High |
| P12-02 | Add utterance completeness guard | High |
| P12-03 | Thread chat_ctx to AgentRouter | High |
| P12-04 | Add agent liveness heartbeat | Medium |

### Recent Commits
- `ff69c08` - fast-path contract + LiveKit metrics
- `bddb61f` - memory recall stabilization
- `94361fa` - memory timing fix (await before resolve)
- `f526408` - user_id mismatch fix
- `74c3012` - memory user_id tagging

### Workflows
- [[Development Workflow]] - Standardized change process
- [[Testing Workflow]] - Comprehensive testing strategy
- [[Code-Maintenance Protocol]] - Refactoring and maintenance process
- [[Daily Progress]] - [[2026-04-01]] (Latest) - Daily development tracking

### Knowledge Sources
This vault was created from:
- CLAUDE.md (comprehensive project documentation)
- CLAUDE_PROJECT_CONTEXT.md (runtime chain and critical rules)
- CLAUDE_RULES.md (mandatory development rules)
- Agent/docs/architecture_phases_master.md (9-phase architecture)

## Search & Browse
Search notes by:
- Tags (Architecture, Components, Decisions, Bugs, etc.)
- Links (follow [[...]] references)
- Directory structure (01-Architecture/ through 09-Flutter/)

## Linking
Every note links to at least 2 related notes using [[Note Name]] format. Follow links to navigate the knowledge graph.

## Updates
When updating the vault:
1. Update existing notes (don't overwrite completely)
2. Merge intelligently
3. Preserve previous knowledge
4. Append new insights

## Recently Added (March-April 2026)
- ✓ [[Flutter-Architecture-Overview]] - New Flutter documentation
- ✓ [[State-Management]] - Provider pattern docs
- ✓ [[Services-Overview]] - Service layer documentation
- ✓ [[Widget-Catalog]] - UI component catalog
- ✓ [[Maya-Flutter-Architecture.canvas]] - Frontend canvas
- ✓ Phase 11 active - Memory Stabilization
- ✓ P11-01 resolved (provider supervisor)
- ✓ Memory fixes: write timing, user_id alignment
- ✓ v0.10.0 released
- ✓ Phase 10 completed with 186 tests passing
- ✓ **Voice turn detection analysis** (2026-04-01)
- ✓ **Implementation plan for EOU + context-aware routing** (2026-04-01)

## Canvas Visualizations
Located in [[Canvases]] folder:
- [[Maya-Project-Overview.canvas]] - Full project overview with 7-layer architecture
- [[Maya-Architecture-Details.canvas]] - Detailed architecture per layer
- [[Maya-Component-Details.canvas]] - Component deep dive diagrams
- [[Maya-Memory-System.canvas]] - Memory system visualization
- [[Maya-Flutter-Architecture.canvas]] - Flutter frontend architecture (NEW)

See [[Canvas-Summary]] for detailed canvas documentation.

## Implementation Plans (External)
- **Voice Turn Detection Plan:** `/home/harsha/.claude/plans/scalable-sprouting-gray.md`
  - EOU model integration
  - Utterance completeness guard
  - Context-aware routing (chat_ctx threading)
  - Agent liveness heartbeat