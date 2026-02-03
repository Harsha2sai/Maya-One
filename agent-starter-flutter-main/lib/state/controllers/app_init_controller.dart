import 'package:flutter/material.dart';
import 'package:logging/logging.dart';
import '../providers/auth_provider.dart';
import '../providers/session_provider.dart';
import '../providers/settings_provider.dart';
import '../controllers/orb_controller.dart';

enum InitState {
  appBoot,
  backendInit,
  authRestore,
  sessionInit,
  agentInit,
  uiReady,
  orbAppear,
  orbActive
}

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

    _updateState(InitState.backendInit);
    // Backend is usually already init in main.dart, but we staged it here
    await Future.delayed(const Duration(milliseconds: 500));

    _updateState(InitState.authRestore);
    while (!auth.isInitialized) {
      await Future.delayed(const Duration(milliseconds: 100));
    }

    _updateState(InitState.sessionInit);
    await settings.fetchSettings();

    _updateState(InitState.agentInit);
    // Check session or other agent deps

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
