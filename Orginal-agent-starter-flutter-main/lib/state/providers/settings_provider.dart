import 'dart:async';

import '../base_provider.dart';
import '../../core/services/settings_service.dart';
import 'auth_provider.dart';
import '../../core/services/backend_sync_service.dart';
import '../../core/services/storage_service.dart';
import '../../core/services/secure_key_storage_service.dart';

class SettingsProvider extends BaseProvider {
  final SettingsService _settingsService;
  AuthProvider _authProvider;
  final BackendSyncService _backendSyncService;
  final SecureKeyStorageService _secureStorage;
  final StorageService _storageService;

  static const Map<String, String> _connectorToggleKeys = {
    'spotify': 'connector_spotify_enabled',
    'youtube': 'connector_youtube_enabled',
    'google_workspace': 'connector_google_workspace_enabled',
    'slack': 'connector_slack_enabled',
    'home_assistant': 'connector_home_assistant_enabled',
    'github': 'connector_github_enabled',
  };

  static const Map<String, Map<String, dynamic>> _defaultConnectorState = {
    'spotify': {'enabled': false, 'available': true, 'reason': ''},
    'youtube': {'enabled': false, 'available': true, 'reason': ''},
    'google_workspace': {
      'enabled': false,
      'available': false,
      'reason': 'OAuth lifecycle not implemented yet.',
    },
    'slack': {'enabled': false, 'available': false, 'reason': 'OAuth lifecycle not implemented yet.'},
    'home_assistant': {
      'enabled': false,
      'available': false,
      'reason': 'Backend connector adapter not implemented yet.',
    },
    'github': {'enabled': false, 'available': false, 'reason': 'OAuth lifecycle not implemented yet.'},
  };

  Map<String, dynamic> _serverConfig = {};
  Map<String, dynamic> _userPreferences = {};
  Map<String, String> _maskedApiKeys = {};
  final Map<String, String> _localApiKeys = {};
  Map<String, Map<String, dynamic>> _connectorStatus = Map<String, Map<String, dynamic>>.from(_defaultConnectorState);
  final Map<String, bool> _connectorSaving = {};
  final Map<String, String> _connectorErrors = {};
  bool _isLoading = false;
  bool _isAdvancedMode = false;
  String _interactionMode = 'auto';

  SettingsProvider(
    this._settingsService,
    this._authProvider,
    this._backendSyncService, {
    SecureKeyStorageService? secureStorage,
    SecureKeyStorageService? secureKeyStorageService,
    StorageService? storageService,
  })  : _secureStorage = secureStorage ?? secureKeyStorageService ?? SecureKeyStorageService(),
        _storageService = storageService ?? StorageService(),
        super('SettingsProvider') {
    unawaited(_init());
    _authProvider.addListener(_onAuthChanged);
  }

  Future<void> _init() async {
    await _loadLocalPreferences();
    await _loadLocalApiKeys();
  }

  Map<String, dynamic> get serverConfig => _serverConfig;
  Map<String, dynamic> get preferences => _userPreferences;
  Map<String, String> get maskedApiKeys => _maskedApiKeys;
  Map<String, String> get localApiKeys => _localApiKeys;
  Map<String, Map<String, dynamic>> get connectorStatus => _connectorStatus;
  bool get isLoading => _isLoading;
  bool get isAdvancedMode => _isAdvancedMode;
  String get interactionMode => _interactionMode;
  String get userEmail => _authProvider.user?.email ?? 'Unknown';

  Future<void> initialize() async {
    await _init();
  }

  void updateAuth(AuthProvider auth) {
    if (_authProvider == auth) {
      return;
    }
    _authProvider.removeListener(_onAuthChanged);
    _authProvider = auth;
    _authProvider.addListener(_onAuthChanged);
    _onAuthChanged();
  }

  bool isConnectorSaving(String connectorId) => _connectorSaving[connectorId] == true;

  String? connectorError(String connectorId) => _connectorErrors[connectorId];

