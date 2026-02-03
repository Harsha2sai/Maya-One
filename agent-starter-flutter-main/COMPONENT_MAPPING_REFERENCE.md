# React Component Mapping Reference
## Detailed Component-by-Component Conversion Guide

---

## Overview

This document provides a **1:1 mapping** between React components and their Flutter equivalents, with specific implementation notes for each.

---

## Component Mapping Table

| # | React Component | Size | Flutter Equivalent | Priority | Status | Notes |
|---|----------------|------|-------------------|----------|--------|-------|
| 1 | `welcome-view.tsx` | 3.1KB | `WelcomeScreen` | HIGH | ✅ DONE | Template provided |
| 2 | `session-view.tsx` | 10.8KB | `SessionScreen` | HIGH | ✅ DONE | Template provided |
| 3 | `sidebar.tsx` | 6.7KB | `AppSidebar` | HIGH | 🔨 PARTIAL | Needs completion |
| 4 | `cosmic-orb.tsx` | 3.6KB | `CosmicOrb` | HIGH | ✅ DONE | Template provided |
| 5 | `chat-transcript.tsx` | 2.5KB | `ChatTranscript` | HIGH | ✅ DONE | Template provided |
| 6 | `chat-input.tsx` | 4.4KB | `ChatInput` | MEDIUM | ⏳ TODO | Template needed |
| 7 | `tile-layout.tsx` | 9.2KB | `VideoTileGrid` | MEDIUM | ⏳ TODO | Complex layout |
| 8 | `settings-modal.tsx` | 58.9KB | `SettingsScreen` | MEDIUM | ⏳ TODO | MASSIVE! Break into widgets |
| 9 | `dashboard-modal.tsx` | 5.8KB | `DashboardScreen` | LOW | ⏳ TODO | Charts needed |
| 10 | `history-modal.tsx` | 12.3KB | `HistoryScreen` | LOW | ⏳ TODO | List view |
| 11 | `memory-modal.tsx` | 12.7KB | `MemoryScreen` | LOW | ⏳ TODO | List view |
| 12 | `audio-modal.tsx` | 12.2KB | `AudioSettingsDialog` | LOW | ⏳ TODO | Device selection |
| 13 | `loading-screen.tsx` | 6.2KB | `LoadingScreen` | LOW | ⏳ TODO | Animations |
| 14 | `theme-toggle.tsx` | 1.7KB | `ThemeToggleButton` | LOW | ⏳ TODO | Simple widget |
| 15 | `view-controller.tsx` | 1.4KB | Provider logic | n/a | ✅ DONE | In UIProvider |

---

## Detailed Component Breakdowns

### 1. settings-modal.tsx (58.9KB) - CRITICAL

This is the **largest and most complex** component. Must be broken down:

**React Structure:**
```typescript
// settings-modal.tsx splits into:
- Audio Settings Section
- Video Settings Section  
- Advanced Settings Section
- Device Selection Components
- VAD Settings
- LiveKit Configuration
- Model/Provider Settings
- Debug Panel
```

**Flutter Structure:**
```dart
lib/features/settings/
├── view/
│   └── settings_screen.dart           // Main screen
├── controller/
│   └── settings_controller.dart
└── widgets/
    ├── audio_settings_section.dart    // Audio config
    ├── video_settings_section.dart    // Video config
    ├── advanced_settings_section.dart
    ├── device_selector_widget.dart    // Mic/speaker/camera
    ├── vad_settings_widget.dart       // Voice activity detection
    ├── model_provider_selector.dart
    ├── debug_panel_widget.dart
    └── setting_tile.dart              // Reusable tile
```

**Implementation Priority:**
1. Basic settings screen layout
2. Device selector (mic, speaker, camera)
3. Audio/video basic settings
4. Advanced settings
5. Debug panel (last)

**Complexity:** ⭐⭐⭐⭐⭐ (Very High)
**Estimated Time:** 6-8 hours

---

### 2. tile-layout.tsx (9.2KB) - Video Grid

**React Logic:**
- Dynamic grid layout based on participant count
- Adaptive tile sizing
- Focus mode
- Screen share handling

**Flutter Implementation:**

