# Maya Project Status Infographic

## Phase Timeline

```mermaid
gantt
    title Maya Agent Development Timeline
    dateFormat YYYY-MM-DD
    section Foundation
    Phase 1 :done, p1, 2024-01-01, 30d
    Phase 2 :done, p2, after p1, 30d
    Phase 3 :done, p3, after p2, 30d
    Phase 4 :done, p4, after p3, 30d

    section Intelligence
    Phase 5 :done, p5, after p4, 30d
    Phase 6 :done, p6, after p5, 30d
    Phase 7 :done, p7, after p6, 30d
    Phase 8 :done, p8, after p7, 30d

    section Advanced
    Phase 9 :done, p9, after p8, 45d
    Phase 10 :done, p10, after p9, 15d
    Phase 11 :active, p11, after p10, 30d
```

## System Architecture Overview

```mermaid
flowchart TB
    subgraph Frontend["🎨 Frontend"]
        F1[Flutter App]
        F2[Web Console]
        F3[CLI Mode]
    end

    subgraph Backend["⚙️ Backend"]
        B1[AgentOrchestrator]
        B2[PlanningEngine]
        B3[TaskWorker]
        B4[MemoryManager]
    end

    subgraph External["🌐 External"]
        E1[LLM Providers]
        E2[LiveKit]
        E3[Supabase]
        E4[Vector DB]
    end

    Frontend -->|WebSocket/HTTP| Backend
    Backend -->|API| External

    style Frontend fill:#e3f2fd
    style Backend fill:#e8f5e9
    style External fill:#fff3e0
```

## Test Coverage

```mermaid
pie title Test Distribution
    "Unit Tests" : 45
    "Integration Tests" : 30
    "E2E Tests" : 15
    "Chaos Tests" : 10
```

## Phase Completion Status

```mermaid
xychart-beta
    title "Phase Completion Rate"
    x-axis [Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7, Phase 8, Phase 9, Phase 10, Phase 11]
    y-axis "Completion %" 0 --> 100
    bar [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 35]
```

## Code Distribution

```mermaid
pie title Codebase by Language
    "Python (Agent)" : 65
    "Dart (Flutter)" : 25
    "Tests" : 8
    "Config/Scripts" : 2
```

## Memory System Architecture

```mermaid
flowchart LR
    subgraph Query["🔍 Query"]
        Q1[User Input]
    end

    subgraph Detection["🧠 Detection"]
        D1{Small Talk?}
    end

    subgraph Search["🔎 Search"]
        S1[Vector Search]
        S2[FTS5 Keyword]
    end

    subgraph Merge["🔄 Merge"]
        M1[Hybrid Retriever]
    end

    subgraph Context["📝 Context"]
        C1[LLM Context]
    end

    Q1 --> D1
    D1 -->|No| S1
    D1 -->|No| S2
    S1 --> M1
    S2 --> M1
    M1 --> C1

    style D1 fill:#fff3e0
    style M1 fill:#e8f5e9
    style C1 fill:#e3f2fd
```

## Current Sprint Status

```mermaid
kanban
    title Phase 11 Sprint Board
    subgraph Todo["⏳ Todo"]
        P11_03[P11-03: Memory Observability]
        P11_04[P11-04: Session-Scoped Recall]
    end

    subgraph InProgress["🔄 In Progress"]
        P11_02[P11-02: Vector Path Issue]
    end

    subgraph Done["✅ Done"]
        P11_01[P11-01: Provider Supervisor]
    end
```

## Commit Activity

```mermaid
heatmap
    title "Commit Activity (Last 7 Days)"
    x-axis Day [Mon, Tue, Wed, Thu, Fri, Sat, Sun]
    y-axis Hour [Morning, Afternoon, Evening, Night]
    data [5, 8, 12, 3, 6, 9, 15, 4, 7, 11, 2, 8, 10, 6, 4, 9, 7, 5, 13, 8, 6, 11, 4, 9, 7, 5, 8, 6]
```

## Team Velocity

```mermaid
xychart-beta
    title "Sprint Velocity"
    x-axis [Sprint 1, Sprint 2, Sprint 3, Sprint 4, Sprint 5]
    y-axis "Story Points" 0 --> 50
    bar [32, 38, 45, 41, 48]
    line [30, 30, 30, 30, 30]
```

## Bug Resolution Trend

```mermaid
xychart-beta
    title "Bug Resolution (Last 30 Days)"
    x-axis Week [Week 1, Week 2, Week 3, Week 4]
    y-axis "Count" 0 --> 20
    bar [15, 12, 8, 5]
    line [12, 10, 7, 4]
```

## Related
- [[Phase Architecture]]
- [[7-Layer Runtime Chain]]
- [[Flutter-Architecture-Overview]]
