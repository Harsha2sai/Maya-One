import 'package:flutter_test/flutter_test.dart';

import '../../helpers/fake_settings_deps.dart';

void main() {
  group('SettingsProvider secure API key persistence', () {
    late InMemorySecureKeyStorageService secureStorage;
    late FakeBackendSyncService backendSync;
    late FakeSettingsService settingsService;

    setUp(() {
      secureStorage = InMemorySecureKeyStorageService();
      backendSync = FakeBackendSyncService();
      settingsService = FakeSettingsService(FakeSupabaseService());
    });

    test('secure save path executes and reload restores keys', () async {
      final provider1 = await buildSettingsProviderForTest(
        secureStorage: secureStorage,
        backendSync: backendSync,
        settingsService: settingsService,
        authenticated: false,
      );

      await provider1.updatePreferences({
        'apiKeys': {
          'livekit_url': 'wss://livekit.example',
          'livekit_api_key': 'abc123',
          'livekit_active_slot': '2',
        }
      });

      expect(provider1.localApiKeys['livekit_url'], 'wss://livekit.example');
      expect(provider1.localApiKeys['livekit_api_key'], 'abc123');
      expect(provider1.localApiKeys['livekit_active_slot'], '2');

      final provider2 = await buildSettingsProviderForTest(
        secureStorage: secureStorage,
        backendSync: backendSync,
        settingsService: settingsService,
        authenticated: false,
      );

      expect(provider2.localApiKeys['livekit_url'], 'wss://livekit.example');
      expect(provider2.localApiKeys['livekit_api_key'], 'abc123');
      expect(provider2.localApiKeys['livekit_active_slot'], '2');
    });

    test('backend sync failure does not clear local values', () async {
      backendSync = FakeBackendSyncService(syncShouldSucceed: false);
      settingsService = FakeSettingsService(FakeSupabaseService());

      final provider = await buildSettingsProviderForTest(
        secureStorage: secureStorage,
        backendSync: backendSync,
        settingsService: settingsService,
        authenticated: false,
      );

      await provider.updatePreferences({
        'apiKeys': {
          'livekit_api_key': 'persist-me',
          'livekit_url': 'wss://persist.example',
        }
      });

      expect(backendSync.syncApiKeysCalls, 1);
      expect(provider.localApiKeys['livekit_api_key'], 'persist-me');
      expect(provider.localApiKeys['livekit_url'], 'wss://persist.example');
    });

    test('raw keys are excluded from Supabase payload', () async {
      final authedSettingsService = FakeSettingsService(FakeSupabaseService(authenticated: true));
      final provider = await buildSettingsProviderForTest(
        secureStorage: secureStorage,
        backendSync: backendSync,
        settingsService: authedSettingsService,
        authenticated: true,
      );

      final success = await provider.updatePreferences({
        'userName': 'Harsha',
        'apiKeys': {
          'livekit_api_key': 'super-secret',
          'livekit_url': 'wss://example.livekit.cloud',
        }
      });

      expect(success, isTrue);
      expect(authedSettingsService.lastUpdatedUserId, 'test-user-id');
      expect(authedSettingsService.lastUpdatedPayload, isNotNull);
      expect(authedSettingsService.lastUpdatedPayload!.containsKey('apiKeys'), isFalse);
      expect(authedSettingsService.lastUpdatedPayload!['userName'], 'Harsha');
    });
  });
}
