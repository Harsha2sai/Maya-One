import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/events/agent_event_models.dart';
import 'package:voice_assistant/core/events/agent_event_validator.dart';
import 'package:voice_assistant/core/services/livekit_service.dart';
import 'package:voice_assistant/state/controllers/overlay_controller.dart';
import 'package:voice_assistant/state/providers/chat_provider.dart';
import 'package:voice_assistant/state/providers/session_provider.dart';

void main() {
  group('SessionProvider chat event validation integration', () {
    late SessionProvider sessionProvider;
    late ChatProvider chatProvider;
    late OverlayController overlayController;
    late List<AgentUiEvent> emittedEvents;

    setUp(() {
      sessionProvider = SessionProvider(LiveKitService());
      chatProvider = ChatProvider();
      overlayController = OverlayController();
      chatProvider.bindOverlayController(overlayController);
      sessionProvider.bindChatProvider(chatProvider);
      emittedEvents = <AgentUiEvent>[];
      sessionProvider.agentEvents.listen(emittedEvents.add);
    });

    test('routes schema-mismatched but parseable known event via best effort', () {
      sessionProvider.processChatEventPayloadForTesting({
        'type': 'user_message',
        'schema_version': '2.0',
        'turn_id': 'turn-1',
        'content': 'hello from old schema',
        'timestamp': 1000,
      });

      expect(chatProvider.messages, isNotEmpty);
      expect(chatProvider.messages.last.content, contains('hello from old schema'));
      expect(emittedEvents.single.eventType, 'user_message');
      expect(emittedEvents.single.schemaVersion, AgentEventValidator.expectedSchemaVersion);
    });

    test('unknown event type is ignored without crash', () {
      sessionProvider.processChatEventPayloadForTesting({
        'type': 'future_event_x',
        'schema_version': '9.9',
        'timestamp': 1001,
      });

      expect(chatProvider.messages, isEmpty);
      expect(chatProvider.agentState, AgentState.idle);
    });

    test('invalid known event triggers safe fallback state', () {
      chatProvider.updateAgentState(AgentState.thinking);
      sessionProvider.processChatEventPayloadForTesting({
        'type': 'tool_execution',
        'schema_version': '1.0',
        'turn_id': 'turn-2',
        // missing tool_name and status -> invalid
        'timestamp': 1002,
      });

      expect(chatProvider.agentState, AgentState.idle);
    });

    test('routes system_result through validated chat path', () {
      sessionProvider.processChatEventPayloadForTesting({
        'type': 'system_result',
        'schema_version': '1.0',
        'turn_id': 'turn-system',
        'action_type': 'SCREENSHOT',
        'success': true,
        'message': 'Saved screenshot.',
        'detail': '/tmp/maya_screen.png',
        'rollback_available': false,
        'task_id': 'task-system-1',
        'conversation_id': 'conversation-1',
        'timestamp': 1003,
        'trace_id': 'trace-system',
      });

      expect(overlayController.systemActionToast, isNotNull);
      expect(overlayController.systemActionToast?.message, 'Saved screenshot.');
      expect(
        chatProvider.messages.last.payload['taskId'],
        'task-system-1',
      );
      expect(
        chatProvider.messages.last.payload['conversationId'],
        'conversation-1',
      );
      expect(emittedEvents.single.taskId, 'task-system-1');
      expect(emittedEvents.single.conversationId, 'conversation-1');
      expect(emittedEvents.single.originSessionId, '');
    });

    test('suppresses lk.agent.response fallback when structured research event is recent', () {
      sessionProvider.processChatEventPayloadForTesting({
        'type': 'research_result',
        'schema_version': '1.0',
        'turn_id': 'turn-research',
        'query': 'who invented python',
        'summary': '**Python — Key Facts**\n🔹 Created by Guido van Rossum',
        'sources': <Map<String, dynamic>>[],
        'timestamp': 1004,
        'trace_id': 'trace-research',
      });

      final beforeCount = chatProvider.messages.length;
      sessionProvider.processAgentResponsePayloadForTesting('fallback plain assistant text');

      expect(chatProvider.messages.length, beforeCount);
      expect(
        chatProvider.messages.where((m) => m.content.contains('fallback plain assistant text')),
        isEmpty,
      );
    });

    test('emits lifecycle events through the shared agent event stream', () {
      sessionProvider.updateConnectionStateForTesting(SessionConnectionState.connected);
      sessionProvider.updateConnectionStateForTesting(SessionConnectionState.reconnecting);
      sessionProvider.updateConnectionStateForTesting(SessionConnectionState.disconnected);

      expect(
        emittedEvents.map((event) => event.eventType),
        <String>['session_connected', 'session_reconnecting', 'session_disconnected'],
      );
    });

    test('bootstrap ack resolves before the timeout budget expires', () async {
      final stopwatch = Stopwatch()..start();
      final future = sessionProvider.waitForBootstrapAckForTesting(
        conversationId: 'conversation-1',
        bootstrapVersion: 1,
      );

      Future<void>.delayed(const Duration(milliseconds: 50), () {
        sessionProvider.handleBootstrapAckForTesting(<String, dynamic>{
          'conversation_id': 'conversation-1',
          'bootstrap_version': 1,
          'applied': true,
        });
      });

      final result = await future;
      stopwatch.stop();

      expect(result, isTrue);
      expect(stopwatch.elapsed, lessThan(const Duration(seconds: 2)));
      expect(
        emittedEvents.map((event) => event.eventType).take(2).toList(),
        <String>['bootstrap_started', 'bootstrap_acknowledged'],
      );
    });

    test('bootstrap timeout wins when the ack arrives after the timeout window', () async {
      final result = await sessionProvider.waitForBootstrapAckForTesting(
        conversationId: 'conversation-timeout',
        bootstrapVersion: 1,
        timeout: const Duration(milliseconds: 30),
      );

      sessionProvider.handleBootstrapAckForTesting(<String, dynamic>{
        'conversation_id': 'conversation-timeout',
        'bootstrap_version': 1,
        'applied': true,
      });

      expect(result, isFalse);
      expect(
        emittedEvents.map((event) => event.eventType),
        <String>['bootstrap_started', 'bootstrap_timeout'],
      );
    });
  });
}
