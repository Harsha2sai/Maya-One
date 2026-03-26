import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/state/providers/chat_provider.dart';
import 'package:voice_assistant/widgets/features/chat/source_cards_panel.dart';

void main() {
  Widget wrap(Widget child) {
    return MaterialApp(
      home: Scaffold(body: child),
    );
  }

  testWidgets('sources panel expands and shows cards', (tester) async {
    final sources = [
      const Source(
        title: 'Example 1',
        url: 'https://example.com/1',
        domain: 'example.com',
        snippet: 'Snippet 1',
        provider: 'tavily',
      ),
      const Source(
        title: 'Example 2',
        url: 'https://example.com/2',
        domain: 'example.com',
        snippet: 'Snippet 2',
        provider: 'serper',
      ),
    ];

    await tester.pumpWidget(wrap(SourceCardsPanel(sources: sources)));

    expect(find.text('Sources (2)'), findsOneWidget);
    expect(find.byKey(const Key('source_cards_list')), findsNothing);

    await tester.tap(find.byKey(const Key('source_cards_toggle')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('source_cards_list')), findsOneWidget);
    expect(find.text('Example 1'), findsOneWidget);
    expect(find.text('Example 2'), findsOneWidget);
  });

  testWidgets('empty sources renders nothing', (tester) async {
    await tester.pumpWidget(wrap(const SourceCardsPanel(sources: [])));
    expect(find.byKey(const Key('source_cards_toggle')), findsNothing);
  });
}
