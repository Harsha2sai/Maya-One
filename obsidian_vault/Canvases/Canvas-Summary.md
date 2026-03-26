# Canvas Files Summary

## Created JSON Canvas Files

### 1. Maya-Project-Overview.canvas (5.1K, 83 lines)
**Sector 1: Full Project Overview**
- Project title and description
- 7-Layer Runtime Chain (mermaid diagram)
- Key components overview
- Current status (Phase 9 Complete)
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

## External Integrations Canvas (Future)

### 5. Maya-External-Integrations.canvas (Recommended Addition)
**Sector 5: External Tool Ecosystem**
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

### Information Density
- Each canvas contains 6-10 information nodes
- Nodes include: architecture details, component specs, metrics, issues
- Cross-references to vault notes using [[Note Name]] format
- Quick command references for testing

### Quality Metrics
- **Total lines:** 346 lines across 4 canvases
- **Total size:** 27.6KB
- **Mermaid diagrams:** 5 comprehensive diagrams
- **Connection edges:** 10+ connection paths
- **Nodes:** 30+ information blocks
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

## Related Files
- [[Vault Index]] - Text-based vault overview
- [[7-Layer Runtime Chain]] - Architecture note
- [[GlobalAgentContainer]] - Component note
- [[Hybrid Memory System]] - Memory architecture
- [[Phase Architecture]] - Phase rollout status (Phase 9 complete)

## Recent Updates (March 2026)
- **Phase 9A-D** completed: Handoff contracts, media/scheduling agents
- **External Integrations** completed: MCP, Skills Marketplace, GSD, Ralph Loop
- Consider adding canvas for external integrations ecosystem
