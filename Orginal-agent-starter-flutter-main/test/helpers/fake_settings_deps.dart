import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:voice_assistant/core/services/backend_sync_service.dart';
import 'package:voice_assistant/core/services/secure_key_storage_service.dart';
import 'package:voice_assistant/core/services/settings_service.dart';
import 'package:voice_assistant/core/services/supabase_service.dart';
import 'package:voice_assistant/state/providers/auth_provider.dart';
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
}) async {
  final auth = AuthProvider(FakeSupabaseService(authenticated: authenticated));
  final provider = SettingsProvider(
    settingsService,
    auth,
    backendSync,
    secureKeyStorageService: secureStorage,
  );
  await Future<void>.delayed(const Duration(milliseconds: 20));
  return provider;
}
