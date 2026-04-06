# Flutter Widget Catalog

## Layout Widgets

### SessionLayout
**File**: `lib/widgets/session/session_layout.dart`

Main layout container for agent sessions.

**Layout Structure**:
```
┌─────────────────────────────────┐
│  Sidebar   │    Main Content    │
│  (optional)│                    │
│            │   ┌───────────┐   │
│            │   │   Orb       │   │
│            │   │  (centered) │   │
│            │   └───────────┘   │
│            │                    │
│            │   ┌───────────┐   │
│            │   │ Control   │   │
│            │   │   Bar     │   │
│            │   └───────────┘   │
└─────────────────────────────────┘
```

**Properties**:
| Property | Type | Description |
|----------|------|-------------|
| `showSidebar` | `bool` | Show/hide sidebar |
| `sidebarWidth` | `double` | Width of sidebar (default: 250) |
| `onSessionEnd` | `VoidCallback?` | End session callback |

### AgentScreen
**File**: `lib/screens/agent_screen.dart`

Main screen containing the complete agent experience.

**Features**:
- Session initialization
- Layout mode switching
- Error handling
- Settings access

## Orb Widgets

### CosmicOrb
**File**: `lib/widgets/cosmic_orb.dart`

Primary animated orb visualization.

**Animation States**:
| State | Visual | Trigger |
|-------|--------|---------|
| `idle` | Gentle pulse | No activity |
| `listening` | Expanding rings | User speaking |
| `thinking` | Rotating particles | Agent processing |
| `speaking` | Wave visualization | TTS active |

**Controller**: `OrbController` manages state transitions.

### ClassicOrb
**File**: `lib/widgets/classic_orb.dart`

Alternative minimal orb style.

## Chat Widgets

### ChatOverlay
**File**: `lib/widgets/session/chat_overlay.dart`

Sliding chat interface with glass morphism effect.

**Features**:
- Slide in/out animation
- Message list with scroll
- Input field with send button
- Auto-scroll to latest message

### AgentThinkingBubble
**File**: `lib/widgets/features/chat/agent_thinking_bubble.dart`

Animated "agent is thinking" indicator.

**Design**:
- Three dots with staggered animation
- Gradient background
- Glass morphism container

### ResearchResultBubble
**File**: `lib/widgets/features/chat/research_result_bubble.dart`

Displays research results with expandable sections.

**Structure**:
- Summary header
- Expandable details
- Source citations
- Action buttons

### SourceCardsPanel
**File**: `lib/widgets/features/chat/source_cards_panel.dart`

Horizontal scrollable source cards.

**Features**:
- Favicon loading
- Title + URL preview
- Tap to open source
- Horizontal scroll

## Settings Widgets

### SettingsDialog
**File**: `lib/widgets/settings/settings_dialog.dart`

Main settings container with tabbed interface.

**Tabs**:
1. **General** - Theme, language, defaults
2. **AI Providers** - Provider selection, models
3. **API Keys** - Secure key management
4. **Voice & Audio** - TTS/STT configuration
5. **Memory** - Chat history, persistence
6. **Personalization** - User preferences
7. **Account** - Profile, logout

### APIKeysPanel
**File**: `lib/widgets/settings/api_keys_panel.dart`

Secure API key input with validation.

**Security**:
- Masked input (dots instead of characters)
- Show/hide toggle
- Secure storage on save
- Validation indicators

### PersonalizationPanel
**File**: `lib/widgets/settings/personalization_panel.dart`

User preference configuration.

**Options**:
- Response style (concise/detailed)
- Default agent mode
- Notification preferences
- Shortcut customization

## Control Widgets

### MessageBar
**File**: `lib/widgets/message_bar.dart`

Bottom input bar for message entry.

**Features**:
- Text input with multiline support
- Send button with animation
- Voice input toggle
- Quick action buttons

### ControlBar
**File**: `lib/widgets/control_bar.dart`

Session control buttons.

**Buttons**:
- Microphone (voice input)
- End session
- Settings
- Chat toggle

### ShellSidebar
**File**: `lib/widgets/shell_sidebar.dart`

Collapsible sidebar for session navigation.

**Sections**:
- Session list
- New session button
- Settings shortcut
- User profile

## Glass Morphism Widgets

### GlassContainer
**File**: `lib/widgets/glass_container.dart`

Reusable glass effect container.

**Properties**:
| Property | Default | Description |
|----------|---------|-------------|
| `blur` | 10.0 | Blur radius |
| `opacity` | 0.2 | Background opacity |
| `borderRadius` | 16.0 | Corner radius |
| `borderColor` | white12 | Border color |

### FloatingGlass
**File**: `lib/widgets/floating_glass.dart`

Floating panel with glass effect.

## Utility Widgets

### ZoyaButton
**File**: `lib/widgets/zoya_button.dart`

Custom styled button with ripple effect.

**Variants**:
- `primary` - Filled with accent color
- `secondary` - Outlined
- `ghost` - No background

### SessionErrorBanner
**File**: `lib/widgets/session/session_error_banner.dart`

Error state display with retry action.

**Features**:
- Auto-dismiss timeout
- Retry button
- Error icon animation
- Collapsible

### AppLayoutSwitcher
**File**: `lib/widgets/app_layout_switcher.dart`

Toggle between different app layouts.

**Modes**:
- Agent (full experience)
- Classic (simplified)
- Minimal (orb only)

## Design System

### Colors
**File**: `lib/ui/color_pallette.dart`

```dart
class ColorPalette {
  static const primary = Color(0xFF6C63FF);
  static const accent = Color(0xFF00BFA6);
  static const background = Color(0xFF1A1A2E);
  static const surface = Color(0xFF16213E);
  static const error = Color(0xFFE94560);
}
```

### Typography
**File**: `lib/ui/zoya_theme.dart`

| Style | Font | Size | Weight |
|-------|------|------|--------|
| Headline | Inter | 24 | Bold |
| Title | Inter | 18 | SemiBold |
| Body | Inter | 14 | Regular |
| Caption | Inter | 12 | Regular |

### Spacing

```dart
const kSpacingXS = 4.0;
const kSpacingSM = 8.0;
const kSpacingMD = 16.0;
const kSpacingLG = 24.0;
const kSpacingXL = 32.0;
```

## Related
- [[Flutter-Architecture-Overview]]
- [[State-Management]]