```dart
// lib/features/session/widgets/video_tile_grid.dart

class VideoTileGrid extends StatelessWidget {
  final List<Participant> participants;
  final Participant? focusedParticipant;
  
  @override
  Widget build(BuildContext context) {
    if (participants.isEmpty) {
      return const Center(child: Text('No participants'));
    }
    
    // Calculate grid dimensions
    final count = participants.length;
    final columns = _calculateColumns(count);
    final rows = (count / columns).ceil();
    
    return GridView.builder(
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        childAspectRatio: 16 / 9,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
      ),
      itemCount: count,
      itemBuilder: (context, index) {
        return VideoTile(participant: participants[index]);
      },
    );
  }
  
  int _calculateColumns(int count) {
    if (count == 1) return 1;
    if (count <= 4) return 2;
    if (count <= 9) return 3;
    return 4;
  }
}
```

**Complexity:** ⭐⭐⭐ (Medium)
**Estimated Time:** 2-3 hours

---

### 3. history-modal.tsx (12.3KB) - Conversation History

**React Features:**
- List of past conversations
- Search/filter
- Delete conversations
- Export functionality

**Flutter Implementation:**

```dart
// lib/features/history/view/history_screen.dart

class HistoryScreen extends StatefulWidget {
  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<ConversationModel> _conversations = [];
  String _searchQuery = '';
  
  @override
  void initState() {
    super.initState();
    _loadHistory();
  }
  
  Future<void> _loadHistory() async {
    final storage = context.read<StorageService>();
    final history = await storage.getConversationHistory();
    setState(() => _conversations = history);
  }
  
  @override
  Widget build(BuildContext context) {
    final filtered = _filterConversations();
    
    return Scaffold(
      appBar: AppBar(
        title: const Text('CONVERSATION HISTORY'),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: _showSearch,
          ),
        ],
      ),
      body: filtered.isEmpty
          ? _buildEmptyState()
          : ListView.builder(
              itemCount: filtered.length,
              itemBuilder: (context, index) {
                return HistoryItem(
                  conversation: filtered[index],
                  onTap: () => _openConversation(filtered[index]),
                  onDelete: () => _deleteConversation(filtered[index]),
                );
              },
            ),
    );
  }
  
  List<ConversationModel> _filterConversations() {
    if (_searchQuery.isEmpty) return _conversations;
    return _conversations.where((c) {
      return c.title.toLowerCase().contains(_searchQuery.toLowerCase());
    }).toList();
  }
  
  // ... other methods
}
```

**Complexity:** ⭐⭐ (Low-Medium)
**Estimated Time:** 2-3 hours

---

### 4. chat-input.tsx (4.4KB) - Message Input

**React Features:**
- Text input with send button
- Voice input toggle
- Mic permission handling
- Enter to send

**Flutter Implementation:**

```dart
// lib/widgets/chat/chat_input.dart

class ChatInput extends StatefulWidget {
  final Function(String) onSend;
  final VoidCallback? onVoiceToggle;
  final bool voiceActive;
  
  const ChatInput({
    required this.onSend,
    this.onVoiceToggle,
    this.voiceActive = false,
  });
  
  @override
  State<ChatInput> createState() => _ChatInputState();
}

class _ChatInputState extends State<ChatInput> {
  final TextEditingController _controller = TextEditingController();
  bool _hasText = false;
  
  @override
  void initState() {
    super.initState();
    _controller.addListener(() {
      final hasText = _controller.text.isNotEmpty;
      if (hasText != _hasText) {
        setState(() => _hasText = hasText);
      }
    });
  }
  
  @override
  Widget build(BuildContext context) {
    return GlassContainer(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _controller,
              style: ZoyaTheme.bodyMedium,
              decoration: InputDecoration(
                hintText: 'Type a message...',
                hintStyle: TextStyle(color: ZoyaColors.textMuted),
                border: InputBorder.none,
              ),
              onSubmitted: _handleSend,
            ),
          ),
          const SizedBox(width: 8),
          
          // Voice toggle
          if (widget.onVoiceToggle != null)
            IconButton(
              icon: Icon(
                widget.voiceActive ? Icons.mic : Icons.mic_none,
                color: widget.voiceActive 
                    ? ZoyaColors.accent
                    : ZoyaColors.textMuted,
              ),
              onPressed: widget.onVoiceToggle,
            ),
          
          // Send button
          IconButton(
            icon: const Icon(Icons.send, color: ZoyaColors.accent),
            onPressed: _hasText ? () => _handleSend(_controller.text) : null,
          ),
        ],
      ),
    );
  }
  
  void _handleSend(String text) {
    if (text.trim().isEmpty) return;
    widget.onSend(text.trim());
    _controller.clear();
  }
  
  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}
```

**Complexity:** ⭐⭐ (Low-Medium)
**Estimated Time:** 1-2 hours

---

