import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/services/ide_actions_service.dart';
import 'package:voice_assistant/core/services/ide_agentic_service.dart';
import 'package:voice_assistant/widgets/features/workbench/ide_tab.dart';

import 'helpers/fake_ide_services.dart';

void main() {
  group('IDE Tab Widget Tests', () {
    late FakeIdeFilesService filesService;
    late FakeIdeTerminalService terminalService;
    late FakeIdeAgenticService agenticService;
    late FakeIdeActionsService actionsService;

    Future<void> pumpIdeTab(WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: IDETab(
              filesService: filesService,
              terminalService: terminalService,
              agenticService: agenticService,
              actionsService: actionsService,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    Future<void> switchToAgentic(WidgetTester tester) async {
      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(TabBarView), const Offset(-600, 0));
      await tester.pumpAndSettle();
    }

    setUp(() {
      filesService = FakeIdeFilesService();
      terminalService = FakeIdeTerminalService();
      agenticService = FakeIdeAgenticService();
      actionsService = FakeIdeActionsService();
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

    testWidgets('Agentic tab renders analysis shell in empty state', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

      expect(find.byKey(const Key('ide-pane-agentic')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-filters')), findsOneWidget);
      expect(find.text('Waiting for runtime events…'), findsOneWidget);
      expect(find.text('Select a task to inspect execution trace'), findsOneWidget);
      expect(find.text('Select a task to view correlated traces'), findsOneWidget);
      expect(find.text('No dependency graph data'), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-live-state')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-connection')), findsOneWidget);
    });

    testWidgets('Agentic pane ingests events and dedupes by seq', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 101,
          eventType: 'task_started',
          timestamp: 1713500000,
          taskId: 'task-alpha',
          traceId: 'trace-alpha',
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
          traceId: 'trace-alpha',
          agentId: 'controller',
          status: 'running',
          payload: <String, dynamic>{'step': 2},
        ),
      );
      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 102,
          eventType: 'task_step',
          timestamp: 1713500002,
          taskId: 'task-alpha',
          traceId: 'trace-alpha',
          agentId: 'controller',
          status: 'running',
          payload: <String, dynamic>{'step': 3},
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-agentic-task-list')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-task-row-task-alpha')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-drilldown')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-trace-events')), findsOneWidget);
      expect(find.text('task_step'), findsOneWidget);
    });

    testWidgets('Task click opens drilldown for selected task', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 1,
          eventType: 'task_started',
          timestamp: 1,
          taskId: 'task-a',
          traceId: 'trace-main',
          status: 'running',
          payload: <String, dynamic>{},
        ),
      );
      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 2,
          eventType: 'task_step',
          timestamp: 2,
          taskId: 'task-a',
          traceId: 'trace-main',
          status: 'running',
          payload: <String, dynamic>{},
        ),
      );
      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 3,
          eventType: 'task_started',
          timestamp: 3,
          taskId: 'task-b',
          traceId: 'trace-main',
          status: 'running',
          payload: <String, dynamic>{},
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('ide-agentic-task-row-task-a')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-agentic-drilldown-header')), findsOneWidget);
      expect(find.text('task-a'), findsWidgets);
    });

    testWidgets('Agentic graph renders nodes and edges', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 1,
          eventType: 'task_started',
          timestamp: 1,
          taskId: 'task-a',
          traceId: 'trace-main',
          payload: <String, dynamic>{},
        ),
      );
      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 2,
          eventType: 'tool_started',
          timestamp: 2,
          taskId: 'task-a',
          traceId: 'trace-main',
          payload: <String, dynamic>{'tool': 'search'},
        ),
      );
      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 3,
          eventType: 'task_finished',
          timestamp: 3,
          taskId: 'task-a',
          traceId: 'trace-main',
          payload: <String, dynamic>{},
        ),
      );
      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 4,
          eventType: 'task_started',
          timestamp: 4,
          taskId: 'task-b',
          traceId: 'trace-main',
          payload: <String, dynamic>{},
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-agentic-graph')), findsOneWidget);
      expect(find.textContaining('task: task-a'), findsOneWidget);
      expect(find.textContaining('tool: search'), findsOneWidget);
      expect(find.textContaining('Graph ('), findsOneWidget);
      expect(find.textContaining('2 edges'), findsOneWidget);
    });

    testWidgets('Missing ids use unscoped fallback and do not crash', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 11,
          eventType: 'task_step',
          timestamp: 11,
          payload: <String, dynamic>{'note': 'no ids'},
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-agentic-task-row-unscoped-task')), findsOneWidget);
      expect(find.text('No trace_id correlation available'), findsOneWidget);
    });

    testWidgets('Agentic pane toggles Catching up mode during burst events', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

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
      await switchToAgentic(tester);

      agenticService.setState(IdeAgenticConnectionState.reconnecting);
      await tester.pump();
      expect(find.text('reconnecting'), findsOneWidget);

      agenticService.setState(IdeAgenticConnectionState.error, error: 'ws down');
      await tester.pump();
      expect(find.text('error'), findsOneWidget);
      expect(find.text('ws down'), findsOneWidget);
    });

    testWidgets('Agentic pane exposes mutating action controls', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

      expect(find.byKey(const Key('ide-agentic-action-retry')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-action-cancel')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-action-approval-center')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-action-mcp')), findsOneWidget);
    });

    testWidgets('Agentic toolbar opens approval center with pending actions', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

      actionsService.nextRequestResult = IdeActionResult(
        actionId: 'act-pending-1',
        status: 'pending',
        risk: 'high',
        policyReason: 'approval required',
      );

      agenticService.emitEvent(
        const IdeAgenticEvent(
          seq: 1,
          eventType: 'task_started',
          timestamp: 1,
          taskId: 'task-p13',
          traceId: 'trace-p13',
          payload: <String, dynamic>{},
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('ide-agentic-task-row-task-p13')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('ide-agentic-action-retry')));
      await tester.pumpAndSettle();

      expect(find.textContaining('queued for approval'), findsOneWidget);

      await tester.tap(find.byKey(const Key('ide-agentic-action-approval-center')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-agentic-approval-dialog')), findsOneWidget);
      expect(find.textContaining('act-pending-1'), findsOneWidget);
    });

    testWidgets('Agentic toolbar opens MCP inventory dialog', (WidgetTester tester) async {
      await pumpIdeTab(tester);
      await switchToAgentic(tester);

      await tester.tap(find.byKey(const Key('ide-agentic-action-mcp')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-agentic-mcp-dialog')), findsOneWidget);
      expect(find.byKey(const Key('ide-agentic-mcp-url')), findsOneWidget);
    });
  });
}
