import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/providers/settings_provider.dart';
import 'package:voice_assistant/widgets/settings/api_keys_panel.dart';

import '../../helpers/fake_settings_deps.dart';

void main() {
  group('ApiKeysPanel persistence behavior', () {
    late InMemorySecureKeyStorageService secureStorage;
    late FakeBackendSyncService backendSync;
    late FakeSettingsService settingsService;
    late SettingsProvider settingsProvider;

    setUp(() async {
      secureStorage = InMemorySecureKeyStorageService();
      backendSync = FakeBackendSyncService(statusPayload: {
        'status': {'livekit': true},
        'masked': {
          'livekit_url': 'wss://***',
          'livekit_api_key': '****',
          'livekit_api_secret': '****',
        },
      });
      settingsService = FakeSettingsService(FakeSupabaseService());
      settingsProvider = await buildSettingsProviderForTest(
        secureStorage: secureStorage,
        backendSync: backendSync,
        settingsService: settingsService,
        authenticated: false,
      );
    });

    Widget buildHarness({
      required Map<String, dynamic> apiKeys,
      Map<String, bool>? showApiKey,
    }) {
      final visibility = showApiKey ?? <String, bool>{};
      return ChangeNotifierProvider<SettingsProvider>.value(
        value: settingsProvider,
        child: MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: ApiKeysPanel(
                apiKeys: apiKeys,
                showApiKey: visibility,
                awsAccessKey: '',
                awsSecretKey: '',
                awsRegion: 'us-east-1',
                llmTemperature: 0.7,
                onApiKeyChanged: (_, __) {},
                onVisibilityChanged: (provider, visible) => visibility[provider] = visible,
                onAwsAccessKeyChanged: (_) {},
                onAwsSecretKeyChanged: (_) {},
                onAwsRegionChanged: (_) {},
                onTemperatureChanged: (_) {},
              ),
            ),
          ),
        ),
      );
    }

    testWidgets('saved LiveKit URL is prefilled in slot 1', (tester) async {
      await tester.pumpWidget(buildHarness(apiKeys: {
        'livekit_active_slot': '1',
        'livekit_url': 'wss://persisted-slot1',
      }));
      await tester.pumpAndSettle();

      final field = tester.widget<TextFormField>(find.byKey(const Key('livekit_url_field')));
      expect(field.initialValue, 'wss://persisted-slot1');
    });

    testWidgets('active slot is restored to slot 2 fields', (tester) async {
      await tester.pumpWidget(buildHarness(apiKeys: {
        'livekit_active_slot': '2',
        'livekit_url_2': 'wss://persisted-slot2',
      }));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('livekit_url_2_field')), findsOneWidget);
      expect(find.byKey(const Key('livekit_url_field')), findsNothing);
    });

    testWidgets('secret fields are obscured by default', (tester) async {
      await tester.pumpWidget(buildHarness(apiKeys: {
        'livekit_active_slot': '1',
        'livekit_api_key': 'my-secret-key',
      }));
      await tester.pumpAndSettle();

      final editable = tester.widget<EditableText>(
        find.descendant(
          of: find.byKey(const Key('livekit_api_key_field')),
          matching: find.byType(EditableText),
        ),
      );
      expect(editable.obscureText, isTrue);
    });
  });
}
