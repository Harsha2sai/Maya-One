# React to Flutter Architecture - Full Conversion Plan

## Executive Summary

This document outlines the complete architectural conversion of the React Agent Starter app to Flutter, maintaining 1:1 parity in UI, UX, features, and business logic.

---

## Phase 1: React App Analysis

### Source Structure
```
agent-starter-react-main/
├── app/
│   ├── (app)/          # Main app routes
│   ├── (auth)/         # Auth routes
│   ├── api/            # API routes
│   ├── globals.css     # ZOYA design system
│   └── layout.tsx      # Root layout
├── components/
│   ├── app/            # 25 app components
│   ├── auth/           # Auth components
│   ├── brand/          # Brand assets
│   └── livekit/        # LiveKit integration
├── styles/
│   ├── globals.css     # Bioluminescent theme
│   ├── auth.css
│   └── user-menu.css
├── hooks/              # Custom React hooks
├── lib/                # Utilities
└── public/             # Static assets
```

### Design System Discovered

**Primary Theme: "ZOYA" (Zoya Interface)**
- Background: `#050510` (deep space black)
- Sidebar: `#0a0a14` (darker variant)
- Accent: `#00f3ff` (cyan neon)
- Secondary: `#bc13fe` (purple)
- Glass: `rgba(20, 20, 35, 0.6)` with 12px blur
- Fonts: Orbitron (display), Roboto (body)

**Secondary Theme: "Bioluminescent Forest"**
- Deep teal/green palette
- Neon lime accents
- Used in different routes

### Key Components Identified

#### Session & Layout (25 components)
1. `session-view.tsx` - Main session container
2. `sidebar.tsx` - Navigation sidebar
3. `cosmic-orb.tsx` - Particle visualizer
4. `welcome-view.tsx` - Initial landing
5. `chat-transcript.tsx` - Message display
6. `chat-input.tsx` - Message input
7. `tile-layout.tsx` - Video tile management
8. `audio-modal.tsx` - Audio settings
9. `settings-modal.tsx` - Settings panel (MASSIVE - 58KB!)
10. `dashboard-modal.tsx` - Dashboard view
11. `history-modal.tsx` - Conversation history
12. `memory-modal.tsx` - Memory management
13. `loading-screen.tsx` - Loading states
14. `preconnect-message.tsx` - Pre-connection UI
15. `view-controller.tsx` - View state management
16. `theme-toggle.tsx` - Theme switcher
17. `theme-provider.tsx` - Theme context

#### LiveKit Integration (17 components)
- Agents, audio, video, connection management

#### Auth (2 components)
- Login/logout flows

---

## Phase 2: Flutter Architecture Design

