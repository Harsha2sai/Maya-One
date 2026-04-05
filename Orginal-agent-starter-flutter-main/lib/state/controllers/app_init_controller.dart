import 'package:flutter/material.dart';
import 'package:logging/logging.dart';
import '../providers/auth_provider.dart';
import '../providers/session_provider.dart';
import '../providers/settings_provider.dart';
import '../controllers/orb_controller.dart';
import '../../core/services/backend_sync_service.dart';

enum InitState { appBoot, backendInit, authRestore, sessionInit, agentInit, uiReady, orbAppear, orbActive }

class AppInitController extends ChangeNotifier {
  final Logger _logger = Logger('AppInitController');
  InitState _state = InitState.appBoot;

  InitState get state => _state;

  void initialize(
    AuthProvider auth,
    SettingsProvider settings,
    SessionProvider session,
    OrbController orb,
  ) async {
    _updateState(InitState.appBoot);
    await Future.delayed(const Duration(milliseconds: 500));

    // --- STEP 1: START AGENT ---
    _updateState(InitState.backendInit);
    try {
      // await AgentProcessManager().startAgent(); // Disabled for manual dev verification
    } catch (e) {
      _logger.severe('Failed to start agent process: $e');
    }

    // --- STEP 2: WAIT FOR BACKEND ---
    try {
      await BackendSyncService().waitForBackend();
    } catch (e) {
      _logger.severe('Backend failed to become ready: $e');
      // Decide if we should return here or let it fail downstream
    }

    _updateState(InitState.authRestore);
    while (!auth.isInitialized) {
      await Future.delayed(const Duration(milliseconds: 100));
    }

    _updateState(InitState.sessionInit);
    try {
      await settings.fetchSettings().timeout(const Duration(seconds: 8));
    } catch (e) {
      _logger.warning('Settings fetch timed out during init, continuing with defaults: $e');
    }

    // --- STEP 3: ACTIVATE SESSION ---
    _updateState(InitState.agentInit);
    var connected = await session.connect(userId: auth.user?.id);
    if (!connected) {
      _logger.warning('Initial session connect failed; retrying with backend recheck');
      for (var attempt = 1; attempt <= 3; attempt++) {
        await Future.delayed(Duration(seconds: attempt * 2));
        try {
          await BackendSyncService().waitForBackend();
        } catch (_) {
          // Keep retrying connect; backend may come up between probes.
        }
        connected = await session.connect(userId: auth.user?.id);
        if (connected) {
          _logger.info('Session connect retry succeeded on attempt $attempt');
          break;
        }
      }
    }
    if (!connected) {
      _logger.severe('Session failed to connect after retries');
    }

    _updateState(InitState.uiReady);
    await Future.delayed(const Duration(milliseconds: 800));

    _updateState(InitState.orbAppear);
    orb.setLifecycle(OrbLifecycle.appearing);
    await Future.delayed(const Duration(milliseconds: 1200));

    _updateState(InitState.orbActive);
    orb.setLifecycle(OrbLifecycle.idle);
  }

  void _updateState(InitState newState) {
    _state = newState;
    _logger.info('App State: $newState');
    notifyListeners();
  }
}
