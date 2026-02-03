import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:provider/provider.dart';
import 'package:logging/logging.dart';

import 'app.dart';
import 'managers/agent_process_manager.dart';
import 'core/services/livekit_service.dart';
import 'core/services/storage_service.dart';
import 'state/providers/session_provider.dart';
import 'state/providers/chat_provider.dart';
import 'state/providers/ui_provider.dart';
import 'state/providers/auth_provider.dart';
import 'state/providers/settings_provider.dart';
import 'core/services/supabase_service.dart';
import 'core/services/settings_service.dart';
import 'core/services/backend_sync_service.dart';
import 'state/controllers/orb_controller.dart';
import 'state/controllers/app_init_controller.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Configure logging
  Logger.root.level = Level.INFO;
  Logger.root.onRecord.listen((record) {
    debugPrint('${record.level.name}: ${record.time}: ${record.message}');
  });

  // Load environment variables
  await dotenv.load(fileName: '.env');

  // Initialize services
  final supabaseService = SupabaseService();
  await supabaseService.initialize();
  
  final settingsService = SettingsService(supabaseService);
  final liveKitService = LiveKitService();
  final storageService = StorageService();
  final backendSyncService = BackendSyncService();

  // Auto-start Python agent on desktop platforms (DISABLED FOR DEBUGGING)
  /* if (!kIsWeb && (Platform.isLinux || Platform.isMacOS || Platform.isWindows)) {
    debugPrint('[Main] Starting Python agent backend...');
    final agentManager = AgentProcessManager();
    final started = await agentManager.startAgent();
    
    if (started) {
      debugPrint('[Main] Agent backend started successfully.');
      await Future.delayed(const Duration(seconds: 2));
    } else {
      debugPrint('[Main] WARNING: Failed to start agent backend.');
    }
  } */

  runApp(
    VoiceAssistantApp(
      liveKitService: liveKitService,
      storageService: storageService,
      supabaseService: supabaseService,
      settingsService: settingsService,
      backendSyncService: backendSyncService,
    ),
  );
}

class VoiceAssistantApp extends StatelessWidget {
  final LiveKitService liveKitService;
  final StorageService storageService;
  final SupabaseService supabaseService;
  final SettingsService settingsService;
  final BackendSyncService backendSyncService;

  const VoiceAssistantApp({
    super.key,
    required this.liveKitService,
    required this.storageService,
    required this.supabaseService,
    required this.settingsService,
    required this.backendSyncService,
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
          create: (_) => AuthProvider(supabaseService),
        ),
        ChangeNotifierProxyProvider<AuthProvider, SettingsProvider>(
          create: (context) => SettingsProvider(
            settingsService,
            Provider.of<AuthProvider>(context, listen: false),
            backendSyncService,
          ),
          update: (context, auth, previous) => previous!,
        ),
        ChangeNotifierProvider(
          create: (_) => OrbController(),
        ),
        ChangeNotifierProvider(
          create: (_) => AppInitController(),
        ),
      ],
      child: MaterialApp(
        title: 'Zoya Voice Assistant',
        debugShowCheckedModeBanner: false,
        home: App(),
      ),
    );
  }
}

/// Clean up the agent process when app is closed
class AppLifecycleObserver extends WidgetsBindingObserver {
  final AgentProcessManager _agentManager = AgentProcessManager();

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) {
      debugPrint('[Main] App detached, stopping agent...');
      _agentManager.stopAgent();
    }
  }
}
