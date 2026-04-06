import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/core/events/agent_event_models.dart';
import 'package:voice_assistant/state/controllers/agent_activity_controller.dart';
import 'package:voice_assistant/state/controllers/orb_controller.dart';
import 'package:voice_assistant/widgets/layout/agent_orb_state_bridge.dart';

void main() {
  Future<void> pumpBridge(
    WidgetTester tester, {
    required AgentActivityController activityController,
    required OrbController orbController,
  }) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AgentActivityController>.value(value: activityController),
          ChangeNotifierProvider<OrbController>.value(value: orbController),
        ],
        child: const MaterialApp(
          home: AgentOrbStateBridge(
            child: SizedBox(key: Key('orb_bridge_child')),
          ),
        ),
      ),
    );
  }

  group('AgentOrbStateBridge', () {
    testWidgets('maps speaking greeting and thinking states into orb lifecycle', (tester) async {
      final activityController = AgentActivityController();
      final orbController = OrbController();
      addTearDown(activityController.dispose);
      addTearDown(orbController.dispose);

      await pumpBridge(
        tester,
        activityController: activityController,
        orbController: orbController,
      );

      activityController.ingestForTesting(
        const AgentUiEvent(
          eventType: 'agent_thinking',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        ),
      );
      await tester.pump();
      expect(orbController.lifecycle, OrbLifecycle.initializing);

      activityController.ingestForTesting(
        const AgentUiEvent(
          eventType: 'track_subscribed',
          schemaVersion: '1.0',
          timestamp: 2,
          payload: <String, dynamic>{},
        ),
      );
      await tester.pump();
      expect(orbController.lifecycle, OrbLifecycle.speaking);

      activityController.ingestForTesting(
        const AgentUiEvent(
          eventType: 'agent_speaking',
          schemaVersion: '1.0',
          timestamp: 3,
          payload: <String, dynamic>{'status': 'speaking'},
        ),
      );
      await tester.pump();
      expect(orbController.lifecycle, OrbLifecycle.speaking);
    });

    testWidgets('maps listening bootstrapping and offline states', (tester) async {
      final activityController = AgentActivityController();
      final orbController = OrbController();
      addTearDown(activityController.dispose);
      addTearDown(orbController.dispose);

      await pumpBridge(
        tester,
        activityController: activityController,
        orbController: orbController,
      );

      activityController.ingestForTesting(
        const AgentUiEvent(
          eventType: 'user_speaking',
          schemaVersion: '1.0',
          timestamp: 1,
          payload: <String, dynamic>{},
        ),
      );
      await tester.pump();
      expect(orbController.lifecycle, OrbLifecycle.listening);

      activityController.ingestForTesting(
        const AgentUiEvent(
          eventType: 'bootstrap_started',
          schemaVersion: '1.0',
          timestamp: 2,
          payload: <String, dynamic>{},
        ),
      );
      await tester.pump();
      expect(orbController.lifecycle, OrbLifecycle.initializing);

      activityController.ingestForTesting(
        const AgentUiEvent(
          eventType: 'session_disconnected',
          schemaVersion: '1.0',
          timestamp: 3,
          payload: <String, dynamic>{},
        ),
      );
      await tester.pump();
      expect(orbController.lifecycle, OrbLifecycle.muted);
    });
  });
}
