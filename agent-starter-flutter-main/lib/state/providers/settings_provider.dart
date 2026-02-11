import '../base_provider.dart';
import '../../core/services/settings_service.dart';
import 'auth_provider.dart';
import '../../core/services/backend_sync_service.dart';

class SettingsProvider extends BaseProvider {
  final SettingsService _settingsService;
  final AuthProvider _authProvider;
  final BackendSyncService _backendSyncService;

  Map<String, dynamic> _serverConfig = {};
  Map<String, dynamic> _userPreferences = {};
  Map<String, String> _maskedApiKeys = {}; // Masked keys from backend
  bool _isLoading = false;

  SettingsProvider(this._settingsService, this._authProvider, this._backendSyncService) : super('SettingsProvider') {
    _init();
    _authProvider.addListener(_onAuthChanged);
  }

  Map<String, dynamic> get serverConfig => _serverConfig;
  Map<String, dynamic> get preferences => _userPreferences;
  Map<String, String> get maskedApiKeys => _maskedApiKeys;
  bool get isLoading => _isLoading;

  Future<void> _init() async {
    await fetchSettings();
    await fetchApiKeyStatus();
  }

  void _onAuthChanged() {
    if (_authProvider.isAuthenticated) {
      fetchSettings();
    } else {
      _userPreferences = {};
      notifyListeners();
    }
  }

  Future<void> fetchSettings() async {
    _isLoading = true;
    notifyListeners();

    await safeExecute(() async {
      // 1. Fetch server defaults
      _serverConfig = await _settingsService.fetchServerConfig();

      // 2. If authenticated, fetch user specifics from Supabase
      if (_authProvider.isAuthenticated) {
        final userId = _authProvider.user!.id;
        final up = await _settingsService.fetchUserSettings(userId);
        if (up != null) {
          _userPreferences = up;
        }
      }
    });

    _isLoading = false;
    notifyListeners();
  }

  /// Fetch API key status from backend (shows which keys are configured)
  Future<void> fetchApiKeyStatus() async {
    final data = await _backendSyncService.fetchApiKeyStatus();
    if (data.isNotEmpty) {
      _serverConfig['apiKeyStatus'] = data['status'] ?? {};
      _maskedApiKeys = Map<String, String>.from(data['masked'] ?? {});
      log('✅ Fetched API key status from backend');
      notifyListeners();
    }
  }

  /// Sync API keys to backend
  Future<bool> syncApiKeysToBackend(Map<String, String> apiKeys) async {
    final success = await _backendSyncService.syncApiKeys(apiKeys);
    if (success) {
      await fetchApiKeyStatus(); // Refresh status
    }
    return success;
  }

  /// Mask an API key (show first 4 and last 4 characters)
  static String maskApiKey(String? key) {
    if (key == null || key.isEmpty) return '';
    if (key.length <= 8) return '*' * key.length;
    return '${key.substring(0, 4)}${'*' * (key.length - 8)}${key.substring(key.length - 4)}';
  }

  Future<bool> updatePreference(String key, dynamic value) async {
    _userPreferences[key] = value;
    notifyListeners();

    // Sync to backend if it affects agent configuration
    if (_isBackendConfigKey(key)) {
      await syncApiKeysToBackend({key: value.toString()});
    }

    return await saveSettings();
  }

  Future<bool> updatePreferences(Map<String, dynamic> newPrefs) async {
    // Handle API keys separately - sync to backend
    if (newPrefs.containsKey('apiKeys')) {
      final apiKeys = Map<String, String>.from(newPrefs['apiKeys'] ?? {});
      if (apiKeys.isNotEmpty) {
        await syncApiKeysToBackend(apiKeys);
      }
      // Don't store full API keys in user preferences - only in backend
      newPrefs.remove('apiKeys');
    }

    // Handle AWS credentials - sync to backend
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
      // Store AWS region only, not the keys
      newPrefs.remove('awsAccessKey');
      newPrefs.remove('awsSecretKey');
    }

    // Handle Config Sync for bulk updates
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
    notifyListeners();
    return await saveSettings();
  }

  Future<bool> saveSettings() async {
    if (!_authProvider.isAuthenticated) return false;

    return await safeExecute(() async {
          await _settingsService.updateUserSettings(_authProvider.user!.id, _userPreferences);
          return true;
        }) ??
        false;
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
  String get awsAccessKey => ''; // Never return full key
  String get awsSecretKey => ''; // Never return full key
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
}
