import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/providers/settings_provider.dart';
import 'package:voice_assistant/widgets/settings/settings_dialog.dart';

import '../../helpers/fake_settings_deps.dart';

void main() {
  group('SettingsDialog archived nav', () {
    late SettingsProvider settingsProvider;

    setUp(() async {
      settingsProvider = await buildSettingsProviderForTest(
        secureStorage: InMemorySecureKeyStorageService(),
        backendSync: FakeBackendSyncService(),
        settingsService: FakeSettingsService(FakeSupabaseService()),
        authenticated: false,
      );
    });

    Future<void> setDesktopViewport(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
    }

    testWidgets('desktop settings sidebar shows current sections', (tester) async {
      await setDesktopViewport(tester);

      await tester.pumpWidget(
        ChangeNotifierProvider<SettingsProvider>.value(
          value: settingsProvider,
          child: const MaterialApp(
            home: Scaffold(
              body: SettingsDialog(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Profile'), findsOneWidget);
      expect(find.text('Preferences'), findsOneWidget);
      expect(find.text('Memory & Privacy'), findsOneWidget);
      expect(find.text('Connectors'), findsOneWidget);
      expect(find.text('Tools & MCP'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
