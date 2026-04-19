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
      await tester.pump();

      expect(find.text('Files'), findsOneWidget);
      expect(find.text('Terminal'), findsOneWidget);
      expect(find.text('Agentic'), findsOneWidget);
      expect(find.byKey(const Key('ide-subtab-files')), findsOneWidget);
      expect(find.byKey(const Key('ide-subtab-terminal')), findsOneWidget);
      expect(find.byKey(const Key('ide-subtab-agentic')), findsOneWidget);
    });

    testWidgets('Files tab shows placeholder content', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: IDETab(),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('Files - Coming in P12.4'), findsOneWidget);
      expect(find.text('Workspace file tree and editing'), findsOneWidget);
      expect(find.byKey(const Key('ide-pane-files')), findsOneWidget);
    });

    testWidgets('Can switch to Terminal tab and see live terminal controls', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: IDETab(),
          ),
        ),
      );
      await tester.pump();

      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-pane-terminal')), findsOneWidget);
      expect(find.text('Run command... (press Enter)'), findsOneWidget);
      expect(find.text('Send'), findsOneWidget);
      expect(find.text('Terminal ready. Type a command and press Enter.\n'), findsOneWidget);
    });

    testWidgets('Can switch to Agentic tab', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: IDETab(),
          ),
        ),
      );
      await tester.pump();

      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();

      expect(find.text('Agentic - Coming in P12.5'), findsOneWidget);
      expect(find.text('AI-powered code assistance'), findsOneWidget);
    });
  });
}
