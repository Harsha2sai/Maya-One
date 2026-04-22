import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/state/controllers/ide_workspace_controller.dart';
import 'package:voice_assistant/widgets/features/ide/buddy_monitor.dart';

void main() {
  testWidgets('buddy monitor renders live idle state', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: BuddyMonitor(
            species: BuddySpecies.mayaCore,
            state: BuddyState.idle,
            isShiny: false,
            catchingUp: false,
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('buddy-monitor')), findsOneWidget);
    expect(find.text('Live'), findsOneWidget);
    expect(find.text('Idle'), findsOneWidget);
  });

  testWidgets('buddy monitor renders catching up and working state', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: BuddyMonitor(
            species: BuddySpecies.orbitFox,
            state: BuddyState.working,
            isShiny: true,
            catchingUp: true,
          ),
        ),
      ),
    );

    expect(find.text('Catching up'), findsOneWidget);
    expect(find.text('Working'), findsOneWidget);
  });
}
