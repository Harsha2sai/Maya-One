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

  testWidgets('renders markdown summary and collapsed sources panel', (tester) async {
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
          summary: '**AI Trends - Key Findings**\n\n- Point one',
          sources: sources,
          traceId: 'test-trace-id',
        ),
      ),
    );

    expect(find.byKey(const Key('research_result_bubble')), findsOneWidget);
    expect(find.text('**AI Trends - Key Findings**'), findsNothing);
    expect(find.text('AI Trends - Key Findings'), findsOneWidget);
    expect(find.text('Point one'), findsOneWidget);
    expect(find.text('Sources (1)'), findsOneWidget);
    expect(find.byKey(const Key('source_cards_list')), findsNothing);
  });
}