### Target Structure
```
lib/
├── core/
│   ├── config/
│   │   ├── app_config.dart          # App-wide configuration
│   │   ├── api_config.dart          # API endpoints
│   │   └── livekit_config.dart      # LiveKit settings
│   ├── constants/
│   │   ├── app_constants.dart       # App constants
│   │   ├── route_names.dart         # Named routes
│   │   └── asset_paths.dart         # Asset paths
│   ├── utils/
│   │   ├── logger.dart              # Logging utility
│   │   ├── validators.dart          # Input validation
│   │   └── helpers.dart             # General helpers
│   └── services/
│       ├── storage_service.dart     # Local storage
│       ├── api_service.dart         # HTTP client
│       └── livekit_service.dart     # LiveKit SDK wrapper
├── theme/
│   ├── app_theme.dart               # Main theme export
│   ├── zoya_theme.dart              # ZOYA design system
│   ├── bioluminescent_theme.dart   # Alternative theme
│   ├── app_colors.dart              # Color palette
│   ├── app_typography.dart          # Text styles
│   ├── app_dimensions.dart          # Spacing/sizes
│   └── app_animations.dart          # Animation constants
├── routes/
│   ├── app_router.dart              # Main router
│   ├── route_generator.dart         # Route generation logic
│   └── route_guards.dart            # Auth guards
├── models/
│   ├── user/
│   │   ├── user_model.dart
│   │   └── user_preferences.dart
│   ├── session/
│   │   ├── session_model.dart
│   │   ├── message_model.dart
│   │   └── agent_state_model.dart
│   ├── livekit/
│   │   ├── room_model.dart
│   │   ├── participant_model.dart
│   │   └── track_model.dart
│   └── settings/
│       └── app_settings_model.dart
├── state/
│   ├── providers/
│   │   ├── session_provider.dart    # Session state
│   │   ├── chat_provider.dart       # Chat messages
│   │   ├── ui_provider.dart         # UI state (modals, etc.)
│   │   ├── settings_provider.dart   # App settings
│   │   └── theme_provider.dart      # Theme state
│   └── app_state.dart               # Root state
├── widgets/
│   ├── common/
│   │   ├── glass_container.dart
│   │   ├── neon_button.dart
│   │   ├── loading_indicator.dart
│   │   └── custom_scrollbar.dart
│   ├── cosmic_orb/
│   │   ├── cosmic_orb.dart
│   │   ├── orb_painter.dart
│   │   └── particle_system.dart
│   ├── chat/
│   │   ├── chat_transcript.dart
│   │   ├── chat_input.dart
│   │   ├── message_bubble.dart
│   │   └── typing_indicator.dart
│   └── navigation/
│       ├── app_sidebar.dart
│       └── nav_item.dart
├── features/
│   ├── welcome/
│   │   ├── view/
│   │   │   └── welcome_screen.dart
│   │   ├── controller/
│   │   │   └── welcome_controller.dart
│   │   └── widgets/
│   │       └── connection_button.dart
│   ├── session/
│   │   ├── view/
│   │   │   └── session_screen.dart
│   │   ├── controller/
│   │   │   └── session_controller.dart
│   │   └── widgets/
│   │       ├── session_layout.dart
│   │       ├── video_tile_grid.dart
│   │       └── control_bar.dart
│   ├── dashboard/
│   │   ├── view/
│   │   │   └── dashboard_screen.dart
│   │   ├── controller/
│   │   │   └── dashboard_controller.dart
│   │   └── widgets/
│   │       └── stat_card.dart
│   ├── history/
│   │   ├── view/
│   │   │   └── history_screen.dart
│   │   ├── controller/
│   │   │   └── history_controller.dart
│   │   └── widgets/
│   │       └── history_item.dart
│   ├── settings/
│   │   ├── view/
│   │   │   └── settings_screen.dart
│   │   ├── controller/
│   │   │   └── settings_controller.dart
│   │   └── widgets/
│   │       ├── setting_section.dart
│   │       ├── setting_item.dart
│   │       └── device_selector.dart
│   └── auth/
│       ├── view/
│       │   ├── login_screen.dart
│       │   └── logout_dialog.dart
│       └── controller/
│           └── auth_controller.dart
└── main.dart

```

---

## Phase 3: Component Mapping

### React → Flutter Conversion Matrix

| React Component | Flutter Widget | Location | Dependencies |
|----------------|----------------|----------|--------------|
| `welcome-view.tsx` | `WelcomeScreen` | `features/welcome/view/` | theme, session_provider |
| `session-view.tsx` | `SessionScreen` | `features/session/view/` | livekit_service, session_provider |
| `sidebar.tsx` | `AppSidebar` | `widgets/navigation/` | ui_provider, router |
| `cosmic-orb.tsx` | `CosmicOrb` | `widgets/cosmic_orb/` | CustomPainter, AnimationController |
| `chat-transcript.tsx` | `ChatTranscript` | `widgets/chat/` | chat_provider, ListView.builder |
| `chat-input.tsx` | `ChatInput` | `widgets/chat/` | TextEditingController, session_provider |
| `settings-modal.tsx` | `SettingsScreen` | `features/settings/view/` | settings_provider, device services |
| `dashboard-modal.tsx` | `DashboardScreen` | `features/dashboard/view/` | session data, charts |
| `history-modal.tsx` | `HistoryScreen` | `features/history/view/` | storage_service |
| `audio-modal.tsx` | `AudioSettingsDialog` | `features/settings/widgets/` | device services |
| `loading-screen.tsx` | `LoadingScreen` | `widgets/common/` | animation, theme |
| `theme-toggle.tsx` | `ThemeToggleButton` | `widgets/common/` | theme_provider |
| `tile-layout.tsx` | `VideoTileGrid` | `features/session/widgets/` | GridView, participant data |

---

## Phase 4: State Management Strategy

### Provider Architecture

