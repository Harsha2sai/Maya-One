import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/events/agent_event_models.dart';
import 'package:voice_assistant/state/controllers/agent_activity_controller.dart';
import 'package:voice_assistant/state/controllers/orb_controller.dart';

void main() {
  group('AgentActivityController', () {
    late StreamController<AgentUiEvent> agentEvents;
    late AgentActivityController controller;

    setUp(() {
      agentEvents = StreamController<AgentUiEvent>.broadcast(sync: true);
      controller = AgentActivityController(agentEvents: agentEvents.stream);
    });

    tearDown(() async {
      controller.dispose();
      await agentEvents.close();
    });

    test('bootstrap-resume functionality regression test', () async {
      // Simulate an offline -> reconnecting -> bootstrapping -> idle flow
      agentEvents.add(
        const AgentUiEvent(
          eventType: 'session_disconnected',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.offline);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'session_reconnecting',
          schemaVersion: '1.0',
          timestamp: 2,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.reconnecting);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'bootstrap_started',
          schemaVersion: '1.0',
          timestamp: 3,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.bootstrapping);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'bootstrap_acknowledged',
          schemaVersion: '1.0',
          timestamp: 4,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.idle);
    });

    test('updates voice state and leaves orb lifecycle to bridge', () async {
      final orbController = OrbController();
      controller.bindOrb(orbController);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'user_speaking',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.listening);
      expect(orbController.lifecycle, OrbLifecycle.hidden);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'agent_speaking',
          schemaVersion: '1.0',
          timestamp: 2,
          payload: <String, dynamic>{'status': 'speaking'},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.speaking);
      expect(orbController.lifecycle, OrbLifecycle.hidden);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'agent_thinking',
          schemaVersion: '1.0',
          timestamp: 3,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.thinking);
      expect(orbController.lifecycle, OrbLifecycle.hidden);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'agent_idle',
          schemaVersion: '1.0',
          timestamp: 4,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.idle);
      expect(orbController.lifecycle, OrbLifecycle.hidden);
    });

    test('maps greeting and bootstrap lifecycle events to voice ui states', () async {
      agentEvents.add(
        const AgentUiEvent(
          eventType: 'track_subscribed',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.greeting);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'bootstrap_started',
          schemaVersion: '1.0',
          timestamp: 2,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.bootstrapping);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'bootstrap_acknowledged',
          schemaVersion: '1.0',
          timestamp: 3,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.idle);
    });

    test('maps speaking and reconnect transitions', () async {
      agentEvents.add(
        const AgentUiEvent(
          eventType: 'agent_speaking',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{'status': 'speaking'},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.speaking);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'session_reconnecting',
          schemaVersion: '1.0',
          timestamp: 2,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.reconnecting);

      agentEvents.add(
        const AgentUiEvent(
          eventType: 'session_disconnected',
          schemaVersion: '1.0',
          timestamp: 3,
          payload: <String, dynamic>{},
        ),
      );
      expect(controller.voiceUiState, VoiceUiState.offline);
    });

    test('tracks active tool state from tool execution events', () async {
      agentEvents.add(
        const AgentUiEvent(
          eventType: 'tool_execution',
          schemaVersion: '1.0',
          taskId: 'task-1',
          timestamp: 1,
          payload: <String, dynamic>{
            'tool_name': 'web_search',
            'status': 'running',
          },
        ),
      );

      expect(controller.voiceUiState, VoiceUiState.toolRunning);
      expect(controller.activeToolName, 'web_search');
      expect(controller.activeTaskId, 'task-1');
    });
  });
}
