import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/providers/settings_provider.dart';
import 'package:voice_assistant/widgets/settings/settings_dialog.dart';

import '../../helpers/fake_settings_deps.dart';

void main() {
  group('SettingsDialog mobile navigation', () {
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

    testWidgets('390 width shows section list and supports list -> page -> close', (
      tester,
    ) async {
      await setViewport(tester, const Size(390, 844));
      await tester.pumpWidget(buildHarness());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_mobile_layout')), findsOneWidget);
      expect(find.byKey(const Key('settings_mobile_section_list')), findsOneWidget);
      expect(find.byKey(const Key('settings_desktop_layout')), findsNothing);
      expect(find.byKey(const Key('settings_section_tile_connectors')), findsOneWidget);
      expect(find.byKey(const Key('settings_section_tile_mcp-servers')), findsOneWidget);
      expect(find.text('Spotify Plugin'), findsNothing);

      await tester.tap(find.byKey(const Key('settings_section_tile_api-keys')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_section_page')), findsOneWidget);
      expect(find.text('API Keys'), findsOneWidget);
      expect(find.byKey(const Key('settings_section_close')), findsOneWidget);

      await tester.tap(find.byKey(const Key('settings_section_close')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_mobile_section_list')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('1200 width keeps desktop split layout', (tester) async {
      await setViewport(tester, const Size(1200, 900));
      await tester.pumpWidget(buildHarness());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_desktop_layout')), findsOneWidget);
      expect(find.byKey(const Key('settings_mobile_section_list')), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });
}
