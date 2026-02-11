# Flutter Implementation Guide & Code Templates
## Complete React → Flutter Conversion Roadmap

---

## Table of Contents
1. [Foundation Setup](#foundation-setup)
2. [State Management Templates](#state-management-templates)
3. [Router Configuration](#router-configuration)
4. [Service Layer Templates](#service-layer-templates)
5. [Component Conversion Templates](#component-conversion-templates)
6. [Implementation Checklist](#implementation-checklist)

---

## Foundation Setup

### Step 1: Update pubspec.yaml

```yaml
name: voice_assistant
description: Voice Assistant Agent Interface
version: 1.0.0+1

environment:
  sdk: '>=3.0.0 <4.0.0'

dependencies:
  flutter:
    sdk: flutter
  
  # State Management
  provider: ^6.1.1
  
  # Routing
  go_router: ^14.0.0
  
  # LiveKit
  livekit_client: ^2.0.0
  livekit_components: ^2.0.0
  
  # HTTP & API
  http: ^1.2.0
  dio: ^5.4.0
  
  # Storage
  shared_preferences: ^2.2.2
  hive: ^2.2.3
  hive_flutter: ^1.1.0
  
  # UI Components
  google_fonts: ^6.1.0
  font_awesome_flutter: ^10.7.0
  flutter_svg: ^2.0.9
  
  # Utilities
  intl: ^0.19.0
  uuid: ^4.3.3
  flutter_dotenv: ^5.1.0
  logging: ^1.2.0
  
  # Animations
  animations: ^2.0.11
  rive: ^0.13.0  # For complex animations
  
dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.1
  build_runner: ^2.4.8
  hive_generator: ^2.0.1

flutter:
  uses-material-design: true
  
  assets:
    - assets/images/
    - assets/icons/
    - assets/animations/
    - .env
  
  fonts:
    - family: Orbitron
      fonts:
        - asset: fonts/Orbitron-Regular.ttf
        - asset: fonts/Orbitron-Bold.ttf
          weight: 700
    - family: Roboto
      fonts:
        - asset: fonts/Roboto-Regular.ttf
        - asset: fonts/Roboto-Medium.ttf
          weight: 500
```

### Step 2: Create Folder Structure

Run these commands:

```bash
cd lib
mkdir -p core/{config,constants,utils,services}
mkdir -p theme
mkdir -p routes
mkdir -p models/{user,session,livekit,settings}
mkdir -p state/providers
mkdir -p widgets/{common,cosmic_orb,chat,navigation}
mkdir -p features/{welcome,session,dashboard,history,settings,auth}/{view,controller,widgets}
```

---

## State Management Templates

### Template 1: Base Provider Pattern

**File:** `lib/state/base_provider.dart`

```dart
import 'package:flutter/foundation.dart';
import 'package:logging/logging.dart';

/// Base class for all providers with common functionality
abstract class BaseProvider extends ChangeNotifier {
  final Logger _logger;
  bool _disposed = false;
  bool _loading = false;
  String? _error;

  BaseProvider(String loggerName) : _logger = Logger(loggerName);

  bool get loading => _loading;
  String? get error => _error;
  bool get hasError => _error != null;

  @protected
  void setLoading(bool value) {
    if (_disposed) return;
    _loading = value;
    notifyListeners();
  }

  @protected
  void setError(String? error) {
    if (_disposed) return;
    _error = error;
    if (error != null) {
      _logger.severe('Error: $error');
    }
    notifyListeners();
  }

  @protected
  void clearError() {
    setError(null);
  }

  @protected
  void log(String message, {Level level = Level.INFO}) {
    _logger.log(level, message);
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  @protected
  Future<T?> safeExecute<T>(Future<T> Function() action) async {
    try {
      setLoading(true);
      clearError();
      final result = await action();
      return result;
    } catch (e, stackTrace) {
      setError(e.toString());
      _logger.severe('Action failed', e, stackTrace);
      return null;
    } finally {
      setLoading(false);
    }
  }
}
```

### Template 2: Session Provider

**File:** `lib/state/providers/session_provider.dart`

```dart
import 'package:livekit_client/livekit_client.dart' as lk;
import '../base_provider.dart';
import '../../models/session/session_model.dart';
import '../../core/services/livekit_service.dart';

class SessionProvider extends BaseProvider {
  final LiveKitService _liveKitService;
  
  lk.Room? _room;
  lk.Session? _session;
  SessionModel? _sessionModel;
  ConnectionState _connectionState = ConnectionState.disconnected;
  
  SessionProvider(this._liveKitService) : super('SessionProvider');

  // Getters
  lk.Room? get room => _room;
  lk.Session? get session => _session;
  SessionModel? get sessionModel => _sessionModel;
  ConnectionState get connectionState => _connectionState;
  bool get isConnected => _connectionState == ConnectionState.connected;

  // Connect to session
  Future<bool> connect() async {
    return await safeExecute(() async {
      log('Connecting to session...');
      
      _room = lk.Room();
      _session = await _liveKitService.createSession(_room!);
      
      // Listen to connection state changes
      _session!.addListener(_onSessionChange);
      _room!.addListener(_onRoomChange);
      
      // Start the session
      await _session!.start();
      
      _sessionModel = SessionModel(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        startedAt: DateTime.now(),
      );
      
      _updateConnectionState(ConnectionState.connected);
      log('Session connected successfully');
      return true;
    }) ?? false;
  }

  // Disconnect from session
  Future<void> disconnect() async {
    await safeExecute(() async {
      log('Disconnecting from session...');
      
      _session?.removeListener(_onSessionChange);
      _room?.removeListener(_onRoomChange);
      
      await _session?.dispose();
      await _room?.dispose();
      
      _session = null;
      _room = null;
      _sessionModel = null;
      
      _updateConnectionState(ConnectionState.disconnected);
      log('Session disconnected');
    });
  }

  void _onSessionChange() {
    if (_session != null) {
      // Handle session state changes
      notifyListeners();
    }
  }

  void _onRoomChange() {
    if (_room != null) {
      _updateConnectionState(_room!.connectionState);
    }
  }

  void _updateConnectionState(ConnectionState state) {
    if (_connectionState != state) {
      _connectionState = state;
      log('Connection state changed: $state');
      notifyListeners();
    }
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}

enum ConnectionState {
  disconnected,
  connecting,
  connected,
  reconnecting,
  disconnecting,
}
```

### Template 3: Chat Provider

**File:** `lib/state/providers/chat_provider.dart`

```dart
import '../base_provider.dart';
import '../../models/session/message_model.dart';
import 'package:livekit_client/livekit_client.dart' as lk;

class ChatProvider extends BaseProvider {
  final List<MessageModel> _messages = [];
  bool _isTyping = false;

  ChatProvider() : super('ChatProvider');

  List<MessageModel> get messages => List.unmodifiable(_messages);
  bool get isTyping => _isTyping;

  void addMessage(MessageModel message) {
    _messages.add(message);
    log('Message added: ${message.content}');
    notifyListeners();
  }

  void addMessageFromLiveKit(lk.ReceivedMessage message) {
    final model = MessageModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      content: message.content.text,
      timestamp: DateTime.now(),
      isUser: message.content is lk.UserInput || message.content is lk.UserTranscript,
      isAgent: message.content is lk.AgentTranscript || message.content is lk.AgentOutput,
    );
    addMessage(model);
  }

  void setTyping(bool value) {
    if (_isTyping != value) {
      _isTyping = value;
      notifyListeners();
    }
  }

  void clearMessages() {
    _messages.clear();
    log('Messages cleared');
    notifyListeners();
  }

  void deleteMessage(String id) {
    _messages.removeWhere((msg) => msg.id == id);
    log('Message deleted: $id');
    notifyListeners();
  }

  @override
  void dispose() {
    _messages.clear();
    super.dispose();
  }
}
```

### Template 4: UI Provider

**File:** `lib/state/providers/ui_provider.dart`

```dart
import '../base_provider.dart';

class UIProvider extends BaseProvider {
  bool _sidebarCollapsed = false;
  String _currentModal = '';
  String _currentPage = 'home';

  UIProvider() : super('UIProvider');

  bool get sidebarCollapsed => _sidebarCollapsed;
  String get currentModal => _currentModal;
  String get currentPage => _currentPage;
  bool get hasActiveModal => _currentModal.isNotEmpty;

  void toggleSidebar() {
    _sidebarCollapsed = !_sidebarCollapsed;
    log('Sidebar ${_sidebarCollapsed ? 'collapsed' : 'expanded'}');
    notifyListeners();
  }

  void setSidebarCollapsed(bool value) {
    if (_sidebarCollapsed != value) {
      _sidebarCollapsed = value;
      notifyListeners();
    }
  }

  void showModal(String modalName) {
    _currentModal = modalName;
    log('Modal opened: $modalName');
    notifyListeners();
  }

  void hideModal() {
    if (_currentModal.isNotEmpty) {
      log('Modal closed: $_currentModal');
      _currentModal = '';
      notifyListeners();
    }
  }

  void setCurrentPage(String page) {
    if (_currentPage != page) {
      _currentPage = page;
      log('Page changed: $page');
      notifyListeners();
    }
  }
}
```

### Template 5: Settings Provider

**File:** `lib/state/providers/settings_provider.dart`

```dart
import '../base_provider.dart';
import '../../models/settings/app_settings_model.dart';
import '../../core/services/storage_service.dart';

class SettingsProvider extends BaseProvider {
  final StorageService _storageService;
  AppSettingsModel _settings = AppSettingsModel.defaults();

  SettingsProvider(this._storageService) : super('SettingsProvider') {
    _loadSettings();
  }

  AppSettingsModel get settings => _settings;

  Future<void> _loadSettings() async {
    await safeExecute(() async {
      final savedSettings = await _storageService.getSettings();
      if (savedSettings != null) {
        _settings = savedSettings;
        log('Settings loaded from storage');
      }
    });
  }

  Future<void> updateSettings(AppSettingsModel newSettings) async {
    await safeExecute(() async {
      _settings = newSettings;
      await _storageService.saveSettings(newSettings);
      log('Settings updated and saved');
      notifyListeners();
    });
  }

  Future<void> resetSettings() async {
    await safeExecute(() async {
      _settings = AppSettingsModel.defaults();
      await _storageService.saveSettings(_settings);
      log('Settings reset to defaults');
      notifyListeners();
    });
  }
}
```

---

## Router Configuration

### Template 6: Go Router Setup

**File:** `lib/routes/app_router.dart`

```dart
import 'package:go_router/go_router.dart';
import 'package:flutter/material.dart';
import '../features/welcome/view/welcome_screen.dart';
import '../features/session/view/session_screen.dart';
import '../features/dashboard/view/dashboard_screen.dart';
import '../features/history/view/history_screen.dart';
import '../features/settings/view/settings_screen.dart';
import '../features/auth/view/login_screen.dart';
import 'route_guards.dart';

class AppRouter {
  static final GoRouter router = GoRouter(
    initialLocation: AppRoutes.welcome,
    routes: [
      GoRoute(
        path: AppRoutes.welcome,
        name: 'welcome',
        pageBuilder: (context, state) => MaterialPage(
          key: state.pageKey,
          child: const WelcomeScreen(),
        ),
      ),
      GoRoute(
        path: AppRoutes.session,
        name: 'session',
        pageBuilder: (context, state) => MaterialPage(
          key: state.pageKey,
          child: const SessionScreen(),
        ),
      ),
      GoRoute(
        path: AppRoutes.dashboard,
        name: 'dashboard',
        pageBuilder: (context, state) => MaterialPage(
          key: state.pageKey,
          child: const DashboardScreen(),
        ),
      ),
      GoRoute(
        path: AppRoutes.history,
        name: 'history',
        pageBuilder: (context, state) => MaterialPage(
          key: state.pageKey,
          child: const HistoryScreen(),
        ),
      ),
      GoRoute(
        path: AppRoutes.settings,
        name: 'settings',
        pageBuilder: (context, state) => MaterialPage(
          key: state.pageKey,
          child: const SettingsScreen(),
        ),
      ),
      GoRoute(
        path: AppRoutes.login,
        name: 'login',
        pageBuilder: (context, state) => MaterialPage(
          key: state.pageKey,
          child: const LoginScreen(),
        ),
      ),
    ],
    redirect: (context, state) {
      // Add auth guards here
      return RouteGuards.checkAuth(context, state);
    },
    errorBuilder: (context, state) => Scaffold(
      body: Center(
        child: Text('Page not found: ${state.uri}'),
      ),
    ),
  );
}

class AppRoutes {
  static const welcome = '/';
  static const session = '/session';
  static const dashboard = '/dashboard';
  static const history = '/history';
  static const settings = '/settings';
  static const login = '/auth/login';
}
```

---

## Service Layer Templates

### Template 7: LiveKit Service

**File:** `lib/core/services/livekit_service.dart`

```dart
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:logging/logging.dart';

class LiveKitService {
  final Logger _logger = Logger('LiveKitService');

  lk.Session createSession(lk.Room room) {
    final sandboxId = dotenv.env['LIVEKIT_SANDBOX_ID']?.replaceAll('"', '');
    
    if (sandboxId == null || sandboxId.isEmpty) {
      _logger.warning('No sandbox ID configured');
      // Return dummy session for development
      return lk.Session.fromFixedTokenSource(
        lk.LiteralTokenSource(
          serverUrl: 'wss://demo.livekit.cloud',
          participantToken: 'development-token',
        ),
        options: lk.SessionOptions(room: room),
      );
    }

    return lk.Session.fromConfigurableTokenSource(
      lk.SandboxTokenSource(sandboxId: sandboxId).cached(),
      options: lk.SessionOptions(room: room),
    );
  }

  Future<void> connect(lk.Session session) async {
    try {
      await session.start();
      _logger.info('Session started successfully');
    } catch (e) {
      _logger.severe('Failed to start session: $e');
      rethrow;
    }
  }

  Future<void> disconnect(lk.Session session) async {
    try {
      await session.dispose();
      _logger.info('Session disposed');
    } catch (e) {
      _logger.severe('Error disposing session: $e');
    }
  }
}
```

### Template 8: Storage Service

**File:** `lib/core/services/storage_service.dart`

```dart
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../../models/settings/app_settings_model.dart';

class StorageService {
  static const _settingsKey = 'app_settings';
  static const _historyKey = 'conversation_history';

  Future<AppSettingsModel?> getSettings() async {
    final prefs = await SharedPreferences.getInstance();
    final json = prefs.getString(_settingsKey);
    if (json != null) {
      return AppSettingsModel.fromJson(jsonDecode(json));
    }
    return null;
  }

  Future<void> saveSettings(AppSettingsModel settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_settingsKey, jsonEncode(settings.toJson()));
  }

  Future<List<String>> getHistory() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getStringList(_historyKey) ?? [];
  }

  Future<void> saveHistory(List<String> history) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_historyKey, history);
  }

  Future<void> clearAll() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
  }
}
```

---

## Component Conversion Templates

### Template 9: Welcome Screen

**File:** `lib/features/welcome/view/welcome_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:go_router/go_router.dart';
import '../../../theme/zoya_theme.dart';
import '../../../widgets/common/glass_container.dart';
import '../../../widgets/common/neon_button.dart';
import '../../../state/providers/session_provider.dart';
import '../../../routes/app_router.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          color: ZoyaColors.mainBg,
          gradient: ZoyaTheme.bgGradient,
        ),
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Logo
              _buildLogo(),
              const SizedBox(height: 40),
              
              // Title
              _buildTitle(),
              const SizedBox(height: 16),
              
              // Subtitle
              _buildSubtitle(),
              const SizedBox(height: 60),
              
              // Control Panel
              _buildControlPanel(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildLogo() {
    return Container(
      width: 120,
      height: 120,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: ZoyaColors.accent.withValues(alpha: 0.05),
        border: Border.all(
          color: ZoyaColors.accent.withValues(alpha: 0.5),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: ZoyaColors.accentGlow,
            blurRadius: 40,
            spreadRadius: -10,
          ),
        ],
      ),
      child: const Icon(
        Icons.terminal,
        size: 60,
        color: ZoyaColors.accent,
      ),
    );
  }

  Widget _buildTitle() {
    return Text(
      'ZOYA AGENT',
      style: ZoyaTheme.displayLarge.copyWith(
        fontSize: 32,
        letterSpacing: 4,
        shadows: [
          Shadow(
            color: ZoyaColors.accent,
            blurRadius: 20,
          ),
        ],
      ),
    );
  }

  Widget _buildSubtitle() {
    return Text(
      'Voice Interface System v2.0',
      style: ZoyaTheme.bodyMedium.copyWith(
        color: ZoyaColors.textMuted,
        letterSpacing: 1.5,
      ),
    );
  }

  Widget _buildControlPanel(BuildContext context) {
    return GlassContainer(
      width: 400,
      padding: const EdgeInsets.all(40),
      child: Column(
        children: [
          _buildStatusIndicator(context),
          const SizedBox(height: 30),
          _buildConnectButton(context),
        ],
      ),
    );
  }

  Widget _buildStatusIndicator(BuildContext context) {
    return Consumer<SessionProvider>(
      builder: (context, session, _) {
        final isReady = !session.loading;
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: isReady ? ZoyaColors.success : ZoyaColors.textMuted,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              isReady ? 'SYSTEM READY' : 'INITIALIZING...',
              style: ZoyaTheme.displaySmall.copyWith(
                fontSize: 12,
                color: isReady ? ZoyaColors.success : ZoyaColors.textMuted,
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildConnectButton(BuildContext context) {
    return Consumer<SessionProvider>(
      builder: (context, session, _) {
        return NeonButton(
          text: session.loading ? 'CONNECTING...' : 'INITIATE LINK',
          isLoading: session.loading,
          onPressed: () => _handleConnect(context),
        );
      },
    );
  }

  Future<void> _handleConnect(BuildContext context) async {
    final session = context.read<SessionProvider>();
    final success = await session.connect();
    
    if (success && context.mounted) {
      context.go(AppRoutes.session);
    } else if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Failed to connect')),
      );
    }
  }
}
```

---

**(Continued in IMPLEMENTATION_GUIDE_PART2.md due to length...)**
