# Flutter Implementation Guide - Part 2
## Component Conversion Templates (Continued)

---

## Advanced Component Templates

### Template 10: Session Screen (Main Layout)

**File:** `lib/features/session/view/session_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../theme/zoya_theme.dart';
import '../../../widgets/navigation/app_sidebar.dart';
import '../../../widgets/cosmic_orb/cosmic_orb.dart';
import '../../../widgets/chat/chat_transcript.dart';
import '../../../widgets/common/glass_container.dart';
import '../../../state/providers/session_provider.dart';
import '../../../state/providers/ui_provider.dart';
import '../widgets/control_bar.dart';

class SessionScreen extends StatelessWidget {
  const SessionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          color: ZoyaColors.mainBg,
          gradient: ZoyaTheme.bgGradient,
        ),
        child: Row(
          children: [
            // Sidebar
            Consumer<UIProvider>(
              builder: (context, ui, _) => AppSidebar(
                collapsed: ui.sidebarCollapsed,
                onToggle: ui.toggleSidebar,
                currentPage: ui.currentPage,
                onPageChange: ui.setCurrentPage,
              ),
            ),
            
            // Main Content
            Expanded(
              child: Stack(
                children: [
                  // Cosmic Orb Visualizer
                  _buildVisualizer(),
                  
                  // Chat Panel
                  _buildChatPanel(),
                  
                  // Control Bar
                  _buildControlBar(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildVisualizer() {
    return Center(
      child: Consumer<SessionProvider>(
        builder: (context, session, _) {
          OrbState orbState = OrbState.idle;
          
          // Map session state to orb state
          if (session.isConnected && session.session != null) {
            final messages = session.session!.messages;
            if (messages.isNotEmpty) {
              final lastMsg = messages.last;
              if (lastMsg.content is lk.AgentTranscript) {
                orbState = OrbState.speaking;
              } else if (lastMsg.content is lk.UserTranscript) {
                orbState = OrbState.listening;
              }
            }
          }
          
          return CosmicOrb(state: orbState);
        },
      ),
    );
  }

  Widget _buildChatPanel() {
    return Positioned(
      right: 20,
      top: 20,
      bottom: 100,
      width: 350,
      child: GlassContainer(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // Header
            Row(
              children: [
                Text(
                  'TRANSCRIPT',
                  style: ZoyaTheme.displaySmall.copyWith(
                    fontSize: 12,
                    letterSpacing: 2,
                  ),
                ),
                const Spacer(),
                const Icon(
                  Icons.history,
                  color: ZoyaColors.textMuted,
                  size: 16,
                ),
              ],
            ),
            const Divider(color: Colors.white10),
            
            // Chat messages
            const Expanded(
              child: ChatTranscript(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildControlBar() {
    return const Positioned(
      bottom: 30,
      left: 0,
      right: 0,
      child: Center(
        child: ControlBar(),
      ),
    );
  }
}
```

### Template 11: Cosmic Orb (Complete Implementation)

**File:** `lib/widgets/cosmic_orb/cosmic_orb.dart`