  bool connectorEnabled(String connectorId) => _connectorStatus[connectorId]?['enabled'] == true;

  bool connectorAvailable(String connectorId) => _connectorStatus[connectorId]?['available'] == true;

  String connectorReason(String connectorId) => (_connectorStatus[connectorId]?['reason'] ?? '').toString();

  Future<void> _loadLocalApiKeys() async {
    _localApiKeys.clear();
    _localApiKeys.addAll(await _secureStorage.loadApiKeys());
  }

  Future<void> _loadLocalPreferences() async {
    final localSettings = await _storageService.getSettings();
    final localPreferences = localSettings?['preferences'];
    if (localPreferences is Map<String, dynamic>) {
      _userPreferences = Map<String, dynamic>.from(localPreferences);
      _applyDerivedPreferences();
    }
  }

  Future<void> _persistLocalPreferences() async {
    await _storageService.saveSettings({'preferences': _userPreferences});
  }

  void _onAuthChanged() {
    if (_authProvider.isAuthenticated) {
      unawaited(fetchSettings());
      return;
    }
    unawaited(_loadLocalPreferences().then((_) => notifyListeners()));
  }

  Future<void> fetchSettings() async {
    _isLoading = true;
    notifyListeners();

    await safeExecute(() async {
      _serverConfig = await _settingsService.fetchServerConfig();
      await _loadLocalPreferences();

      if (_authProvider.isAuthenticated && _authProvider.user != null) {
        final userId = _authProvider.user!.id;
        final backendPreferences = await _settingsService.fetchUserSettings(userId);
        if (backendPreferences != null) {
          _userPreferences.addAll(backendPreferences);
          _applyDerivedPreferences();
          await _persistLocalPreferences();
        }
      }
    });

    _isLoading = false;
    notifyListeners();
  }

  /// Fetch API key status from backend (shows which keys are configured)
  Future<void> fetchApiKeyStatus() async {
    final data = await _backendSyncService.fetchApiKeyStatus();
    if (data.isEmpty) {
      return;
    }

    _serverConfig['apiKeyStatus'] = Map<String, dynamic>.from(data['status'] ?? {});
    _maskedApiKeys = Map<String, String>.from(data['masked'] ?? {});
    _hydrateConnectorStatus(data);
    log('✅ Fetched API key status from backend');
    notifyListeners();
  }

  void _hydrateConnectorStatus(Map<String, dynamic> statusPayload) {
    final merged = <String, Map<String, dynamic>>{};
    final connectorData = statusPayload['connectors'];
    for (final entry in _defaultConnectorState.entries) {
      final id = entry.key;
      final defaults = entry.value;
      final backendEntry = connectorData is Map<String, dynamic> ? connectorData[id] : null;
      if (backendEntry is Map<String, dynamic>) {
        merged[id] = {
          'enabled': backendEntry['enabled'] == true,
          'available': backendEntry['available'] == true,
          'reason': (backendEntry['reason'] ?? defaults['reason'] ?? '').toString(),
        };
      } else {
        merged[id] = Map<String, dynamic>.from(defaults);
      }
    }
    _connectorStatus = merged;
  }

  /// Sync API keys to backend
  Future<bool> syncApiKeysToBackend(Map<String, String> apiKeys) async {
    final success = await _backendSyncService.syncApiKeys(apiKeys);
    if (success) {
      await fetchApiKeyStatus();
    }
    return success;
  }

  Future<bool> setConnectorEnabled(String connectorId, bool enabled) async {
    final toggleKey = _connectorToggleKeys[connectorId];
    if (toggleKey == null) {
      return false;
    }

    final previousEnabled = connectorEnabled(connectorId);
    _connectorSaving[connectorId] = true;
    _connectorErrors.remove(connectorId);
    _setConnectorState(connectorId, enabled: enabled);
    notifyListeners();

    final success = await syncApiKeysToBackend({toggleKey: enabled.toString()});
    if (!success) {
      _setConnectorState(connectorId, enabled: previousEnabled);
      _connectorErrors[connectorId] = 'Failed to save connector setting. Check backend connectivity.';
    }

    _connectorSaving[connectorId] = false;
    notifyListeners();
    return success;
  }

