import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/widgets/features/chat/conversation_header.dart';

void main() {
  testWidgets('ConversationHeader renders title and close button only', (tester) async {
    var closed = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConversationHeader(
            title: 'Chat',
            onClose: () => closed = true,
          ),
        ),
      ),
    );

    expect(find.text('Chat'), findsOneWidget);
    expect(find.byIcon(Icons.close), findsOneWidget);
    expect(find.textContaining('Greeting'), findsNothing);
    expect(find.textContaining('Connected'), findsNothing);

    await tester.tap(find.byIcon(Icons.close));
    await tester.pump();
    expect(closed, isTrue);
  });
}
