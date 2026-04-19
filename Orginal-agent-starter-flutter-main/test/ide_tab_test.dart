import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/widgets/features/workbench/ide_tab.dart';

import 'helpers/fake_ide_services.dart';

void main() {
  group('IDE Tab Widget Tests', () {
    late FakeIdeFilesService filesService;
    late FakeIdeTerminalService terminalService;

    Future<void> pumpIdeTab(WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: IDETab(
              filesService: filesService,
              terminalService: terminalService,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    setUp(() {
      filesService = FakeIdeFilesService();
      terminalService = FakeIdeTerminalService();
    });

    testWidgets('IDE tab renders with three sub-tabs', (WidgetTester tester) async {
      await pumpIdeTab(tester);

      expect(find.text('Files'), findsOneWidget);
      expect(find.text('Terminal'), findsOneWidget);
      expect(find.text('Agentic'), findsOneWidget);
      expect(find.byKey(const Key('ide-subtab-files')), findsOneWidget);
      expect(find.byKey(const Key('ide-subtab-terminal')), findsOneWidget);
      expect(find.byKey(const Key('ide-subtab-agentic')), findsOneWidget);
    });

    testWidgets('Files tab renders breadcrumb, list, and editor shell', (WidgetTester tester) async {
      await pumpIdeTab(tester);

      expect(find.byKey(const Key('ide-pane-files')), findsOneWidget);
      expect(find.byKey(const Key('ide-files-breadcrumb')), findsOneWidget);
      expect(find.byKey(const Key('ide-files-list')), findsOneWidget);
      expect(find.text('Select a file to start editing'), findsOneWidget);
    });

    testWidgets('Can switch to Terminal tab and see terminal controls', (WidgetTester tester) async {
      await pumpIdeTab(tester);

      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-pane-terminal')), findsOneWidget);
      expect(find.text('Run command... (press Enter)'), findsOneWidget);
      expect(find.text('Send'), findsOneWidget);
    });

    testWidgets('Can switch to Agentic tab', (WidgetTester tester) async {
      await pumpIdeTab(tester);

      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();

      expect(find.text('Agentic - Coming in P12.5'), findsOneWidget);
      expect(find.text('AI-powered code assistance'), findsOneWidget);
    });
  });
}