  void _setConnectorState(String connectorId, {required bool enabled}) {
    final existing = _connectorStatus[connectorId] ?? <String, dynamic>{};
    _connectorStatus[connectorId] = {
      'enabled': enabled,
      'available': existing['available'] == true,
      'reason': (existing['reason'] ?? '').toString(),
    };
  }

  Future<bool> clearLocalConversationHistory() async {
    return await _storageService.saveConversationHistory(<String>[]);
  }

  /// Mask an API key (show first 4 and last 4 characters)
  static String maskApiKey(String? key) {
    if (key == null || key.isEmpty) return '';
    if (key.length <= 8) return '*' * key.length;
    return '${key.substring(0, 4)}${'*' * (key.length - 8)}${key.substring(key.length - 4)}';
  }

  Future<bool> updatePreference(String key, dynamic value) async {
    _userPreferences[key] = value;
    _applyDerivedPreferences();
    notifyListeners();

    await _persistLocalPreferences();

    if (_isBackendConfigKey(key)) {
      await syncApiKeysToBackend({key: value.toString()});
    }

    return await saveSettings();
  }

  Future<bool> updatePreferences(Map<String, dynamic> newPrefs) async {
    if (newPrefs.containsKey('apiKeys')) {
      final apiKeys = Map<String, String>.from(newPrefs['apiKeys'] ?? {});
      await updateApiKeys(apiKeys);
      newPrefs.remove('apiKeys');
    }

    if (newPrefs.containsKey('awsAccessKey') || newPrefs.containsKey('awsSecretKey')) {
      final awsKeys = <String, String>{};
      if (newPrefs['awsAccessKey']?.isNotEmpty == true) {
        awsKeys['aws_access_key'] = newPrefs['awsAccessKey'];
      }
      if (newPrefs['awsSecretKey']?.isNotEmpty == true) {
        awsKeys['aws_secret_key'] = newPrefs['awsSecretKey'];
      }
      if (awsKeys.isNotEmpty) {
        await syncApiKeysToBackend(awsKeys);
      }
      newPrefs.remove('awsAccessKey');
      newPrefs.remove('awsSecretKey');
    }

    final configUpdates = <String, String>{};
    newPrefs.forEach((k, v) {
      if (_isBackendConfigKey(k)) {
        configUpdates[k] = v.toString();
      }
    });
    if (configUpdates.isNotEmpty) {
      await syncApiKeysToBackend(configUpdates);
    }

    _userPreferences.addAll(newPrefs);
    _applyDerivedPreferences();
    notifyListeners();
    await _persistLocalPreferences();
    return await saveSettings();
  }

  Future<bool> saveSettings() async {
    final localSaveOk = await _storageService.saveSettings({'preferences': _userPreferences});
    if (!_authProvider.isAuthenticated || _authProvider.user == null) {
      return localSaveOk;
    }

    final remotePreferences = _buildSafeRemotePreferences(_userPreferences);
    final remoteSaveOk = await safeExecute(() async {
          await _settingsService.updateUserSettings(_authProvider.user!.id, remotePreferences);
          return true;
        }) ??
        false;
    return localSaveOk && remoteSaveOk;
  }

  Map<String, dynamic> _buildSafeRemotePreferences(Map<String, dynamic> source) {
    final sanitized = Map<String, dynamic>.from(source);
    sanitized.remove('apiKeys');
    for (final key in _legacySensitivePreferenceKeys) {
      sanitized.remove(key);
    }
    return sanitized;
  }

  static const Set<String> _legacySensitivePreferenceKeys = {
    'awsAccessKey',
    'awsSecretKey',
    'livekit_api_key',
    'livekit_api_secret',
    'openai_api_key',
    'groq_api_key',
    'deepgram_api_key',
    'cartesia_api_key',
    'mem0_api_key',
  };

