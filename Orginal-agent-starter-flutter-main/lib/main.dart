import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:provider/provider.dart';
import 'package:logging/logging.dart';

import 'core/services/livekit_service.dart';
import 'core/services/agent_process_manager.dart';
import 'core/services/supabase_service.dart';
import 'core/services/settings_service.dart';
import 'core/services/backend_sync_service.dart';
import 'core/services/search_cue_service.dart';
import 'core/services/storage_service.dart';

import 'state/providers/session_provider.dart';
import 'state/providers/chat_provider.dart';
import 'state/providers/conversation_history_provider.dart';
import 'state/providers/settings_provider.dart';
import 'state/providers/auth_provider.dart';
import 'state/controllers/app_init_controller.dart';
import 'state/controllers/agent_activity_controller.dart';
import 'state/controllers/composer_controller.dart';
import 'state/controllers/conversation_controller.dart';
import 'state/controllers/orb_controller.dart';
import 'state/controllers/workspace_controller.dart';
import 'state/controllers/overlay_controller.dart';
import 'ui/theme/app_theme.dart';
import 'widgets/overlays/global_overlay_host.dart';
import 'app.dart';

bool _isTruthyEnv(String? raw, {bool defaultValue = false}) {
  if (raw == null) return defaultValue;
  final normalized = raw.trim().toLowerCase();
  return normalized == '1' || normalized == 'true' || normalized == 'yes' || normalized == 'on';
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize logging
  Logger.root.level = Level.INFO;
  Logger.root.onRecord.listen((record) {
    debugPrint('${record.level.name}: ${record.time}: ${record.message}');
  });

  // Load environment
  try {
    await dotenv.load(fileName: '.env');
  } catch (e) {
    debugPrint('Warning: .env file not found or could not be loaded');
  }

  // Initialize Core Services
  final supabaseService = SupabaseService();
  await supabaseService.initialize();

  final settingsService = SettingsService(supabaseService);
  final backendSyncService = BackendSyncService();
  final liveKitService = LiveKitService();
  final storageService = StorageService();

  // Default to the externally managed backend in desktop dev. Local spawn remains
  // available as an explicit opt-in for self-contained runs.
  final autoStartLocalAgent = _isTruthyEnv(
    dotenv.env['FLUTTER_AUTO_START_AGENT'],
    defaultValue: false,
  );
  if (!kIsWeb && (Platform.isLinux || Platform.isMacOS || Platform.isWindows) && autoStartLocalAgent) {
    final agentManager = AgentProcessManager();
    final started = await agentManager.startAgent();
    if (started) {
      await Future.delayed(const Duration(seconds: 2));
    }
  } else if (!kIsWeb && (Platform.isLinux || Platform.isMacOS || Platform.isWindows)) {
    debugPrint('Desktop app using external backend on :5050 (FLUTTER_AUTO_START_AGENT=0).');
  }

  runApp(
    MultiProvider(
      providers: [
        Provider<StorageService>.value(value: storageService),
        Provider<SearchCueService>(
          create: (_) {
            final service = SearchCueService();
            unawaited(service.preload().catchError((error) {
              debugPrint('Audio cue preload failed: $error');
            }));
            return service;
          },
          dispose: (_, service) => unawaited(service.dispose()),
        ),
        ChangeNotifierProvider(create: (_) => AuthProvider(supabaseService)),
        ChangeNotifierProxyProvider<AuthProvider, SettingsProvider>(
          create: (context) => SettingsProvider(
            settingsService,
            Provider.of<AuthProvider>(context, listen: false),
            backendSyncService,
          ),
          update: (context, auth, settings) => settings!..updateAuth(auth),
        ),
        ChangeNotifierProvider(create: (_) => OverlayController()),
        ChangeNotifierProxyProvider3<OverlayController, SettingsProvider, SearchCueService, ChatProvider>(
          create: (_) => ChatProvider(),
          update: (_, overlay, settings, searchCue, chat) {
            final provider = chat ?? ChatProvider();
            provider.bindOverlayController(overlay);
            provider.bindSearchCueService(searchCue);
            provider.bindSoundEffectsPreference(settings.soundEffectsEnabled);
            return provider;
          },
        ),
        ChangeNotifierProvider(create: (_) => ComposerController()),
        ChangeNotifierProvider(create: (_) => OrbController()),
        ChangeNotifierProxyProvider2<ChatProvider, OverlayController, SessionProvider>(
          create: (_) => SessionProvider(liveKitService),
          update: (_, chat, overlay, session) {
            final provider = session ?? SessionProvider(liveKitService);
            provider.bindChatProvider(chat);
            provider.bindOverlayController(overlay);
            return provider;
          },
        ),
        ChangeNotifierProxyProvider2<SessionProvider, OrbController, AgentActivityController>(
          create: (context) => AgentActivityController(
            agentEvents: Provider.of<SessionProvider>(context, listen: false).agentEvents,
          ),
          update: (_, session, __, controller) {
            final activityController = controller ?? AgentActivityController(agentEvents: session.agentEvents);
            activityController.bind(session.agentEvents);
            return activityController;
          },
        ),
        ChangeNotifierProxyProvider3<StorageService, ChatProvider, SessionProvider, ConversationHistoryProvider>(
          create: (context) => ConversationHistoryProvider(
            Provider.of<StorageService>(context, listen: false),
            Provider.of<ChatProvider>(context, listen: false),
            Provider.of<SessionProvider>(context, listen: false),
          ),
          update: (context, storage, chat, session, provider) {
            final historyProvider = provider ??
                ConversationHistoryProvider(
                  storage,
                  chat,
                  session,
                );
            historyProvider.updateDependencies(storage, chat, session);
            return historyProvider;
          },
        ),
        ChangeNotifierProxyProvider2<ChatProvider, ConversationHistoryProvider, ConversationController>(
          create: (_) => ConversationController(),
          update: (_, chat, history, controller) {
            final conversationController = controller ?? ConversationController();
            conversationController.bind(chat, history);
            return conversationController;
          },
        ),
        ChangeNotifierProvider(create: (_) => WorkspaceController()),
        ChangeNotifierProvider(create: (_) => AppInitController()),
      ],
      child: const VoiceAssistantApp(),
    ),
  );
}

class VoiceAssistantApp extends StatelessWidget {
  const VoiceAssistantApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Maya Agent',
      debugShowCheckedModeBanner: false,
      theme: ZoyaTheme.themeData,
      home: const GlobalOverlayHost(child: App()),
    );
  }
}
