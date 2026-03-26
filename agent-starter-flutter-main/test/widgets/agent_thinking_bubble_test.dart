import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/state/providers/chat_provider.dart';
import 'package:voice_assistant/widgets/features/chat/agent_thinking_bubble.dart';

void main() {
  Widget wrap(Widget child) {
    return MaterialApp(
      home: Scaffold(body: child),
    );
  }

  testWidgets('renders thinking label', (tester) async {
    await tester.pumpWidget(
      wrap(
        const AgentThinkingBubble(state: AgentState.thinking),
      ),
    );
    expect(find.text('Thinking...'), findsOneWidget);
  });

  testWidgets('renders tool execution label', (tester) async {
    await tester.pumpWidget(
      wrap(
        const AgentThinkingBubble(state: AgentState.callingTools, tool: 'web_search'),
      ),
    );
    expect(find.text('Calling tool: web_search'), findsOneWidget);
  });

  testWidgets('renders writing response label', (tester) async {
    await tester.pumpWidget(
      wrap(
        const AgentThinkingBubble(state: AgentState.writingResponse),
      ),
    );
    expect(find.text('Writing response...'), findsOneWidget);
  });
}

