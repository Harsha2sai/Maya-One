import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/controllers/agent_activity_controller.dart';
import 'package:voice_assistant/state/controllers/composer_controller.dart';
import 'package:voice_assistant/state/controllers/overlay_controller.dart';
import 'package:voice_assistant/state/controllers/workspace_controller.dart';
import 'package:voice_assistant/state/models/workspace_models.dart';
import 'package:voice_assistant/widgets/layout/voice_action_dock.dart';

void main() {
  Future<void> pumpDock(
    WidgetTester tester, {
    required AgentActivityController activityController,
    required ComposerController composerController,
    WorkspaceController? workspaceController,
    OverlayController? overlayController,
  }) async {
    workspaceController ??= WorkspaceController()..setLayoutMode(WorkspaceLayoutMode.compact);
    overlayController ??= OverlayController();
    
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AgentActivityController>.value(value: activityController),
          ChangeNotifierProvider<ComposerController>.value(value: composerController),
          ChangeNotifierProvider<WorkspaceController>.value(value: workspaceController),
          ChangeNotifierProvider<OverlayController>.value(value: overlayController),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: Center(
              child: VoiceActionDock(),
            ),
          ),
        ),
      ),
    );
  }

  group('VoiceActionDock', () {
    testWidgets('dock visibility depends on layout mode and sheet state', (tester) async {
      final activityController = AgentActivityController();
      final composerController = ComposerController();
      final workspaceController = WorkspaceController();
      final overlayController = OverlayController();
      
      addTearDown(activityController.dispose);
      addTearDown(composerController.dispose);
      addTearDown(workspaceController.dispose);
      addTearDown(overlayController.dispose);

      await pumpDock(
        tester,
        activityController: activityController,
        composerController: composerController,
        workspaceController: workspaceController,
        overlayController: overlayController,
      );

      // Compact -> visible
      workspaceController.setLayoutMode(WorkspaceLayoutMode.compact);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('voice_action_dock')), findsOneWidget);

      // Wide -> hidden
      workspaceController.setLayoutMode(WorkspaceLayoutMode.wide);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('voice_action_dock')), findsNothing);

      // Medium, sheet open -> hidden
      workspaceController.setLayoutMode(WorkspaceLayoutMode.medium);
      overlayController.setCompactWorkbenchSheetOpen(true);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('voice_action_dock')), findsNothing);

      // Medium, sheet closed -> visible
      overlayController.setCompactWorkbenchSheetOpen(false);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('voice_action_dock')), findsOneWidget);
    });

    testWidgets('buttons are always rendered when dock is visible', (tester) async {
      final activityController = AgentActivityController();
      final composerController = ComposerController();
      addTearDown(activityController.dispose);
      addTearDown(composerController.dispose);

      await pumpDock(
        tester,
        activityController: activityController,
        composerController: composerController,
      );

      expect(find.byKey(const Key('voice_action_primary_toggle')), findsOneWidget);
      expect(find.byKey(const Key('voice_action_interrupt')), findsOneWidget);
      expect(find.byKey(const Key('voice_action_reveal_composer')), findsOneWidget);
    });

    testWidgets('mic toggle switches the composer voice mode', (tester) async {
      final activityController = AgentActivityController();
      final composerController = ComposerController();
      addTearDown(activityController.dispose);
      addTearDown(composerController.dispose);

      await pumpDock(
        tester,
        activityController: activityController,
        composerController: composerController,
      );

      expect(composerController.voiceMode, VoiceInputMode.pushToTalk);

      await tester.tap(find.byKey(const Key('voice_action_primary_toggle')));
      await tester.pump();
      expect(composerController.voiceMode, VoiceInputMode.continuous);

      await tester.tap(find.byKey(const Key('voice_action_primary_toggle')));
      await tester.pump();
      expect(composerController.voiceMode, VoiceInputMode.pushToTalk);
    });

    testWidgets('reveal composer is disabled if already revealed', (tester) async {
      final activityController = AgentActivityController();
      final composerController = ComposerController()..setComposerRevealed(true);
      addTearDown(activityController.dispose);
      addTearDown(composerController.dispose);

      await pumpDock(
        tester,
        activityController: activityController,
        composerController: composerController,
      );

      final inkWellFinder = find.descendant(
        of: find.byKey(const Key('voice_action_reveal_composer')),
        matching: find.byType(InkWell),
      );
      
      final InkWell inkWell = tester.widget(inkWellFinder);
      expect(inkWell.onTap, isNull); // disabled
    });
  });
}
