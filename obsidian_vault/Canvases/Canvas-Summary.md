# Canvas Files Summary

## Created JSON Canvas Files

### 1. Maya-Project-Overview.canvas (5.1K, 83 lines)
**Sector 1: Full Project Overview**
- Project title and description
- 7-Layer Runtime Chain (mermaid diagram)
- Key components overview
- Current status (Phase 11 Active - Memory Stabilization)
- Critical files and change risk levels
- Database and configuration
- Navigation links with quick commands
- Mermaid diagram: Layered architecture visualization

### 2. Maya-Architecture-Details.canvas (8.7K, 112 lines)
**Sector 2: Detailed Architecture**
- **Layer 1:** LifecycleManager (boot, modes, recovery)
- **Layer 2:** ConsoleHarness (strict contract, thin shell)
- **Layer 3:** Entrypoint agent.py (fixed dual-brain issue)
- **Layer 4:** GlobalAgentContainer initialization flow
- **Layer 5:** AgentOrchestrator (central brain)
- **Layer 6:** Task + Worker system (PlanningEngine, TaskStore, TaskWorker)
- **Layer 7:** Tools layer (registry, execution, schema issues)
- Complete 7-layer data flow Mermaid diagram
- GlobalAgentContainer class diagram
- Runtime golden flow across all layers

### 3. Maya-Component-Details.canvas (6.9K, 69 lines)
**Sector 3: Component Deep Dive**
- GlobalAgentContainer class diagram
- Component interaction flow Mermaid
- Component reference grid (8 core components)
- SmartLLM deep dive (roles, configurations, issues)
- Task system details (PlanningEngine, TaskStore, TaskWorker)
- Task specification schema
- TaskStore SQLite schema
- TaskWorker background loop

### 4. Maya-Memory-System.canvas (6.9K, 82 lines)
**Sector 4: Memory System**
- Hybrid Memory System flow diagram
- Vector search details (Qdrant/ChromaDB)
- FTS5 keyword search details (SQLite FTS5)
- Optimization strategies (Small-Talk Bypass, ContextGuard)
- Performance metrics (Phase 6 improvements)
- Known issues with impact assessment

### 5. Maya-Flutter-Architecture.canvas (NEW)
**Sector 5: Flutter Frontend Architecture**
- UI Layer: SessionLayout, ChatOverlay, CosmicOrb, SettingsDialog
- State Layer: AuthProvider, SettingsProvider, ChatProvider, SessionProvider
- Service Layer: BackendSyncService, LiveKitService, SettingsService, SupabaseService
- External Systems: Python Agent (WebSocket), LiveKit Server (WebRTC)
- Data flow visualization (UI → Provider → Service → Backend)
- Provider Pattern documentation
- Connection: Links to Python backend via WebSocket/WebRTC

## External Integrations Canvas (Future)

### 6. Maya-External-Integrations.canvas (Recommended Addition)
**Sector 6: External Tool Ecosystem**
- MCP Integration architecture
- Skills Marketplace flow
- GSD Workflow integration
- Ralph Loop autonomous execution
- Slash command routing
- State persistence patterns

## Canvas Features

### Visual Layout
- Nodes positioned for logical flow (top → bottom, left → right)
- Color-coded sections (blue=architecture, green=config, red=bugs/orange=issues)
- Connection edges between related concepts
- Grouped by functional area

### Mermaid Diagrams Included
1. **7-Layer Architecture** - Layered runtime chain
2. **GlobalAgentContainer** - Class diagram with components
3. **Component Interaction** - Flow from user message → LLM → task → response
4. **Complete Runtime Flow** - Full 7-layer data flow
5. **Memory System** - Query → detection → search → merge → context
6. **Flutter Architecture** - UI → State → Service → Backend data flow

### Information Density
- Each canvas contains 6-10 information nodes
- Nodes include: architecture details, component specs, metrics, issues
- Cross-references to vault notes using [[Note Name]] format
- Quick command references for testing

### Quality Metrics
- **Total lines:** 400+ lines across 5 canvases
- **Total size:** 35KB+
- **Mermaid diagrams:** 6 comprehensive diagrams
- **Connection edges:** 15+ connection paths
- **Nodes:** 40+ information blocks
- **Color coding:** 6 visual categories

## How to Use

### Opening in Obsidian
1. Open Obsidian vault: `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/`
2. Navigate to [[Canvases]] folder
3. Open any `.canvas` file
4. Click and drag to navigate
5. Zoom in/out for details

### Canvas Navigation
- **Pan:** Click and drag empty space
- **Zoom:** Scroll wheel / pinch gesture
- **Nodes:** Click to edit/view
- **Edges:** Show relationships
- **Mermaid:** Renders as SVG diagrams

### Best Viewing Order
1. **Maya-Project-Overview.canvas** - Start here for big picture
2. **Maya-Architecture-Details.canvas** - Deep dive into 7-layer architecture
3. **Maya-Component-Details.canvas** - Component specifications
4. **Maya-Memory-System.canvas** - Memory system details
5. **Maya-Flutter-Architecture.canvas** - Frontend architecture

## Related Files
- [[Vault Index]] - Text-based vault overview
- [[7-Layer Runtime Chain]] - Architecture note
- [[GlobalAgentContainer]] - Component note
- [[Hybrid Memory System]] - Memory architecture
- [[Phase Architecture]] - Phase rollout status (Phase 11 active)
- [[Flutter-Architecture-Overview]] - Frontend documentation

## Recent Updates (March 2026)

### Phase 11 (Current)
- **P11-01:** ✅ Provider supervisor configuration (resolved)
- **P11-02:** 🔄 Chroma vector path issue (active)
- **P11-03:** ⏳ Memory observability improvements
- **P11-04:** ⏳ Session-scoped recall implementation

### Recent Commits
- `ff69c08` - fast-path contract + LiveKit metrics
- `bddb61f` - memory recall stabilization
- `94361fa` - memory timing fix (await before resolve)
- `f526408` - user_id mismatch fix
- `74c3012` - memory user_id tagging

### Phase 10 (Completed)
- v0.10.0 tagged and released
- 186 tests passing across 4 batches
- Memory pipeline audit logging added

### Phase 9 (Completed)
- **Phase 9A-D:** Handoff contracts, media/scheduling agents
- **External Integrations:** MCP, Skills Marketplace, GSD, Ralph Loop
- Handoff system fully operational

### New Documentation (2026-03-30)
- Created 09-Flutter folder in vault
- Added Flutter architecture documentation
- Created Maya-Flutter-Architecture.canvas
- Updated project status to Phase 11
