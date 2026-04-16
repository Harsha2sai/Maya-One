import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:voice_assistant/core/services/backend_sync_service.dart';
import 'package:voice_assistant/core/services/secure_key_storage_service.dart';
import 'package:voice_assistant/core/services/settings_service.dart';
import 'package:voice_assistant/core/services/storage_service.dart';
import 'package:voice_assistant/core/services/supabase_service.dart';
import 'package:voice_assistant/state/providers/auth_provider.dart';
import 'package:voice_assistant/state/models/conversation_models.dart';
import 'package:voice_assistant/state/providers/settings_provider.dart';

class InMemorySecureKeyStorageService extends SecureKeyStorageService {
  Map<String, String> _data = {};

  @override
  Future<Map<String, String>> loadApiKeys() async {
    return Map<String, String>.from(_data);
  }

  @override
  Future<void> saveApiKeys(Map<String, String> keys) async {
    _data = Map<String, String>.from(keys);
  }

  @override
  Future<void> removeApiKey(String key) async {
    _data.remove(key);
  }

  @override
  Future<void> clearApiKeys() async {
    _data = {};
  }
}

class InMemoryStorageService extends StorageService {
  Map<String, dynamic>? _settings;
  List<String> _conversationHistory = <String>[];
  ConversationStoreSnapshot? _conversationStore;
  bool _migrationComplete = false;

  @override
  Future<Map<String, dynamic>?> getSettings() async {
    if (_settings == null) {
      return null;
    }
    return Map<String, dynamic>.from(_settings!);
  }

  @override
  Future<bool> saveSettings(Map<String, dynamic> settings) async {
    _settings = Map<String, dynamic>.from(settings);
    return true;
  }

  @override
  Future<List<String>> getConversationHistory() async {
    return List<String>.from(_conversationHistory);
  }

  @override
  Future<bool> saveConversationHistory(List<String> history) async {
    _conversationHistory = List<String>.from(history);
    return true;
  }

  @override
  Future<ConversationStoreSnapshot?> loadConversationStore() async {
    return _conversationStore;
  }

  @override
  Future<bool> saveConversationStore(ConversationStoreSnapshot store) async {
    _conversationStore = store;
    return true;
  }

  @override
  Future<bool> hasConversationStore() async {
    return _conversationStore != null;
  }

  @override
  Future<bool> isConversationMigrationComplete() async {
    return _migrationComplete;
  }

  @override
  Future<bool> setConversationMigrationComplete(bool value) async {
    _migrationComplete = value;
    return true;
  }

  @override
  Future<bool> clearAll() async {
    _settings = null;
    _conversationHistory = <String>[];
    _conversationStore = null;
    _migrationComplete = false;
    return true;
  }
}

class FakeSupabaseService implements SupabaseService {
  final bool authenticated;
  final User? _user;

  FakeSupabaseService({this.authenticated = false})
      : _user = authenticated
            ? const User(
                id: 'test-user-id',
                appMetadata: {},
                userMetadata: {},
                aud: 'authenticated',
                createdAt: '2026-03-08T00:00:00.000Z',
              )
            : null;

  @override
  SupabaseClient get client => throw UnimplementedError('client not used in tests');

  @override
  bool get isAvailable => true;

  @override
  bool get isInitialized => true;

  @override
  User? get currentUser => _user;

  @override
  Session? get currentSession => null;

  @override
  Stream<AuthState> get authStateChanges => const Stream<AuthState>.empty();

  @override
  Future<void> initialize() async {}

  @override
  Future<AuthResponse> signIn(String email, String password) {
    throw UnimplementedError('signIn not used in tests');
  }

  @override
  Future<AuthResponse> signUp(String email, String password, {String? displayName}) {
    throw UnimplementedError('signUp not used in tests');
  }

  @override
  Future<void> signOut() async {}
}

class FakeSettingsService extends SettingsService {
  Map<String, dynamic>? lastUpdatedPayload;
  String? lastUpdatedUserId;
  Map<String, dynamic>? initialUserSettings;

  FakeSettingsService(SupabaseService supabaseService) : super(supabaseService);

  @override
  Future<Map<String, dynamic>> fetchServerConfig() async {
    return {
      'providers': {
        'llm': [],
        'stt': [],
        'tts': [],
      },
      'apiKeyStatus': <String, dynamic>{},
    };
  }

  @override
  Future<Map<String, dynamic>?> fetchUserSettings(String userId) async {
    return initialUserSettings;
  }

  @override
  Future<void> updateUserSettings(String userId, Map<String, dynamic> settings) async {
    lastUpdatedUserId = userId;
    lastUpdatedPayload = Map<String, dynamic>.from(settings);
  }
}

class FakeBackendSyncService extends BackendSyncService {
  bool syncShouldSucceed;
  int syncApiKeysCalls = 0;
  Map<String, String>? lastSyncedApiKeys;
  Map<String, dynamic> statusPayload;

  FakeBackendSyncService({
    this.syncShouldSucceed = true,
    this.statusPayload = const {},
  });

  @override
  Future<Map<String, dynamic>> fetchApiKeyStatus() async {
    return statusPayload;
  }

  @override
  Future<bool> syncApiKeys(Map<String, String> apiKeys) async {
    syncApiKeysCalls += 1;
    lastSyncedApiKeys = Map<String, String>.from(apiKeys);
    return syncShouldSucceed;
  }
}

Future<SettingsProvider> buildSettingsProviderForTest({
  required InMemorySecureKeyStorageService secureStorage,
  required FakeBackendSyncService backendSync,
  required FakeSettingsService settingsService,
  required bool authenticated,
  StorageService? storageService,
}) async {
  final auth = AuthProvider(FakeSupabaseService(authenticated: authenticated));
  final provider = SettingsProvider(
    settingsService,
    auth,
    backendSync,
    secureKeyStorageService: secureStorage,
    storageService: storageService ?? InMemoryStorageService(),
  );
  await Future<void>.delayed(const Duration(milliseconds: 20));
  return provider;
}
