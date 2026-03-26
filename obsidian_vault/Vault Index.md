# Maya Agent Obsidian Vault

## Overview
Structured knowledge graph for the Maya Agent system containing architecture, components, decisions, bugs, workflows, and concepts.

**Vault Location:** `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/`

## Vault Statistics
- **Total Notes:** 42+
- **Architecture Notes:** 8
- **Component Notes:** 12
- **Decision Notes:** 4
- **Bug Notes:** 3
- **Workflow Notes:** 3
- **Memory Notes:** 4
- **Concept Notes:** 4
- **Templates:** 5
- **Canvas Files:** 4 visual diagrams

## Quick Navigation

### Architecture
- [[7-Layer Runtime Chain]] - The strict layered architecture
- [[Phase Architecture]] - 9-phase rollout (currently Phase 9 complete)
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

### External Integrations (Phase 9+)
- **MCP Integration** - Model Context Protocol for external tools
- **Skills Marketplace** - Dynamic skill installation/management
- **GSD Workflow** - Project planning and execution via GSD
- **Ralph Loop** - Autonomous execution engine with state persistence

### Current Issues (March 2026)
**Resolved:**
- ✓ [[LLM Tool-Call Schema Mismatch]] - Working as designed (Groq API compatibility)
- ✓ [[FTS5 Memory Search Running Unnecessarily]] - Small-talk bypass confirmed
- ✓ [[Context Builder Token Bloat]] - Token budgets correctly configured

**Recently Fixed:**
- ✓ Context token budget reduced to < 2000 (Phase 6)
- ✓ Tool gating and safety enforcement (Phase 6)
- ✓ Trace propagation across all layers (Phase 7)
- ✓ TTS priority queue for voice stability (Phase 7)
- ✓ Phase 9A-D: Handoff contracts, specialist agents, worker prompts (March 2026)
- ✓ External tool integrations: MCP, Skills, GSD, Ralph Loop (March 2026)

### Key Decisions
- [[Context Gating and Tool Safety]] (Phase 6) - Token budget reduction to < 2000
- [[TTS Priority Queue]] (Phase 7) - Voice stability improvements
- [[Trace Propagation]] (Phase 7) - Distributed tracing across layers
- [[Console Handler Using Old Orchestrator API]] (FIXED) - Single-brain alignment

### Phase Status
| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Global Resources & Provider Initialization | ✓ Complete |
| 2 | Orchestration & Single-Brain Execution | ✓ Complete |
| 3 | Tool Pipeline Integration | ✓ Complete |
| 4 | Intent, Planning & Worker Execution | ✓ Complete |
| 5 | Voice Pipeline (Audio Session Management) | ✓ Complete |
| 6 | Memory System & Context Integrity | ✓ Complete |
| 7 | Provider Resilience & Chaos Recovery | ✓ Complete |
| 8 | Frontend State Synchronization | ✓ Complete |
| 9A | Internal Multi-Agent Handoff Contract | ✓ Complete |
| 9B | Media Agent Specialization | ✓ Complete |
| 9C | Worker Prompt Authority Architecture | ✓ Complete |
| 9D | Scheduling Agent Specialization | ✓ Complete |
| 9E | Note CRUD Implementation | ⏳ Pending |

### Workflows
- [[Development Workflow]] - Standardized change process
- [[Testing Workflow]] - Comprehensive testing strategy
- [[Code-Maintenance Protocol]] - Refactoring and maintenance process
- [[Daily Progress]] - [[2026-03-24]] (Latest) - Daily development tracking

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
- Directory structure (01-Architecture/ through 08-Concepts/)

## Linking
Every note links to at least 2 related notes using [[Note Name]] format. Follow links to navigate the knowledge graph.

## Updates
When updating the vault:
1. Update existing notes (don't overwrite completely)
2. Merge intelligently
3. Preserve previous knowledge
4. Append new insights

## Recently Added (March 2026)
- ✓ [[2026-03-24]] - External tool integrations complete (MCP, Skills, GSD, Ralph Loop)
- ✓ [[2026-03-23]] - Phase 9D calendar closure and 9E planning
- ✓ Phase 9A-9D: Handoff contracts, media/scheduling agents, worker prompts
- ✓ HandoffManager with depth/parent guards
- ✓ AgentHandoffRequest/AgentHandoffResult contracts
- ✓ Worker prompt authority with type overlays
- ✓ Host capability profile for resource awareness
- ✓ Media and Scheduling specialist agents
- ✓ Component docs: Subagent-Driven Development, ToolManager, ContextBuilder, ExecutionManager
- ✓ Trace propagation across all layers (Phase 7)
- ✓ TTS priority queue for voice stability (Phase 7)
- ✓ External integration components:
  - MCP Integration (180 lines)
  - Skills Marketplace (510 lines)
  - GSD Workflow Integration (320 lines)
  - Ralph Loop (920 lines)

## Canvas Visualizations
Located in [[Canvases]] folder:
- [[Maya-Project-Overview.canvas]] - Full project overview with 7-layer architecture
- [[Maya-Architecture-Details.canvas]] - Detailed architecture per layer
- [[Maya-Component-Details.canvas]] - Component deep dive diagrams
- [[Maya-Memory-System.canvas]] - Memory system visualization

See [[Canvases/Canvas-Summary]] for detailed canvas documentation.
