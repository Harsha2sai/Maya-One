import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/services/ide_agentic_service.dart';
import 'package:voice_assistant/widgets/features/workbench/ide_tab.dart';

import 'helpers/fake_ide_services.dart';

void main() {
  group('IDE Tab Widget Tests', () {
    late FakeIdeFilesService filesService;
    late FakeIdeTerminalService terminalService;
    late FakeIdeAgenticService agenticService;

    Future<void> pumpIdeTab(WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: IDETab(
              filesService: filesService,
              terminalService: terminalService,
              agenticService: agenticService,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    setUp(() {
      filesService = FakeIdeFilesService();
      terminalService = FakeIdeTerminalService();
      agenticService = FakeIdeAgenticService();
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

    testWidgets('Can switch to Agentic tab and see live telemetry shell', (WidgetTester tester) async {
      await pumpIdeTab(tester);

      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-pane-agentic')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-filters')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-feed')), findsNothing);
      expect(find.byKey(const Key('ide-agentic-timeline')), findsNothing);
      expect(find.text('Waiting for runtime events…'), findsOneWidget);
      expect(find.text('No task timeline yet'), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-live-state')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-connection')), findsOneWidget);
    });

    testWidgets('Agentic pane ingests events and dedupes by seq', (WidgetTester tester) async {
      await pumpIdeTab(tester);

      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();

      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 101,
          eventType: 'task_started',
          timestamp: 1713500000,
          taskId: 'task-alpha',
          agentId: 'controller',
          status: 'running',
          payload: <String, dynamic>{'step': 1},
        ),
      );
      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 101,
          eventType: 'task_step',
          timestamp: 1713500001,
          taskId: 'task-alpha',
          agentId: 'controller',
          status: 'running',
          payload: <String, dynamic>{'step': 2},
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-agentic-feed')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-timeline')), findsOneWidget);
      expect(find.text('task_started'), findsWidgets);
      expect(find.text('task_step'), findsNothing);
      expect(find.text('task-alpha'), findsWidgets);
    });

    testWidgets('Agentic pane toggles Catching up mode during burst events', (WidgetTester tester) async {
      await pumpIdeTab(tester);

      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();

      for (var i = 1; i <= 65; i++) {
        agenticService.emitEvent(
          IdeAgenticEvent(
            seq: i,
            eventType: 'task_step',
            timestamp: 1713501000 + i.toDouble(),
            taskId: 'task-burst',
            agentId: 'agent-$i',
            status: 'running',
            payload: <String, dynamic>{'i': i},
          ),
        );
      }
      await tester.pump(const Duration(milliseconds: 50));

      expect(find.text('Catching up'), findsOneWidget);
    });

    testWidgets('Agentic pane shows reconnecting and error state banners', (WidgetTester tester) async {
      await pumpIdeTab(tester);

      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();

      agenticService.setState(IdeAgenticConnectionState.reconnecting);
      await tester.pump();
      expect(find.text('reconnecting'), findsOneWidget);

      agenticService.setState(IdeAgenticConnectionState.error, error: 'ws down');
      await tester.pump();
      expect(find.text('error'), findsOneWidget);
      expect(find.text('ws down'), findsOneWidget);
    });
  });
}
