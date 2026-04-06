import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/providers/settings_provider.dart';
import 'package:voice_assistant/widgets/settings/settings_dialog.dart';

import '../../helpers/fake_settings_deps.dart';

void main() {
  group('SettingsDialog responsive layout', () {
    late SettingsProvider settingsProvider;

    setUp(() async {
      settingsProvider = await buildSettingsProviderForTest(
        secureStorage: InMemorySecureKeyStorageService(),
        backendSync: FakeBackendSyncService(),
        settingsService: FakeSettingsService(FakeSupabaseService()),
        authenticated: false,
      );
    });

    Widget buildHarness() {
      return ChangeNotifierProvider<SettingsProvider>.value(
        value: settingsProvider,
        child: const MaterialApp(
          home: Scaffold(
            body: SettingsDialog(),
          ),
        ),
      );
    }

    Future<void> setViewport(WidgetTester tester, Size size) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
    }

    testWidgets('uses mobile layout below 900 width', (tester) async {
      await setViewport(tester, const Size(390, 844));
      await tester.pumpWidget(buildHarness());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_mobile_layout')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('uses mobile layout for medium widths below 900', (tester) async {
      await setViewport(tester, const Size(768, 1024));
      await tester.pumpWidget(buildHarness());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_mobile_layout')), findsOneWidget);
      expect(find.byKey(const Key('settings_desktop_layout')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('uses desktop layout above 900 width', (tester) async {
      await setViewport(tester, const Size(1200, 900));
      await tester.pumpWidget(buildHarness());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_desktop_layout')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
