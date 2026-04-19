# Maya Agent Obsidian Vault

## Overview
Structured knowledge graph for the Maya Agent system containing architecture, components, decisions, bugs, workflows, and concepts.

**Vault Location:** `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/`
**Last Full Update:** 2026-04-19 (vault brought current from April 6 to April 19 — 16 phases added)

## Vault Statistics
- **Total Notes:** 70+
- **Architecture Notes:** 8
- **Component Notes:** 12
- **Flutter Notes:** 4
- **Decision Notes:** 4
- **Bug Notes:** 3 (all resolved/closed)
- **Workflow Notes:** 3
- **Memory Notes:** 4
- **Concept Notes:** 4
- **Templates:** 5
- **Daily Notes:** 34 (through 2026-04-19)
- **Canvas Files:** 5 visual diagrams

## Quick Navigation

### Architecture
- [[7-Layer Runtime Chain]] - The strict layered architecture
- [[Phase Architecture]] - Multi-phase rollout (currently Phase 12 active)
- [[Single-Brain Pattern]] - GlobalAgentContainer singleton
- [[Role-Based LLM System]] - CHAT/TOOL_ACTION/PLANNER/WORKER roles
- [[Intent-First Routing]] - Deterministic fast-path + LLM routing with shadow envelope
- [[Hybrid Memory System]] - Vector + keyword hybrid search with small-talk bypass
- [[Task Worker System]] - Planning → Storage → Execution pipeline
- [[Semantic Tape]] - Session-scoped in-memory conversation tape for pronoun resolution

### Critical Components
- [[GlobalAgentContainer]] - Singleton with shared resources
- [[AgentOrchestrator]] - Central decision hub/brain (decomposed into 14 modules)
- [[SmartLLM]] - LLM wrapper with role management
- [[PlanningEngine]] - Task decomposition (2-5 min tasks)
- [[HybridMemoryManager]] - Memory retrieval with small-talk bypass
- [[TaskStore]] - SQLite task persistence
- [[TaskWorker]] - Background task execution loop
- [[ExecutionRouter]] - Intent classification and routing
- [[ToolManager]] - Tool registry and execution coordination
- [[ContextBuilder]] - LLM context with dynamic turn shaping (4-6 turns)
- [[ExecutionManager]] - Task and step execution coordination
- [[Subagent-Driven Development]] - Pattern for specialist workers
- [[HandoffManager]] - Inter-agent handoff coordination
- [[ConversationTape]] - In-memory session-scoped tape for pronoun resolution (Phase 11A)
- [[FastPathRouter]] - Deterministic intent routing (Phase 26 extraction)

### Flutter Frontend (09-Flutter/)
- [[Flutter-Architecture-Overview]] - Cross-platform UI architecture
- [[State-Management]] - Provider pattern and reactive state
- [[Services-Overview]] - BackendSync, LiveKit, Settings services
- [[Widget-Catalog]] - UI widgets and design system
- [[VoiceProjectBridge]] - Flutter↔Python voice transcript bridge (Phase 35)

### Phase 11A: Context Integrity + Semantic Tape
- [[ConversationTape]] - Session-scoped in-memory tape (last 6 turns)
- Pronoun resolution now reads tape → research-tagged entries → unfiltered fallback
- Dynamic context shaping: adaptive 4-6 recent turns based on session lifecycle
- LLM routing with deterministic fast-path contract for first-turn routing

### Phase 12: IDE Runtime (Active — feature/p12-ide-runtime branch)
- **P12.1 IDE Runtime Foundation** (shipping)
  - `core/ide/ide_session_manager.py` — open/close/get sessions, max 5 concurrent
  - `core/ide/ide_file_service.py` — workspace-scoped read/write/tree, path traversal guard
  - `core/ide/ide_action_guard.py` — ActionEnvelope risk policy enforcement
  - `core/ide/ide_state_bus.py` — in-process async pub/sub event bus
  - API: `POST /ide/session/open`, `POST /ide/session/close`, `GET /ide/files/tree`, `GET /ide/file/read`, `POST /ide/file/write`
- **P12.2 Flutter IDE Tab** (planned): Files | Terminal | Agentic panels

### External Integrations (Phase 9+, fully integrated)
- **MCP Core Infrastructure** — `core/tools/mcp/` (Phase 29)
  - Plugins: email (SMTP/IMAP), home_assistant, google_maps, google_drive
- **Skills Marketplace** — Dynamic skill installation/management
- **GSD Workflow** — Project planning and execution
- **Ralph Loop** — Autonomous execution engine with state persistence
- **AgentScope** — Model wiring infrastructure (v0.39.0)
- **MsgHub** — Live IPC for background subagents (v0.40.0)

### Agent Pets System (Phase 33, v0.41.0)
- Buddy companion with XP and 5 evolution stages
- Persistence across sessions
- Integration with personality system

### Permission System (Phase 32)
- `core/action/verifier.py` — Action precedence and verification
- `core/action/state_store.py` — Action state persistence
- Role-based execution gates: USER/ADMIN/SPECTATOR roles

