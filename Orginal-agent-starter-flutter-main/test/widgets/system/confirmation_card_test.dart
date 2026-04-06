import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/widgets/features/chat/confirmation_card.dart';

void main() {
  Widget wrap(Widget child) {
    return MaterialApp(
      home: Scaffold(body: child),
    );
  }

  testWidgets('renders description and action type', (tester) async {
    await tester.pumpWidget(
      wrap(
        ConfirmationCard(
          actionType: 'FILE_DELETE',
          description: 'Delete test.txt',
          destructive: true,
          timeoutSeconds: 30,
          onRespond: (_) {},
        ),
      ),
    );

    expect(find.byKey(const Key('confirmation_card')), findsOneWidget);
    expect(find.text('FILE DELETE'), findsOneWidget);
    expect(find.text('Delete test.txt'), findsOneWidget);
  });

  testWidgets('shows destructive badge when destructive', (tester) async {
    await tester.pumpWidget(
      wrap(
        ConfirmationCard(
          actionType: 'FILE_DELETE',
          description: 'Delete test.txt',
          destructive: true,
          timeoutSeconds: 30,
          onRespond: (_) {},
        ),
      ),
    );

    expect(find.text('Destructive'), findsOneWidget);
  });

  testWidgets('hides destructive badge for non destructive actions', (tester) async {
    await tester.pumpWidget(
      wrap(
        ConfirmationCard(
          actionType: 'APP_CLOSE',
          description: 'Close calculator',
          destructive: false,
          timeoutSeconds: 30,
          onRespond: (_) {},
        ),
      ),
    );

    expect(find.text('Destructive'), findsNothing);
  });

  testWidgets('shows countdown text', (tester) async {
    await tester.pumpWidget(
      wrap(
        ConfirmationCard(
          actionType: 'FILE_DELETE',
          description: 'Delete test.txt',
          destructive: true,
          timeoutSeconds: 30,
          onRespond: (_) {},
        ),
      ),
    );

    expect(find.text('30s remaining'), findsOneWidget);
  });

  testWidgets('confirm button triggers true response', (tester) async {
    bool? result;
    await tester.pumpWidget(
      wrap(
        ConfirmationCard(
          actionType: 'FILE_DELETE',
          description: 'Delete test.txt',
          destructive: true,
          timeoutSeconds: 30,
          onRespond: (confirmed) => result = confirmed,
        ),
      ),
    );

    await tester.tap(find.text('Confirm'));
    await tester.pump();

    expect(result, isTrue);
    expect(find.text('Confirmed'), findsOneWidget);
  });

  testWidgets('cancel button triggers false response', (tester) async {
    bool? result;
    await tester.pumpWidget(
      wrap(
        ConfirmationCard(
          actionType: 'FILE_DELETE',
          description: 'Delete test.txt',
          destructive: true,
          timeoutSeconds: 30,
          onRespond: (confirmed) => result = confirmed,
        ),
      ),
    );

    await tester.tap(find.text('Cancel'));
    await tester.pump();

    expect(result, isFalse);
    expect(find.text('Cancelled'), findsOneWidget);
  });

  testWidgets('timeout auto cancels', (tester) async {
    bool? result;
    await tester.pumpWidget(
      wrap(
        ConfirmationCard(
          actionType: 'FILE_DELETE',
          description: 'Delete test.txt',
          destructive: true,
          timeoutSeconds: 2,
          onRespond: (confirmed) => result = confirmed,
        ),
      ),
    );

    await tester.pump(const Duration(seconds: 2));

    expect(result, isFalse);
    expect(find.text('Timed out — cancelled'), findsOneWidget);
  });

  testWidgets('countdown decrements before timeout', (tester) async {
    await tester.pumpWidget(
      wrap(
        ConfirmationCard(
          actionType: 'FILE_DELETE',
          description: 'Delete test.txt',
          destructive: true,
          timeoutSeconds: 3,
          onRespond: (_) {},
        ),
      ),
    );

    await tester.pump(const Duration(seconds: 1));

    expect(find.text('2s remaining'), findsOneWidget);
  });
}
