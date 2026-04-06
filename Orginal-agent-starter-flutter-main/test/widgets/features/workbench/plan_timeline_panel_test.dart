import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/core/events/agent_event_models.dart';
import 'package:voice_assistant/state/controllers/agent_activity_controller.dart';
import 'package:voice_assistant/state/controllers/workspace_controller.dart';
import 'package:voice_assistant/widgets/features/workbench/plan_timeline_panel.dart';

void main() {
  group('PlanTimelinePanel', () {
    testWidgets('no task selected shows placeholder text', (tester) async {
      final activity = AgentActivityController();
      final workspace = WorkspaceController();

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: activity),
            ChangeNotifierProvider.value(value: workspace),
          ],
          child: const MaterialApp(home: Scaffold(body: PlanTimelinePanel())),
        ),
      );

      expect(find.text('Select a task to see its plan'), findsOneWidget);
    });

    testWidgets('current step is distinct from completed steps', (tester) async {
      final activity = AgentActivityController();
      final workspace = WorkspaceController()..selectTask('task-running');
      activity.ingestForTesting(
        const AgentUiEvent(
          eventType: 'tool_execution',
          schemaVersion: '1',
          taskId: 'task-running',
          timestamp: 1,
          payload: {'tool_name': 'web_search', 'status': 'running'},
        ),
      );

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: activity),
            ChangeNotifierProvider.value(value: workspace),
          ],
          child: const MaterialApp(home: Scaffold(body: PlanTimelinePanel())),
        ),
      );

      expect(find.byKey(const Key('timeline_current_step')), findsOneWidget);
      expect(find.byIcon(Icons.check_circle), findsWidgets);
    });

    testWidgets('failed step shows error indicator', (tester) async {
      final activity = AgentActivityController();
      final workspace = WorkspaceController()..selectTask('task-failed');
      activity.ingestForTesting(
        const AgentUiEvent(
          eventType: 'tool_execution',
          schemaVersion: '1',
          taskId: 'task-failed',
          timestamp: 1,
          payload: {'tool_name': 'research', 'status': 'failed', 'result': 'error'},
        ),
      );

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: activity),
            ChangeNotifierProvider.value(value: workspace),
          ],
          child: const MaterialApp(home: Scaffold(body: PlanTimelinePanel())),
        ),
      );

      expect(find.byKey(const Key('timeline_failed_indicator')), findsOneWidget);
    });
  });
}
