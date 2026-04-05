import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:voice_assistant/core/events/agent_event_models.dart';
import 'package:voice_assistant/state/controllers/agent_activity_controller.dart';
import 'package:voice_assistant/state/controllers/orb_controller.dart';
import 'package:voice_assistant/widgets/layout/agent_orb_state_bridge.dart';

AgentUiEvent _event(String type) {
  return AgentUiEvent(
    eventType: type,
    schemaVersion: '1.0',
    timestamp: DateTime.now().millisecondsSinceEpoch,
    payload: const <String, dynamic>{},
  );
}

void main() {
  test('AgentActivityController no longer writes orb lifecycle directly', () {
    final controller = AgentActivityController();
    final orb = OrbController();
    controller.bindOrb(orb);

    controller.ingestForTesting(_event('user_speaking'));

    // Bridge is now the single writer for orb lifecycle transitions.
    expect(orb.lifecycle, OrbLifecycle.hidden);
  });

  testWidgets('AgentOrbStateBridge applies orb lifecycle on post-frame sync', (tester) async {
    final events = StreamController<AgentUiEvent>.broadcast(sync: true);
    final activity = AgentActivityController(agentEvents: events.stream);
    final orb = OrbController();

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AgentActivityController>.value(value: activity),
          ChangeNotifierProvider<OrbController>.value(value: orb),
        ],
        child: const MaterialApp(
          home: AgentOrbStateBridge(
            child: SizedBox.shrink(),
          ),
        ),
      ),
    );

    events.add(_event('user_speaking'));
    await tester.pump();
    await tester.pump();

    expect(orb.lifecycle, OrbLifecycle.listening);
    await events.close();
  });
}
