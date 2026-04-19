import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/widgets/features/workbench/ide_tab.dart';

void main() {
  group('IDE Tab Widget Tests', () {
    testWidgets('IDE tab renders with three sub-tabs', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: IDETab(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify all three tabs exist
      expect(find.text('Files'), findsOneWidget);
      expect(find.text('Terminal'), findsOneWidget);
      expect(find.text('Agentic'), findsOneWidget);
    });

    testWidgets('Files tab shows placeholder content', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: IDETab(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Files tab is default, verify placeholder text
      expect(find.text('Files - Coming in P12.3'), findsOneWidget);
      expect(find.text('Workspace file tree and editing'), findsOneWidget);
    });

    testWidgets('Can switch to Terminal tab', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: IDETab(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap Terminal tab
      await tester.tap(find.text('Terminal'));
      await tester.pumpAndSettle();

      // Verify Terminal content
      expect(find.text('Terminal - Coming in P12.4'), findsOneWidget);
      expect(find.text('Remote shell execution via backend'), findsOneWidget);
    });

    testWidgets('Can switch to Agentic tab', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: IDETab(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap Agentic tab
      await tester.tap(find.text('Agentic'));
      await tester.pumpAndSettle();

      // Verify Agentic content
      expect(find.text('Agentic - Coming in P12.5'), findsOneWidget);
      expect(find.text('AI-powered code assistance'), findsOneWidget);
    });
  });
}
