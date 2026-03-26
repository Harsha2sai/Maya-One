import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/state/providers/chat_provider.dart';
import 'package:voice_assistant/widgets/features/chat/research_result_bubble.dart';

void main() {
  Widget wrap(Widget child) {
    return MaterialApp(
      home: Scaffold(body: child),
    );
  }

  testWidgets('renders summary and collapsed sources panel', (tester) async {
    final sources = [
      const Source(
        title: 'Example',
        url: 'https://example.com',
        domain: 'example.com',
        snippet: 'Snippet',
        provider: 'tavily',
      )
    ];

    await tester.pumpWidget(
      wrap(
        ResearchResultBubble(
          summary: 'Research summary text',
          sources: sources,
        ),
      ),
    );

    expect(find.byKey(const Key('research_result_bubble')), findsOneWidget);
    expect(find.text('Research summary text'), findsOneWidget);
    expect(find.text('Sources (1)'), findsOneWidget);
    expect(find.byKey(const Key('source_cards_list')), findsNothing);
  });
}