```dart
import 'dart:math';
import 'package:flutter/material.dart';
import 'orb_painter.dart';
import '../../theme/zoya_theme.dart';

enum OrbState { idle, listening, thinking, speaking }

class CosmicOrb extends StatefulWidget {
  final OrbState state;
  final VoidCallback? onTap;

  const CosmicOrb({
    super.key,
    this.state = OrbState.idle,
    this.onTap,
  });

  @override
  State<CosmicOrb> createState() => _CosmicOrbState();
}

class _CosmicOrbState extends State<CosmicOrb>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  final List<OrbParticle> _particles = [];
  final Random _rng = Random();

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(minutes: 5),
    )..repeat();

    // Initialize 60 particles
    for (int i = 0; i < 60; i++) {
      _particles.add(OrbParticle(
        angle: _rng.nextDouble() * 2 * pi,
        radius: 40 + _rng.nextDouble() * 80,
        speed: 0.2 + _rng.nextDouble() * 0.8,
        size: 1 + _rng.nextDouble() * 2,
        opacity: 0.1 + _rng.nextDouble() * 0.7,
      ));
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Color get _glowColor {
    switch (widget.state) {
      case OrbState.listening:
        return ZoyaColors.secondaryAccent;
      case OrbState.thinking:
        return Colors.white;
      case OrbState.speaking:
        return ZoyaColors.accent;
      case OrbState.idle:
        return ZoyaColors.accent.withValues(alpha: 0.5);
    }
  }

  String get _statusText {
    switch (widget.state) {
      case OrbState.listening:
        return 'LISTENING...';
      case OrbState.thinking:
        return 'THINKING...';
      case OrbState.speaking:
        return 'SPEAKING';
      case OrbState.idle:
        return 'AWAITING INPUT';
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 300,
            height: 300,
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Animated particles
                AnimatedBuilder(
                  animation: _controller,
                  builder: (ctx, child) {
                    return CustomPaint(
                      size: const Size(300, 300),
                      painter: OrbParticlePainter(
                        particles: _particles,
                        rotation: _controller.value * 2 * pi,
                        color: ZoyaColors.accent,
                      ),
                    );
                  },
                ),
                
                // Core orb
                _buildCoreOrb(),
              ],
            ),
          ),
          const SizedBox(height: 20),
          
          // Status text
          Text(
            _statusText,
            style: ZoyaTheme.displaySmall.copyWith(
              fontSize: 14,
              letterSpacing: 2,
              color: ZoyaColors.textMuted,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCoreOrb() {
    return TweenAnimationBuilder<double>(
      tween: Tween(
        begin: 1.0,
        end: widget.state == OrbState.speaking ? 1.2 : 1.0,
      ),
      duration: const Duration(milliseconds: 400),
      builder: (ctx, scale, child) {
        return Transform.scale(
          scale: scale,
          child: Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _glowColor.withValues(alpha: 0.2),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.8),
                width: 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: _glowColor,
                  blurRadius: widget.state == OrbState.speaking ? 50 : 30,
                  spreadRadius: 5,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class OrbParticle {
  double angle;
  double radius;
  double speed;
  double size;
  double opacity;

  OrbParticle({
    required this.angle,
    required this.radius,
    required this.speed,
    required this.size,
    required this.opacity,
  });
}
```

**File:** `lib/widgets/cosmic_orb/orb_painter.dart`

```dart
import 'dart:math';
import 'package:flutter/material.dart';
import 'cosmic_orb.dart';

class OrbParticlePainter extends CustomPainter {
  final List<OrbParticle> particles;
  final double rotation;
  final Color color;

  OrbParticlePainter({
    required this.particles,
    required this.rotation,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final paint = Paint()
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.fill;

    for (var particle in particles) {
      final currentAngle = particle.angle + (rotation * particle.speed);
      final x = center.dx + cos(currentAngle) * particle.radius;
      final y = center.dy + sin(currentAngle) * particle.radius;

      paint.color = color.withValues(alpha: particle.opacity);
      canvas.drawCircle(Offset(x, y), particle.size, paint);
    }
  }

  @override
  bool shouldRepaint(covariant OrbParticlePainter oldDelegate) => true;
}
```

### Template 12: Chat Components

**File:** `lib/widgets/chat/chat_transcript.dart`

```dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../state/providers/chat_provider.dart';
import '../../theme/zoya_theme.dart';
import 'message_bubble.dart';

class ChatTranscript extends StatelessWidget {
  const ChatTranscript({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ChatProvider>(
      builder: (context, chat, _) {
        if (chat.messages.isEmpty) {
          return Center(
            child: Text(
              'No messages yet...',
              style: ZoyaTheme.bodyMedium.copyWith(
                color: ZoyaColors.textMuted,
                fontStyle: FontStyle.italic,
              ),
            ),
          );
        }

        return ListView.builder(
          padding: const EdgeInsets.symmetric(vertical: 8),
          itemCount: chat.messages.length,
          itemBuilder: (context, index) {
            final message = chat.messages[index];
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: MessageBubble(message: message),
            );
          },
        );
      },
    );
  }
}
```