**Root Providers (MultiProvider in main.dart):**
```dart
MultiProvider(
  providers: [
    ChangeNotifierProvider(create: (_) => ThemeProvider()),
    ChangeNotifierProvider(create: (_) => SessionProvider()),
    ChangeNotifierProvider(create: (_) => ChatProvider()),
    ChangeNotifierProvider(create: (_) => UIProvider()),
    ChangeNotifierProvider(create: (_) => SettingsProvider()),
    ChangeNotifierProvider(create: (_) => AuthProvider()),
  ],
  child: App(),
)
```

**State Flow:**
```
User Action → Controller → Provider → Notifies Listeners → UI Rebuilds
```

---

## Phase 5: Design System Implementation

### Theme Tokens (from globals.css)

```dart
class ZoyaColors {
  static const mainBg = Color(0xFF050510);
  static const sidebarBg = Color(0xFF0A0A14);
  static const glassBg = Color.fromRGBO(20, 20, 35, 0.6);
  static const glassBorder = Color.fromRGBO(100, 200, 255, 0.1);
  static const textColor = Color(0xFFE0E6ED);
  static const textMuted = Color(0xFF6C7A89);
  static const accent = Color(0xFF00F3FF);
  static const accentGlow = Color.fromRGBO(0, 243, 255, 0.4);
  static const secondaryAccent = Color(0xFFBC13FE);
  static const danger = Color(0xFFFF2A6D);
  static const success = Color(0xFF05D5FA);
}

class ZoyaTypography {
  static const displayFont = 'Orbitron';
  static const bodyFont = 'Roboto';
}

class ZoyaDimensions {
  static const sidebarWidth = 280.0;
  static const sidebarCollapsedWidth = 70.0;
  static const borderRadius = 16.0;
  static const glassBlur = 12.0;
}
```

---

## Phase 6: Routing Strategy

### Named Routes
```dart
class AppRoutes {
  static const welcome = '/';
  static const session = '/session';
  static const dashboard = '/dashboard';
  static const history = '/history';
  static const settings = '/settings';
  static const login = '/auth/login';
}
```

### Route Generator
```dart
Route<dynamic> generateRoute(RouteSettings settings) {
  switch (settings.name) {
    case AppRoutes.welcome:
      return MaterialPageRoute(builder: (_) => WelcomeScreen());
    case AppRoutes.session:
      return MaterialPageRoute(builder: (_) => SessionScreen());
    // ... etc
  }
}
```

---

## Phase 7: Implementation Priority

### Sprint 1: Foundation (CRITICAL)
1. ✅ Theme system (ZoyaTheme) - DONE
2. ✅ Core widgets (GlassContainer, etc.) - DONE
3. ⏳ State providers setup
4. ⏳ Router configuration
5. ⏳ Service layer (API, Storage, LiveKit)

### Sprint 2: Core Features
1. ⏳ Welcome screen (full React parity)
2. ⏳ Session screen layout
3. ⏳ Sidebar navigation
4. ⏳ Cosmic Orb (complete particle system)
5. ⏳ Chat transcript & input

### Sprint 3: Advanced Features
1. ⏳ Settings screen (massive conversion from 58KB file)
2. ⏳ Dashboard screen
3. ⏳ History screen
4. ⏳ Audio/video device management
5. ⏳ LiveKit full integration

### Sprint 4: Polish & Sync
1. ⏳ Animations (match CSS keyframes)
2. ⏳ Responsive layouts
3. ⏳ Error handling
4. ⏳ Loading states
5. ⏳ Testing & debugging

---

## Phase 8: Quality Checklist

### UI Parity
- [ ] Colors match exactly
- [ ] Spacing matches CSS
- [ ] Typography matches
- [ ] Animations match
- [ ] Layout proportions match
- [ ] Component hierarchy matches

### Functional Parity
- [ ] All routes working
- [ ] State management working
- [ ] LiveKit integration working
- [ ] Settings persist
- [ ] Chat works
- [ ] Audio/video controls work

### Code Quality
- [ ] Clean architecture
- [ ] No monolithic files
- [ ] Proper separation of concerns
- [ ] Documented code
- [ ] No hardcoded values
- [ ] Proper error handling

---

## Next Steps

**IMMEDIATE ACTIONS:**
1. Set up state providers
2. Create router configuration
3. Build service layer
4. Convert remaining screens
5. Implement full LiveKit integration

**STATUS:** Ready to proceed with full conversion
**ESTIMATED TIME:** 8-12 hours for complete parity
**CURRENT PROGRESS:** ~20% (UI foundations complete)