### 5. sidebar.tsx (6.7KB) - Navigation Sidebar

**React Features:**
- Collapsible sidebar
- Navigation items (Home, Dashboard, History, Settings)
- Active state highlighting
- Icons

**Flutter Implementation:**

```dart
// lib/widgets/navigation/app_sidebar.dart

class AppSidebar extends StatelessWidget {
  final bool collapsed;
  final VoidCallback onToggle;
  final String currentPage;
  final Function(String) onPageChange;
  
  const AppSidebar({
    super.key,
    required this.collapsed,
    required this.onToggle,
    required this.currentPage,
    required this.onPageChange,
  });
  
  @override
  Widget build(BuildContext context) {
    final width = collapsed ? 70.0 : 280.0;
    
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      width: width,
      color: ZoyaColors.sidebarBg,
      child: Column(
        children: [
          const SizedBox(height: 20),
          
          // Logo
          _buildLogo(),
          const SizedBox(height: 40),
          
          // Navigation items
          _NavItem(
            icon: Icons.home,
            label: 'Home',
            active: currentPage == 'home',
            collapsed: collapsed,
            onTap: () => onPageChange('home'),
          ),
          _NavItem(
            icon: Icons.dashboard,
            label: 'Dashboard',
            active: currentPage == 'dashboard',
            collapsed: collapsed,
            onTap: () => onPageChange('dashboard'),
          ),
          _NavItem(
            icon: Icons.history,
            label: 'History',
            active: currentPage == 'history',
            collapsed: collapsed,
            onTap: () => onPageChange('history'),
          ),
          
          const Spacer(),
          
          // Settings at bottom
          _NavItem(
            icon: Icons.settings,
            label: 'Settings',
            active: currentPage == 'settings',
            collapsed: collapsed,
            onTap: () => onPageChange('settings'),
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }
  
  Widget _buildLogo() {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: ZoyaColors.accent.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: ZoyaColors.accent.withValues(alpha: 0.3)),
      ),
      child: const Icon(
        Icons.terminal,
        color: ZoyaColors.accent,
        size: 20,
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool active;
  final bool collapsed;
  final VoidCallback onTap;
  
  const _NavItem({
    required this.icon,
    required this.label,
    required this.active,
    required this.collapsed,
    required this.onTap,
  });
  
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: active
              ? BoxDecoration(
                  color: ZoyaColors.accent.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: ZoyaColors.accent.withValues(alpha: 0.5),
                  ),
                )
              : null,
          child: Row(
            children: [
              Icon(
                icon,
                color: active ? ZoyaColors.accent : ZoyaColors.textMuted,
                size: 20,
              ),
              if (!collapsed) ...[
                const SizedBox(width: 16),
                Text(
                  label,
                  style: ZoyaTheme.bodyMedium.copyWith(
                    color: active ? ZoyaColors.accent : ZoyaColors.textMuted,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
```

**Complexity:** ⭐⭐ (Low-Medium)
**Estimated Time:** 2-3 hours

---

## Implementation Strategy

### Week 1: Foundation
- Set up all providers
- Configure routing
- Create base models
- Build common widgets

### Week 2: Core Features
- Complete WelcomeScreen
- Complete SessionScreen
- Complete Sidebar
- Complete Chat components

### Week 3: Advanced Features
- VideoTileGrid
- Settings screen (main effort)
- Audio/video device management

### Week 4: Additional Features
- Dashboard
- History
- Memory
- Polish & testing

---

## Priority Matrix

### Must Have (MVP)
1. ✅ WelcomeScreen
2. ✅ SessionScreen (basic layout)
3. ✅ CosmicOrb
4. ✅ Chat (transcript + input)
5. ⏳ Sidebar navigation
6. ⏳ Basic settings
7. ⏳ LiveKit integration

### Should Have
1. ⏳ VideoTileGrid
2. ⏳ Full settings
3. ⏳ Device selection
4. ⏳ History

### Nice to Have
1. ⏳ Dashboard
2. ⏳ Memory features
3. ⏳ Advanced animations
4. ⏳ Dark/light theme toggle

---

## Success Criteria

✅ **UI Parity**: Flutter app looks identical to React app
✅ **Feature Parity**: All major features working
✅ **Performance**: 60fps animations, smooth scrolling
✅ **Code Quality**: Clean architecture, maintainable
✅ **Platform Support**: Works on Android, iOS, Linux, macOS, Windows

---

**Total Estimated Time for Full Parity: 24-36 hours**

Use this document as your roadmap. Tackle components in priority order and test incrementally!