**File:** `lib/widgets/chat/message_bubble.dart`

```dart
import 'package:flutter/material.dart';
import '../../models/session/message_model.dart';
import '../../theme/zoya_theme.dart';

class MessageBubble extends StatelessWidget {
  final MessageModel message;

  const MessageBubble({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: message.isUser
          ? Alignment.centerRight
          : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 4),
        padding: const EdgeInsets.all(12),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        decoration: BoxDecoration(
          color: message.isUser
              ? ZoyaColors.accent.withValues(alpha: 0.1)
              : Colors.white.withValues(alpha: 0.05),
          border: Border.all(
            color: message.isUser
                ? ZoyaColors.accent.withValues(alpha: 0.3)
                : Colors.white10,
          ),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(12),
            topRight: const Radius.circular(12),
            bottomLeft: Radius.circular(message.isUser ? 12 : 2),
            bottomRight: Radius.circular(message.isUser ? 2 : 12),
          ),
        ),
        child: Text(
          message.content,
          style: ZoyaTheme.bodyMedium.copyWith(
            color: message.isUser ? ZoyaColors.accent : ZoyaColors.textMain,
            fontSize: 13,
          ),
        ),
      ),
    );
  }
}
```

### Template 13: Common Widgets

**File:** `lib/widgets/common/neon_button.dart`

```dart
import 'package:flutter/material.dart';
import '../../theme/zoya_theme.dart';

class NeonButton extends StatelessWidget {
  final String text;
  final VoidCallback onPressed;
  final bool isLoading;
  final bool isSecondary;
  final double? width;

  const NeonButton({
    super.key,
    required this.text,
    required this.onPressed,
    this.isLoading = false,
    this.isSecondary = false,
    this.width,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: isLoading ? null : onPressed,
      child: Container(
        width: width,
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 32),
        decoration: BoxDecoration(
          color: isSecondary
              ? Colors.transparent
              : ZoyaColors.accent,
          border: isSecondary
              ? Border.all(color: ZoyaColors.accent)
              : null,
          borderRadius: BorderRadius.circular(30),
          boxShadow: isSecondary
              ? null
              : [
                  BoxShadow(
                    color: ZoyaColors.accentGlow,
                    blurRadius: 20,
                  ),
                ],
        ),
        child: isLoading
            ? const SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                  color: Colors.black,
                  strokeWidth: 2,
                ),
              )
            : Text(
                text.toUpperCase(),
                textAlign: TextAlign.center,
                style: ZoyaTheme.displaySmall.copyWith(
                  color: isSecondary ? ZoyaColors.accent : Colors.black,
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.5,
                ),
              ),
      ),
    );
  }
}
```

---

## Model Templates

### Template 14: Message Model

**File:** `lib/models/session/message_model.dart`

```dart
class MessageModel {
  final String id;
  final String content;
  final DateTime timestamp;
  final bool isUser;
  final bool isAgent;
  final String? metadata;

  MessageModel({
    required this.id,
    required this.content,
    required this.timestamp,
    required this.isUser,
    required this.isAgent,
    this.metadata,
  });

  factory MessageModel.fromJson(Map<String, dynamic> json) {
    return MessageModel(
      id: json['id'],
      content: json['content'],
      timestamp: DateTime.parse(json['timestamp']),
      isUser: json['isUser'] ?? false,
      isAgent: json['isAgent'] ?? false,
      metadata: json['metadata'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'content': content,
      'timestamp': timestamp.toIso8601String(),
      'isUser': isUser,
      'isAgent': isAgent,
      'metadata': metadata,
    };
  }
}
```

### Template 15: Settings Model

