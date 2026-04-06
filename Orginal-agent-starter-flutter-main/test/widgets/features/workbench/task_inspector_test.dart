import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/core/events/agent_event_models.dart';
import 'package:voice_assistant/state/controllers/agent_activity_controller.dart';
import 'package:voice_assistant/state/controllers/conversation_controller.dart';
import 'package:voice_assistant/state/controllers/workspace_controller.dart';
import 'package:voice_assistant/state/models/conversation_models.dart';
import 'package:voice_assistant/widgets/features/workbench/task_inspector.dart';

class _FakeConversationController extends ConversationController {
  List<ConversationMessageSnapshot> responses = const <ConversationMessageSnapshot>[];

  @override
  List<ConversationMessageSnapshot> taskRelatedMessages(String? taskId) {
    return responses;
  }
}

void main() {
  group('TaskInspector', () {
    testWidgets('no task selected shows placeholder', (tester) async {
      final activity = AgentActivityController();
      final workspace = WorkspaceController();
      final conversation = _FakeConversationController();

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: activity),
            ChangeNotifierProvider.value(value: workspace),
            ChangeNotifierProvider<ConversationController>.value(value: conversation),
          ],
          child: const MaterialApp(home: Scaffold(body: TaskInspector())),
        ),
      );

      expect(find.text('Select a task to inspect'), findsOneWidget);
    });

    testWidgets('failed task shows error detail', (tester) async {
      final activity = AgentActivityController();
      final workspace = WorkspaceController()..selectTask('task-failed');
      final conversation = _FakeConversationController();

      activity.ingestForTesting(
        const AgentUiEvent(
          eventType: 'tool_execution',
          schemaVersion: '1',
          taskId: 'task-failed',
          timestamp: 1,
          payload: {
            'tool_name': 'research',
            'status': 'failed',
            'result': 'Network timeout while fetching sources',
          },
        ),
      );

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: activity),
            ChangeNotifierProvider.value(value: workspace),
            ChangeNotifierProvider<ConversationController>.value(value: conversation),
          ],
          child: const MaterialApp(home: Scaffold(body: TaskInspector())),
        ),
      );

      expect(find.byKey(const Key('task_inspector_error_detail')), findsOneWidget);
      expect(find.textContaining('Task failed'), findsOneWidget);
    });

    testWidgets('originating message shown when ConversationController has it', (tester) async {
      final activity = AgentActivityController();
      final workspace = WorkspaceController()..selectTask('task-1');
      final conversation = _FakeConversationController()
        ..responses = <ConversationMessageSnapshot>[
          ConversationMessageSnapshot(
            id: 'm1',
            role: ConversationMessageRole.user,
            messageType: ConversationMessageType.text,
            content: 'Please research electric vehicle market share.',
            timestamp: DateTime.now(),
            payload: const {'taskId': 'task-1'},
          ),
        ];

      activity.ingestForTesting(
        const AgentUiEvent(
          eventType: 'tool_execution',
          schemaVersion: '1',
          taskId: 'task-1',
          timestamp: 1,
          payload: {'tool_name': 'research', 'status': 'running'},
        ),
      );

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: activity),
            ChangeNotifierProvider.value(value: workspace),
            ChangeNotifierProvider<ConversationController>.value(value: conversation),
          ],
          child: const MaterialApp(home: Scaffold(body: TaskInspector())),
        ),
      );

      expect(find.byKey(const Key('task_inspector_origin_message')), findsOneWidget);
      expect(find.textContaining('electric vehicle'), findsOneWidget);
    });

    testWidgets('originating message absent gracefully when not found', (tester) async {
      final activity = AgentActivityController();
      final workspace = WorkspaceController()..selectTask('task-2');
      final conversation = _FakeConversationController()..responses = const <ConversationMessageSnapshot>[];

      activity.ingestForTesting(
        const AgentUiEvent(
          eventType: 'tool_execution',
          schemaVersion: '1',
          taskId: 'task-2',
          timestamp: 1,
          payload: {'tool_name': 'research', 'status': 'running'},
        ),
      );

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: activity),
            ChangeNotifierProvider.value(value: workspace),
            ChangeNotifierProvider<ConversationController>.value(value: conversation),
          ],
          child: const MaterialApp(home: Scaffold(body: TaskInspector())),
        ),
      );

      expect(find.byKey(const Key('task_inspector_origin_message')), findsNothing);
      expect(find.text('Originating message'), findsNothing);
    });
  });
}
