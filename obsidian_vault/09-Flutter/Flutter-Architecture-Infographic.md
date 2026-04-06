# Flutter Architecture Infographic

## Visual Overview

```mermaid
flowchart TB
    subgraph Users["👥 Users"]
        U1[Mobile App]
        U2[Desktop App]
        U3[Web App]
    end

    subgraph Flutter["🎨 Flutter Frontend"]
        subgraph UI["UI Layer"]
            S1[SessionLayout]
            S2[ChatOverlay]
            S3[CosmicOrb]
            S4[SettingsDialog]
        end

        subgraph State["State Layer"]
            P1[AuthProvider]
            P2[SettingsProvider]
            P3[ChatProvider]
            P4[SessionProvider]
            P5[UIProvider]
        end

        subgraph Services["Service Layer"]
            SV1[BackendSyncService]
            SV2[LiveKitService]
            SV3[SettingsService]
            SV4[SupabaseService]
            SV5[SecureKeyStorage]
        end
    end

    subgraph Backend["⚙️ Python Backend"]
        B1[AgentOrchestrator]
        B2[HybridMemoryManager]
        B3[TaskWorker]
    end

    subgraph External["🌐 External Services"]
        E1[LiveKit Server]
        E2[Supabase]
        E3[OpenAI/Groq]
    end

    Users --> UI
    UI --> State
    State --> Services

    SV1 -->|WebSocket| B1
    SV2 -->|WebRTC| E1
    SV4 -->|HTTP| E2

    B1 --> B2
    B1 --> B3
    B1 --> E3

    style UI fill:#e3f2fd
    style State fill:#e8f5e9
    style Services fill:#fff3e0
    style Backend fill:#fce4ec
    style External fill:#f3e5f5
```

## Data Flow Architecture

```mermaid
sequenceDiagram
    participant User as 👤 User
    participant UI as 🎨 UI Widget
    participant State as 📊 Provider
    participant Service as 🔌 Service
    participant Backend as ⚙️ Python Agent

    User->>UI: Tap Send
    UI->>State: sendMessage(text)
    State->>State: Update UI (loading)
    State->>Service: sendMessage(text)
    Service->>Backend: WebSocket JSON
    Backend->>Backend: Process
    Backend-->>Service: Response JSON
    Service-->>State: Message received
    State->>State: Update messages list
    State-->>UI: Rebuild with new state
    UI-->>User: Display response
```

## Provider Hierarchy

```mermaid
graph TD
    BP[BaseProvider]

    BP -->|extends| AP[AuthProvider]
    BP -->|extends| SP[SettingsProvider]
    BP -->|extends| CP[ChatProvider]
    BP -->|extends| SeP[SessionProvider]
    BP -->|extends| UP[UIProvider]

    AP -->|uses| SuS[SupabaseService]
    SP -->|uses| SeS[SecureKeyStorage]
    SP -->|uses| StS[SettingsService]
    CP -->|uses| BS[BackendSyncService]
    SeP -->|uses| BS
    UP -->|uses| None

    style BP fill:#fff3e0
    style AP fill:#e3f2fd
    style SP fill:#e3f2fd
    style CP fill:#e3f2fd
    style SeP fill:#e3f2fd
    style UP fill:#e3f2fd
```

## State Management Flow

```mermaid
stateDiagram-v2
    [*] --> Idle: App Start

    Idle --> Initializing: initApp()

    Initializing --> Authenticated: Login Success
    Initializing --> Unauthenticated: No Session

    Authenticated --> Connecting: Start Session
    Connecting --> Connected: WebSocket OK
    Connecting --> Error: Connection Failed

    Connected --> Listening: User Speaking
    Listening --> Thinking: Message Sent
    Thinking --> Responding: Agent Reply
    Responding --> Connected: Complete

    Connected --> Disconnected: Network Error
    Disconnected --> Connecting: Retry

    Authenticated --> Unauthenticated: Logout
    Unauthenticated --> Initializing: Login
```

## Security Architecture

```mermaid
flowchart LR
    subgraph Input["🔐 Secure Input"]
        I1[API Key Field]
        I2[Password Field]
    end

    subgraph Storage["🗄️ Storage"]
        S1[Secure Storage]
        S2[Shared Preferences]
    end

    subgraph Network["🌐 Network"]
        N1[WSS/HTTPS]
        N2[Token Auth]
    end

    I1 -->|Encrypted| S1
    I2 -->|Encrypted| S1
    S1 -->|Token| N2
    N2 -->|Secure| N1

    S2 -->|Settings| I1

    style S1 fill:#ffebee
    style N1 fill:#e8f5e9
```

## Widget Tree Structure

```mermaid
graph TD
    M[MaterialApp]
    M --> MultiProvider

    MultiProvider --> App
    App --> AgentScreen

    AgentScreen --> SessionLayout
    SessionLayout --> Sidebar
    SessionLayout --> MainContent

    MainContent --> CosmicOrb
    MainContent --> ChatOverlay
    MainContent --> ControlBar

    ChatOverlay --> MessageList
    ChatOverlay --> MessageBar

    MessageList --> UserBubble
    MessageList --> AgentBubble
    MessageList --> ThinkingBubble

    ControlBar --> MicButton
    ControlBar --> SettingsButton
    ControlBar --> EndSessionButton

    style M fill:#e3f2fd
    style AgentScreen fill:#e8f5e9
    style SessionLayout fill:#fff3e0
```

## Performance Metrics

| Metric | Target | Current |
|--------|--------|---------|
| App Start Time | < 3s | ~2.5s |
| First Frame | < 1s | ~0.8s |
| Message Latency | < 500ms | ~300ms |
| Memory Usage | < 150MB | ~120MB |
| WebSocket Reconnect | < 3s | ~2s |

## Key Technologies

| Layer | Technology | Purpose |
|-------|------------|---------|
| State | Provider | Reactive state management |
| HTTP | dio | REST API communication |
| WebSocket | websocket | Real-time messaging |
| WebRTC | livekit | Audio/video streaming |
| Storage | hive | Local persistence |
| Secure | flutter_secure_storage | Encrypted credentials |
| Backend | Supabase | Auth & database |

## Related
- [[Flutter-Architecture-Overview]]
- [[State-Management]]
- [[Services-Overview]]
- [[Widget-Catalog]]
