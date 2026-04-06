import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/core/events/agent_event_models.dart';
import 'package:voice_assistant/state/controllers/agent_activity_controller.dart';
import 'package:voice_assistant/widgets/layout/voice_status_bar.dart';

void main() {
  Future<void> pumpStatusBar(
    WidgetTester tester, {
    required AgentActivityController controller,
  }) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<AgentActivityController>.value(
        value: controller,
        child: const MaterialApp(
          home: Scaffold(
            body: VoiceStatusBar(),
          ),
        ),
      ),
    );
  }

  AgentUiEvent eventForState(VoiceUiState state) {
    switch (state) {
      case VoiceUiState.idle:
        return const AgentUiEvent(
          eventType: 'session_connected',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        );
      case VoiceUiState.listening:
        return const AgentUiEvent(
          eventType: 'user_speaking',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        );
      case VoiceUiState.thinking:
        return const AgentUiEvent(
          eventType: 'agent_thinking',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        );
      case VoiceUiState.toolRunning:
        return const AgentUiEvent(
          eventType: 'tool_execution',
          schemaVersion: '1.0',
          taskId: 'task-1',
          timestamp: 1,
          payload: <String, dynamic>{'tool_name': 'web_search', 'status': 'running'},
        );
      case VoiceUiState.speaking:
        return const AgentUiEvent(
          eventType: 'agent_speaking',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{'status': 'speaking'},
        );
      case VoiceUiState.greeting:
        return const AgentUiEvent(
          eventType: 'track_subscribed',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        );
      case VoiceUiState.interrupted:
        return const AgentUiEvent(
          eventType: 'agent_interrupted',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        );
      case VoiceUiState.bootstrapping:
        return const AgentUiEvent(
          eventType: 'bootstrap_started',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        );
      case VoiceUiState.offline:
        return const AgentUiEvent(
          eventType: 'session_disconnected',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        );
      case VoiceUiState.reconnecting:
        return const AgentUiEvent(
          eventType: 'session_reconnecting',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        );
    }
  }

  group('VoiceStatusBar', () {
    testWidgets('renders a non-null surface for every voice state', (tester) async {
      final controller = AgentActivityController();
      addTearDown(controller.dispose);

      await pumpStatusBar(tester, controller: controller);

      for (final state in VoiceUiState.values) {
        controller.ingestForTesting(eventForState(state));
        await tester.pump();

        expect(find.byKey(const Key('voice_status_bar')), findsOneWidget);
        expect(find.byKey(const Key('voice_status_state_label')), findsOneWidget);
        expect(find.byKey(const Key('voice_status_detail_text')), findsOneWidget);
      }
    });

    testWidgets('renders greeting and bootstrapping labels explicitly', (tester) async {
      final controller = AgentActivityController();
      addTearDown(controller.dispose);

      await pumpStatusBar(tester, controller: controller);

      controller.ingestForTesting(eventForState(VoiceUiState.greeting));
      await tester.pump();
      expect(find.text('Greeting'), findsOneWidget);
      expect(find.textContaining('greeting the session'), findsOneWidget);

      controller.ingestForTesting(eventForState(VoiceUiState.bootstrapping));
      await tester.pump();
      expect(find.text('Resuming...'), findsOneWidget);
      expect(find.textContaining('Switching conversation context'), findsOneWidget);
    });

    testWidgets('renders offline and reconnecting states explicitly', (tester) async {
      final controller = AgentActivityController();
      addTearDown(controller.dispose);

      await pumpStatusBar(tester, controller: controller);

      controller.ingestForTesting(eventForState(VoiceUiState.offline));
      await tester.pump();
      expect(find.text('Offline'), findsOneWidget);
      expect(find.text('Connection lost'), findsOneWidget);

      controller.ingestForTesting(eventForState(VoiceUiState.reconnecting));
      await tester.pump();
      expect(find.text('Reconnecting...'), findsOneWidget);
      expect(find.text('Restoring the session'), findsOneWidget);
    });

    testWidgets('greeting state renders same visual treatment as speaking', (tester) async {
      final controllerSpeaking = AgentActivityController();
      addTearDown(controllerSpeaking.dispose);
      await pumpStatusBar(tester, controller: controllerSpeaking);
      controllerSpeaking.ingestForTesting(eventForState(VoiceUiState.speaking));
      await tester.pumpAndSettle();
      
      final speakingBox = tester.widget<Container>(find.byKey(const Key('voice_status_state_badge')));
      final speakingColor = (speakingBox.decoration as BoxDecoration).color;
      final speakingDot = tester.widget<Container>(find.descendant(of: find.byKey(const Key('voice_status_state_badge')), matching: find.byType(Container)).last);
      final speakingDotColor = (speakingDot.decoration as BoxDecoration).color;

      final controllerGreeting = AgentActivityController();
      addTearDown(controllerGreeting.dispose);
      await pumpStatusBar(tester, controller: controllerGreeting);
      controllerGreeting.ingestForTesting(eventForState(VoiceUiState.greeting));
      await tester.pumpAndSettle();
      
      final greetingBox = tester.widget<Container>(find.byKey(const Key('voice_status_state_badge')));
      final greetingColor = (greetingBox.decoration as BoxDecoration).color;
      final greetingDot = tester.widget<Container>(find.descendant(of: find.byKey(const Key('voice_status_state_badge')), matching: find.byType(Container)).last);
      final greetingDotColor = (greetingDot.decoration as BoxDecoration).color;

      expect(greetingColor, equals(speakingColor));
      expect(greetingDotColor, equals(speakingDotColor));
    });

    testWidgets('shows tool detail when a tool is active', (tester) async {
      final controller = AgentActivityController();
      addTearDown(controller.dispose);

      await pumpStatusBar(tester, controller: controller);

      controller.ingestForTesting(eventForState(VoiceUiState.toolRunning));
      await tester.pump();

      expect(find.text('web_search'), findsOneWidget);
    });
  });
}
