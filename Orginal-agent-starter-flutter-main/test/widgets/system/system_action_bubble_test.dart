import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/widgets/features/chat/system_action_bubble.dart';

void main() {
  Widget wrap(Widget child) {
    return MaterialApp(
      home: Scaffold(body: child),
    );
  }

  testWidgets('renders action label and message', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SystemActionBubble(
          actionType: 'SCREENSHOT',
          message: 'Saved screenshot.',
          success: true,
        ),
      ),
    );

    expect(find.byKey(const Key('system_action_bubble')), findsOneWidget);
    expect(find.text('SCREENSHOT'), findsOneWidget);
    expect(find.text('Saved screenshot.'), findsOneWidget);
  });

  testWidgets('renders detail when provided', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SystemActionBubble(
          actionType: 'FILE_DELETE',
          message: 'Deleted file.',
          detail: '/tmp/test.txt',
          success: true,
        ),
      ),
    );

    expect(find.text('/tmp/test.txt'), findsOneWidget);
  });

  testWidgets('hides detail when empty', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SystemActionBubble(
          actionType: 'APP_LAUNCH',
          message: 'Opened calculator.',
          success: true,
        ),
      ),
    );

    expect(find.text('/tmp/test.txt'), findsNothing);
  });

  testWidgets('shows success icon for success state', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SystemActionBubble(
          actionType: 'APP_LAUNCH',
          message: 'Opened calculator.',
          success: true,
        ),
      ),
    );

    expect(find.byIcon(Icons.check_circle_outline), findsOneWidget);
  });

  testWidgets('shows error icon for failure state', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SystemActionBubble(
          actionType: 'PROCESS_KILL',
          message: 'I cannot kill that process.',
          success: false,
        ),
      ),
    );

    expect(find.byIcon(Icons.error_outline), findsOneWidget);
  });

  testWidgets('shows undo button when rollback is available', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SystemActionBubble(
          actionType: 'FILE_MOVE',
          message: 'Moved file.',
          success: true,
          rollbackAvailable: true,
        ),
      ),
    );

    expect(find.text('Undo'), findsOneWidget);
  });

  testWidgets('dismiss button calls callback', (tester) async {
    var dismissed = false;
    await tester.pumpWidget(
      wrap(
        SystemActionBubble(
          actionType: 'SCREENSHOT',
          message: 'Saved screenshot.',
          success: true,
          onDismiss: () => dismissed = true,
        ),
      ),
    );

    await tester.tap(find.byTooltip('Dismiss'));
    await tester.pump();

    expect(dismissed, isTrue);
  });

  testWidgets('auto dismiss fires after four seconds', (tester) async {
    var dismissed = false;
    await tester.pumpWidget(
      wrap(
        SystemActionBubble(
          actionType: 'SCREENSHOT',
          message: 'Saved screenshot.',
          success: true,
          onDismiss: () => dismissed = true,
        ),
      ),
    );

    await tester.pump(const Duration(seconds: 4));

    expect(dismissed, isTrue);
  });
}
