import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/widgets/features/chat/conversation_list.dart';
import 'package:voice_assistant/widgets/features/chat/jump_to_latest_chip.dart';
import 'package:voice_assistant/state/providers/chat_provider.dart';

void main() {
  group('ConversationList Auto-Scroll Tests', () {
    late ChatProvider chatProvider;

    setUp(() {
      chatProvider = ChatProvider();
    });

    Widget buildTestApp() {
      return MaterialApp(
        home: Scaffold(
          body: ChangeNotifierProvider<ChatProvider>.value(
            value: chatProvider,
            child: const SizedBox(
              height: 400, // Fixed height to allow scrolling
              child: Column(
                children: [
                  ConversationList(),
                ],
              ),
            ),
          ),
        ),
      );
    }

    testWidgets('Scrolls to bottom initially when messages are present', (tester) async {
      for (int i = 0; i < 20; i++) {
        chatProvider.addMessage(ChatMessage(
          id: 'msg_$i',
          content: 'Message $i\nLine 2\nLine 3\nLine 4\nLine 5',
          timestamp: DateTime.now(),
          isUser: i % 2 == 0,
          isAgent: i % 2 != 0,
        ));
      }

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      final scrollable = tester.state<ScrollableState>(find.byType(Scrollable));
      final maxScrollExtent = scrollable.position.maxScrollExtent;
      final currentScroll = scrollable.position.pixels;

      // Ensure it's effectively at the bottom
      expect(currentScroll, greaterThanOrEqualTo(maxScrollExtent - 1.0));
      expect(find.byType(JumpToLatestChip), findsNothing);
    });

    testWidgets('JumpToLatestChip appears when user scrolls up', (tester) async {
      for (int i = 0; i < 20; i++) {
        chatProvider.addMessage(ChatMessage(
          id: 'msg_$i',
          content: 'Message $i\nLine 2\nLine 3\nLine 4\nLine 5',
          timestamp: DateTime.now(),
          isUser: i % 2 == 0,
          isAgent: i % 2 != 0,
        ));
      }

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      // Scroll up by drag
      await tester.drag(find.byType(Scrollable), const Offset(0, 400));
      await tester.pumpAndSettle();

      // Chip should appear
      expect(find.byType(JumpToLatestChip), findsOneWidget);
    });

    testWidgets('Tapping JumpToLatestChip scrolls to bottom and removes chip', (tester) async {
      for (int i = 0; i < 20; i++) {
        chatProvider.addMessage(ChatMessage(
          id: 'msg_$i',
          content: 'Message $i\nLine 2\nLine 3\nLine 4\nLine 5',
          timestamp: DateTime.now(),
          isUser: i % 2 == 0,
          isAgent: i % 2 != 0,
        ));
      }

      await tester.pumpWidget(buildTestApp());
      await tester.pumpAndSettle();

      // Scroll up
      await tester.drag(find.byType(Scrollable), const Offset(0, 400));
      await tester.pumpAndSettle();

      expect(find.byType(JumpToLatestChip), findsOneWidget);

      await tester.tap(find.byType(JumpToLatestChip));
      await tester.pumpAndSettle();

      final scrollable = tester.state<ScrollableState>(find.byType(Scrollable));
      final maxScrollExtent = scrollable.position.maxScrollExtent;
      final currentScroll = scrollable.position.pixels;
      
      expect(currentScroll, greaterThanOrEqualTo(maxScrollExtent - 1.0));
      expect(find.byType(JumpToLatestChip), findsNothing);
    });
  });
}
