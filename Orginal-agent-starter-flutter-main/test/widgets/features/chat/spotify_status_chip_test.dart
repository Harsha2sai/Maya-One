import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/widgets/features/chat/spotify_status_chip.dart';

void main() {
  testWidgets('shows connected label when connected', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SpotifyStatusChip(
            connected: true,
            displayName: 'Harsha',
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('spotify_status_chip')), findsOneWidget);
    expect(find.textContaining('Spotify'), findsOneWidget);
    expect(find.textContaining('Harsha'), findsOneWidget);
  });

  testWidgets('shows disconnected label when not connected', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SpotifyStatusChip(
            connected: false,
          ),
        ),
      ),
    );

    expect(find.textContaining('disconnected'), findsOneWidget);
  });
}