**File:** `lib/models/settings/app_settings_model.dart`

```dart
class AppSettingsModel {
  final String theme;
  final bool notificationsEnabled;
  final double volume;
  final String? selectedMicrophone;
  final String? selectedSpeaker;
  final String? selectedCamera;
  final bool autoConnect;
  final Map<String, dynamic>? advancedSettings;

  AppSettingsModel({
    required this.theme,
    required this.notificationsEnabled,
    required this.volume,
    this.selectedMicrophone,
    this.selectedSpeaker,
    this.selectedCamera,
    required this.autoConnect,
    this.advancedSettings,
  });

  factory AppSettingsModel.defaults() {
    return AppSettingsModel(
      theme: 'zoya',
      notificationsEnabled: true,
      volume: 0.8,
      autoConnect: false,
    );
  }

  factory AppSettingsModel.fromJson(Map<String, dynamic> json) {
    return AppSettingsModel(
      theme: json['theme'] ?? 'zoya',
      notificationsEnabled: json['notificationsEnabled'] ?? true,
      volume: (json['volume'] ?? 0.8).toDouble(),
      selectedMicrophone: json['selectedMicrophone'],
      selectedSpeaker: json['selectedSpeaker'],
      selectedCamera: json['selectedCamera'],
      autoConnect: json['autoConnect'] ?? false,
      advancedSettings: json['advancedSettings'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'theme': theme,
      'notificationsEnabled': notificationsEnabled,
      'volume': volume,
      'selectedMicrophone': selectedMicrophone,
      'selectedSpeaker': selectedSpeaker,
      'selectedCamera': selectedCamera,
      'autoConnect': autoConnect,
      'advancedSettings': advancedSettings,
    };
  }

  AppSettingsModel copyWith({
    String? theme,
    bool? notificationsEnabled,
    double? volume,
    String? selectedMicrophone,
    String? selectedSpeaker,
    String? selectedCamera,
    bool? autoConnect,
    Map<String, dynamic>? advancedSettings,
  }) {
    return AppSettingsModel(
      theme: theme ?? this.theme,
      notificationsEnabled: notificationsEnabled ?? this.notificationsEnabled,
      volume: volume ?? this.volume,
      selectedMicrophone: selectedMicrophone ?? this.selectedMicrophone,
      selectedSpeaker: selectedSpeaker ?? this.selectedSpeaker,
      selectedCamera: selectedCamera ?? this.selectedCamera,
      autoConnect: autoConnect ?? this.autoConnect,
      advancedSettings: advancedSettings ?? this.advancedSettings,
    );
  }
}
```

---

## Main App Setup

### Template 16: Updated main.dart

**File:** `lib/main.dart`

```dart
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:provider/provider.dart';
import 'package:logging/logging.dart';

import 'core/services/livekit_service.dart';
import 'core/services/storage_service.dart';
import 'managers/agent_process_manager.dart';
import 'state/providers/session_provider.dart';
import 'state/providers/chat_provider.dart';
import 'state/providers/ui_provider.dart';
import 'state/providers/settings_provider.dart';
import 'theme/zoya_theme.dart';
import 'routes/app_router.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Initialize logging
  Logger.root.level = Level.INFO;
  Logger.root.onRecord.listen((record) {
    debugPrint('${record.level.name}: ${record.time}: ${record.message}');
  });

  // Load environment
  await dotenv.load(fileName: '.env');

  // Initialize services
  final liveKitService = LiveKitService();
  final storageService = StorageService();

  // Auto-start Python agent (desktop only)
  if (!kIsWeb && (Platform.isLinux || Platform.isMacOS || Platform.isWindows)) {
    final agentManager = AgentProcessManager();
    final started = await agentManager.startAgent();
    if (started) {
      await Future.delayed(const Duration(seconds: 2));
    }
  }

  runApp(VoiceAssistantApp(
    liveKitService: liveKitService,
    storageService: storageService,
  ));
}

class VoiceAssistantApp extends StatelessWidget {
  final LiveKitService liveKitService;
  final StorageService storageService;

  const VoiceAssistantApp({
    super.key,
    required this.liveKitService,
    required this.storageService,
  });

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => SessionProvider(liveKitService),
        ),
        ChangeNotifierProvider(
          create: (_) => ChatProvider(),
        ),
        ChangeNotifierProvider(
          create: (_) => UIProvider(),
        ),
        ChangeNotifierProvider(
          create: (_) => SettingsProvider(storageService),
        ),
      ],
      child: MaterialApp.router(
        title: 'Zoya Agent',
        debugShowCheckedModeBanner: false,
        theme: ZoyaTheme.themeData,
        routerConfig: AppRouter.router,
      ),
    );
  }
}
```

