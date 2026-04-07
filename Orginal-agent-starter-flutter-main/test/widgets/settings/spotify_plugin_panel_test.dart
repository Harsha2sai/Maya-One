import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/providers/chat_provider.dart';
import 'package:voice_assistant/state/providers/session_provider.dart';
import 'package:voice_assistant/state/providers/settings_provider.dart';
import 'package:voice_assistant/widgets/settings/connectors_panel.dart';

class _ChatProviderStub extends ChangeNotifier implements ChatProvider {
  @override
  bool get spotifyConnected => false;

  @override
  String? get spotifyDisplayName => null;

  @override
  void updateSpotifyStatus({required bool connected, String? displayName}) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _SessionProviderStub extends ChangeNotifier implements SessionProvider {
  @override
  lk.Room? get room => null;

  @override
  Future<void> sendCommand(String action, [Map<String, dynamic>? payload]) async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _SettingsProviderStub extends ChangeNotifier implements SettingsProvider {
  @override
  Map<String, dynamic> get preferences => const {
        'connectorsEnabled': {
          'spotify': true,
        },
      };

  @override
  Future<bool> updatePreferences(Map<String, dynamic> newPrefs) async => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  testWidgets('renders connectors panel with spotify actions', (tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<ChatProvider>.value(value: _ChatProviderStub()),
          ChangeNotifierProvider<SessionProvider>.value(value: _SessionProviderStub()),
          ChangeNotifierProvider<SettingsProvider>.value(value: _SettingsProviderStub()),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: ConnectorsPanel(),
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('connectors_panel')), findsOneWidget);
    await tester.tap(find.byKey(const Key('connector_icon_spotify')));
    await tester.pumpAndSettle();

    expect(find.text('Spotify'), findsWidgets);
    expect(find.text('APPLICATION CONNECTOR'), findsOneWidget);
    expect(find.text('Connect Account'), findsOneWidget);
  });
}