  void _applyDerivedPreferences() {
    _isAdvancedMode = _userPreferences['isAdvancedMode'] == true;
    _interactionMode = (_userPreferences['interactionMode'] ?? 'auto').toString();
  }

  // Getters for specific settings with fallbacks
  String get llmProvider => _userPreferences['llmProvider'] ?? 'groq';
  String get llmModel => _userPreferences['llmModel'] ?? 'llama-3.1-8b-instant';
  double get llmTemperature => (_userPreferences['llmTemperature'] ?? 0.7).toDouble();
  String get sttProvider => _userPreferences['sttProvider'] ?? 'deepgram';
  String get sttModel => _userPreferences['sttModel'] ?? 'nova-2';
  String get sttLanguage => _userPreferences['sttLanguage'] ?? 'en-US';
  String get ttsProvider => _userPreferences['ttsProvider'] ?? 'edge_tts';
  String get ttsVoice => _userPreferences['ttsVoice'] ?? 'en-IN-NeerjaNeural';
  bool get mem0Enabled => _userPreferences['mem0Enabled'] ?? false;
  String get interfaceTheme => _userPreferences['interfaceTheme'] ?? 'zoya';

  // API Keys (return masked versions for display)
  Map<String, dynamic> get apiKeys => _userPreferences['apiKeys'] ?? {};
  Map<String, dynamic> get apiKeyStatus => _serverConfig['apiKeyStatus'] ?? {};
  String get awsAccessKey => '';
  String get awsSecretKey => '';
  String get awsRegion => _userPreferences['awsRegion'] ?? 'us-east-1';

  // Personalization
  String get userName => _userPreferences['userName'] ?? 'User';
  String get preferredLanguage => _userPreferences['preferredLanguage'] ?? 'en-US';
  String get assistantPersonality => _userPreferences['assistantPersonality'] ?? 'professional';

  // Visual Effects
  bool get quantumParticlesEnabled => _userPreferences['quantumParticlesEnabled'] ?? true;
  bool get orbitalGlowEnabled => _userPreferences['orbitalGlowEnabled'] ?? true;
  bool get soundEffectsEnabled => _userPreferences['soundEffectsEnabled'] ?? true;

  // Memory - return masked
  String get mem0ApiKey => maskedApiKeys['mem0'] ?? '';

  // Providers structure from server config
  Map<String, dynamic> get providers =>
      _serverConfig['providers'] ??
      {
        'llm': [],
        'stt': [],
        'tts': [],
      };

  bool _isBackendConfigKey(String key) {
    return const [
      'llmProvider',
      'llmModel',
      'sttProvider',
      'sttModel',
      'sttLanguage',
      'ttsProvider',
      'ttsModel',
      'ttsVoice',
    ].contains(key);
  }

  Future<void> updateApiKey(String key, String value, {bool syncBackend = true}) async {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      await _secureStorage.removeApiKey(key);
      _localApiKeys.remove(key);
    } else {
      _localApiKeys[key] = trimmed;
      await _secureStorage.saveApiKeys(_localApiKeys);
    }

    notifyListeners();

    if (syncBackend) {
      final payload = <String, String>{key: trimmed};
      await syncApiKeysToBackend(payload);
    }
  }

  Future<void> updateApiKeys(Map<String, String> apiKeys, {bool syncBackend = true}) async {
    final payload = <String, String>{};
    for (final entry in apiKeys.entries) {
      final key = entry.key;
      final value = entry.value.trim();
      if (value.isEmpty) {
        _localApiKeys.remove(key);
      } else {
        _localApiKeys[key] = value;
      }
      payload[key] = value;
    }
    await _secureStorage.saveApiKeys(_localApiKeys);

    notifyListeners();

    if (syncBackend && payload.isNotEmpty) {
      await syncApiKeysToBackend(payload);
    }
  }
}