---

## Implementation Checklist

### Phase 1: Foundation ✅
- [x] Update pubspec.yaml with all dependencies
- [x] Create folder structure
- [ ] Set up logging
- [ ] Configure environment variables

### Phase 2: State Management
- [ ] Implement BaseProvider
- [ ] Create SessionProvider
- [ ] Create ChatProvider
- [ ] Create UIProvider
- [ ] Create SettingsProvider
- [ ] Test provider interactions

### Phase 3: Services
- [ ] Implement LiveKitService
- [ ] Implement StorageService
- [ ] Implement AgentProcessManager (already done ✅)
- [ ] Add error handling

### Phase 4: Routing
- [ ] Set up GoRouter
- [ ] Define all routes
- [ ] Add route guards
- [ ] Test navigation

### Phase 5: Models
- [ ] Create MessageModel
- [ ] Create SessionModel
- [ ] Create SettingsModel
- [ ] Create UserModel
- [ ] Add JSON serialization

### Phase 6: Core Widgets
- [ ] Implement NeonButton (template provided ✅)
- [ ] Implement GlassContainer (already done ✅)
- [ ] Create LoadingIndicator
- [ ] Create CustomScrollbar

### Phase 7: Feature Widgets
- [ ] Implement CosmicOrb (template provided ✅)
- [ ] Create ChatTranscript (template provided ✅)
- [ ] Create MessageBubble (template provided ✅)
- [ ] Create ChatInput
- [ ] Create AppSidebar (partial ✅)
- [ ] Create ControlBar

### Phase 8: Screens
- [ ] WelcomeScreen (template provided ✅)
- [ ] SessionScreen (template provided ✅)
- [ ] DashboardScreen
- [ ] HistoryScreen
- [ ] SettingsScreen (complex - 58KB in React!)

### Phase 9: Testing & Polish
- [ ] Test all routes
- [ ] Test state management
- [ ] Test LiveKit integration
- [ ] Fix Android/iOS compatibility
- [ ] Optimize animations
- [ ] Add error boundaries
- [ ] Performance testing

---

## Quick Start Commands

```bash
# 1. Install dependencies
flutter pub get

# 2. Run code generation (if using build_runner)
flutter pub run build_runner build

# 3. Run on Linux
flutter run -d linux

# 4. Run on Android
flutter run -d <device_id>

# 5. Build for release
flutter build linux
flutter build apk
flutter build ios
```

---

## Next Steps

1. **Copy templates into your project** - Use the templates above as starting points
2. **Customize as needed** - Adapt to your specific requirements
3. **Test incrementally** - Test each component as you build it
4. **Refer to React app** - Use the React code as reference for behavior
5. **Iterate** - Refine based on testing

**Estimated Timeline:**
- Foundation: 2-4 hours
- State & Services: 3-5 hours
- Core Components: 4-6 hours
- All Screens: 6-10 hours
- Testing & Polish: 3-5 hours

**Total: 18-30 hours for complete parity**

---

**IMPORTANT NOTE:** This guide provides production-ready templates. The actual React app has additional complexity (especially in settings - 58KB file!). Use these as foundations and expand as needed.

Good luck with the conversion! 🚀
