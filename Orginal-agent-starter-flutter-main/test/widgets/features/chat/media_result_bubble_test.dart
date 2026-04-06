import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/widgets/features/chat/media_result_bubble.dart';

void main() {
  testWidgets('renders track, provider line and status text', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: MediaResultBubble(
            trackName: 'Song A',
            provider: 'spotify',
            statusText: 'Play completed via SPOTIFY.',
            artist: 'Artist A',
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('media_result_bubble')), findsOneWidget);
    expect(find.text('Song A'), findsOneWidget);
    expect(find.text('via SPOTIFY'), findsOneWidget);
    expect(find.text('Play completed via SPOTIFY.'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 3100));
  });

  testWidgets('falls back to Media title when track is empty', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: MediaResultBubble(
            trackName: '',
            provider: 'playerctl',
            statusText: 'Play completed via PLAYERCTL.',
          ),
        ),
      ),
    );

    expect(find.text('Media'), findsOneWidget);
    expect(find.text('via PLAYERCTL'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 3100));
  });

  testWidgets('tap dismiss triggers callback', (tester) async {
    var dismissed = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MediaResultBubble(
            trackName: 'Song A',
            provider: 'spotify',
            statusText: 'Play completed via SPOTIFY.',
            onDismiss: () {
              dismissed = true;
            },
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('media_result_bubble')));
    await tester.pump();

    expect(dismissed, isTrue);
    await tester.pump(const Duration(milliseconds: 3100));
  });

  testWidgets('auto dismisses after 3000ms', (tester) async {
    var dismissed = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MediaResultBubble(
            trackName: 'Song A',
            provider: 'spotify',
            statusText: 'Play completed via SPOTIFY.',
            onDismiss: () {
              dismissed = true;
            },
          ),
        ),
      ),
    );

    await tester.pump(const Duration(milliseconds: 3100));
    await tester.pump();

    expect(dismissed, isTrue);
    expect(find.byKey(const Key('media_result_bubble')), findsNothing);
  });
}