## Current Issues (April 2026)
**Active Work (Phase 12, branch `feature/p12-ide-runtime`):**
- 🔄 **P12.1 IDE Runtime Foundation** — API handlers, session manager, action guard (9 tests passing)
- 🔄 Flutter IDE tab integration (P12.2 planned for next phase)

**Acknowledged Technical Debt:**
- 🔄 `core/orchestrator/chat_mixin.py:642` — HACK: `smart_llm` not cleanly injected; patch via `agent.py` attachment. Needs clean `__init__` injection.
- 🔄 Supabase optional mode — test guest path with no credentials for offline resilience

**Recently Fixed (Phase 11A):**
- ✅ Phase 11A Context Integrity + Semantic Tape (Pronoun resolution fully operational in live runtime)
- ✅ LLM Fact Classifier + Personality overlays (PR #15, #16)
- ✅ VoiceProjectBridge — Flutter↔Python voice transcript (PR #14)
- ✅ MCP core plugins: email, home_assistant, google_maps, google_drive (PR #13)
- ✅ Google OAuth desktop flow + callback UI
- ✅ Agent Pets system with XP and 5 stages

**Previously Resolved (all verified closed):**
- ✅ [[LLM Tool-Call Schema Mismatch]] - Working as designed (Groq API compatibility)
- ✅ [[FTS5 Memory Search Running Unnecessarily]] - Small-talk bypass confirmed
- ✅ Context token budget: memory section 2000 tokens, total 12000 (model window cap, correct)
- ✅ Tool gating and safety enforcement (Phase 6)
- ✅ Trace propagation across all layers (Phase 7)
- ✅ TTS priority queue for voice stability (Phase 7)
- ✅ Phase 9A-E: Handoff contracts, specialist agents, worker prompts (Phase 9A-D), Note CRUD (Phase 9E)
- ✅ External tool integrations: MCP, Skills, GSD, Ralph Loop (Phase 9+)
- ✅ Memory write timing (await before resolve) — Phase 11/P12
- ✅ user_id alignment (write/read consistency) — Phase 11
- ✅ Provider supervisor configuration (P11-01) — Phase 11

### Key Decisions
- [[Context Gating and Tool Safety]] (Phase 6) - Memory section: 2000 tokens; total: 12000 (model window cap)
- [[TTS Priority Queue]] (Phase 7) - Voice stability improvements
- [[Trace Propagation]] (Phase 7) - Distributed tracing across layers
- Semantic Tape Priority (Phase 11A) — research-tagged tape entries used before fallthrough

## Phase Status (Complete as of 2026-04-19)

| Phase | Description | Status | Tag |
|-------|-------------|--------|-----|
| 1 | Global Resources & Provider Initialization | ✅ Complete | |
| 2 | Orchestration & Single-Brain Execution | ✅ Complete | |
| 3 | Tool Pipeline Integration | ✅ Complete | |
| 4 | Intent, Planning & Worker Execution | ✅ Complete | |
| 5 | Voice Pipeline (Audio Session Management) | ✅ Complete | |
| 6 | Memory System & Context Integrity | ✅ Complete | |
| 7 | Provider Resilience & Chaos Recovery | ✅ Complete | |
| 8 | Frontend State Synchronization | ✅ Complete | |
| 9A | Internal Multi-Agent Handoff Contract | ✅ Complete | |
| 9B | Media Agent Specialization | ✅ Complete | |
| 9C | Worker Prompt Authority Architecture | ✅ Complete | |
| 9D | Scheduling Agent Specialization | ✅ Complete | |
| 9E | Note CRUD Implementation | ✅ Complete | |
| 10 | Baseline Validation & Release | ✅ Complete | v0.10.0 |
| 11 | Memory Stabilization | ✅ Complete | |
| 11A | Context Integrity + Semantic Tape | ✅ Complete | (post-v0.44.0 feature) |
| 12 | IDE Runtime (P12.1 shipping, P12.2 planned) | 🔄 In Progress | feature/p12-ide-runtime |
| P25 | Orchestration Spine Extraction | ✅ Complete | v0.25.0 |
| P26 | Orchestrator Decomposition (14 modules) | ✅ Complete | v0.26.0 |
| P27 | Voice Certification Hardening | ✅ Complete | v0.27.0 |
| P28 | CI Production Readiness Automation | ✅ Complete | v0.28.0 |
| P29-P38 | SubAgent System, Team Mode, Permissions, Pets, Slash Commands, Project Mode, Feature Flags, RL, Docker/K8s | ✅ Delivered (squash) | v0.27.0-v0.38.0 |
| P39 | AgentScope Model Wiring | ✅ Complete | v0.39.0 |
| P40 | MsgHub Live IPC | ✅ Complete | v0.40.0 |
| P41 | Agent Pets System | ✅ Complete | v0.41.0 |
| P42 | LiveKit Voice Bridge | ✅ Complete | v0.42.0 |
| P43 | MCP Core Plugins | ✅ Complete | (merged via PR #13) |
| P44 | Google OAuth Desktop Flow | ✅ Complete | (merged via PR #15/16) |

### Phase 12 IDE Runtime (Active)
| Item | Description | Status |
|------|-------------|--------|
| P12.1 | IDE Runtime Foundation (session manager, file service, action guard, state bus) | ✅ Shipping |
| P12.2 | Flutter IDE Tab (Files \| Terminal \| Agentic) | 🔄 Planned |
| P12.3 | IDE terminal exec integration | 🔄 Planned |

## Recent Commits (v0.28.0 → v0.44.0, HEAD)
```
a811a74e — test: Google auth test hardening (2026-04-18)
e9087cdb — fix(pronoun): do you know about antecedent (2026-04-17)
0b22b250 — Phase 11A: Context Integrity + Semantic Tape (2026-04-17)
9ecb407e — fix: pin agentscope==1.0.18 (2026-04-16)
b5aedfd6 — feat(auth): Google OAuth desktop flow (2026-04-16)
6526b351 — feat(auth-ui): Google sign-in UI (2026-04-16)
1b3bec38 — fix: Supabase optional + guest auth + worker fix (2026-04-16)
b842b540 — chore: realistic monitoring alert thresholds (2026-04-15)
be1ce131 — fix(api): race condition in /ready endpoint (2026-04-14)
0b854080 — feat: voice project bridge + buddy TTS (2026-04-14)
79553a03 — feat: LLM fact classifier + personality injection (2026-04-14)
92863da1 — feat: LLM fact classifier + fast-path fixes (2026-04-14)
9d00f574 — feat: VoiceProjectBridge Flutter↔Python (PR #14, 2026-04-13)
8286698c — feat(mcp): MCP cherry-pick — 4 plugins (PR #13, 2026-04-12)
5afd34fa — integrate: P27-P38 delivery track (2026-04-11)
e931ec22 — integrate: LiveKit voice bridge v0.42 (2026-04-11)
b358866c — integrate: Agent Pets v0.41 (2026-04-11/12)
36c01990 — integrate: MsgHub IPC v0.40 (2026-04-11/12)
e4e125fa — test(P25): handler contract coverage (2026-04-06, Phase 25)
```

**Full version chain:** v0.14.0 → v0.44.0 (all tags on remote)

### Verified Baseline (2026-04-19)
- **Full regression:** 1275 passed, 65 warnings, 0 failed
- **Phase 11A targeted:** 134 passed
- **Phase 12.1 tests:** 9 passed (`tests/test_ide_runtime.py`)
- **GitNexus index:** up-to-date at `a811a74e`

## Workflows
- [[Development Workflow]] - Standardized change process
- [[Testing Workflow]] - Comprehensive testing strategy
- [[Code-Maintenance Protocol]] - Refactoring and maintenance process
- [[Daily Progress]] - [[2026-04-19]] (Latest) - Daily development tracking

## Daily Progress
Daily logs from [[2026-04-04]] through [[2026-04-19]] are all present and up to date.
Notable:
- [[2026-04-06]] — Phase 25-28 closure (orchestrator decomposition complete)
- [[2026-04-08]] — P27-P38 squash merge to main (v0.27.0-v0.38.0)
- [[2026-04-11]] — Phase 28 squash merge + personality system
- [[2026-04-16]] — Supabase optional + Google OAuth
- [[2026-04-17]] — Phase 11A Context Integrity + Semantic Tape
- [[2026-04-19]] — Vault update + Phase 12.1 IDE Runtime (current)

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

## Vault Maintenance Log
- **2026-04-19**: Complete vault audit. Brought current (April 6 → April 19, 16 phases). Added April 7-18 daily notes. Resolved reports moved to `Reports/Resolved/`. Root `Analysis-Report.md` placed in `Daily/2026-04-12-Phase-12-Voice-Analysis.md`. Vault Index fully updated.
- Phase baseline moved from v0.28.0 to v0.44.0 (HEAD)
- All Phase 11/12/11A memory and context work verified as resolved

## Canvas Visualizations
Located in [[Canvases]] folder:
- [[Maya-Project-Overview.canvas]] - Full project overview with 7-layer architecture
- [[Maya-Architecture-Details.canvas]] - Detailed architecture per layer
- [[Maya-Component-Details.canvas]] - Component deep dive diagrams
- [[Maya-Memory-System.canvas]] - Memory system visualization
- [[Maya-Flutter-Architecture.canvas]] - Flutter frontend architecture

See [[Canvas-Summary]] for detailed canvas documentation.

## Implementation Plans (External)
- **Phase 12 IDE Runtime Plan:** Branch `feature/p12-ide-runtime`
  - P12.1: API endpoints, session manager, action guard, file service — shipping now
  - P12.2: Flutter IDE tab (Files | Terminal | Agentic) — next phase
  - P12.3: IDE terminal exec integration
- **Former Voice Turn Detection Plan (superseded):** `/home/harsha/.claude/plans/scalable-sprouting-gray.md`
  - Superseded by Phase 11A (Semantic Tape + dynamic context shaping)
  - EOU model + context-aware routing now delivered via conversational tape architecture