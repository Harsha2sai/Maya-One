import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/controllers/workspace_controller.dart';
import 'package:voice_assistant/state/models/workspace_models.dart';
import 'package:voice_assistant/widgets/layout/workspace_scaffold.dart';

void main() {
  Future<void> pumpScaffold(
    WidgetTester tester, {
    required WorkspaceController workspaceController,
    Widget? voiceActionDock,
  }) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<WorkspaceController>.value(
        value: workspaceController,
        child: MaterialApp(
          home: WorkspaceScaffold(
            background: const ColoredBox(key: Key('background'), color: Colors.black),
            centerStage: const ColoredBox(key: Key('center-stage'), color: Colors.blue),
            leftNavigationRail: const SizedBox(key: Key('left-rail'), width: 100),
            statusPanel: const SizedBox(key: Key('status-panel'), width: 20, height: 20),
            leftControlBar: const SizedBox(key: Key('left-control-bar'), width: 20, height: 20),
            voiceActionDock: voiceActionDock,
          ),
        ),
      ),
    );
  }

  group('WorkspaceScaffold', () {
    testWidgets('renders core shell slots', (tester) async {
      final workspaceController = WorkspaceController()..setLayoutMode(WorkspaceLayoutMode.medium);

      await pumpScaffold(tester, workspaceController: workspaceController);

      expect(find.byKey(const Key('workspace_scaffold_root')), findsOneWidget);
      expect(find.byKey(const ValueKey<String>('workspace_layout_medium')), findsOneWidget);
      expect(find.byKey(const Key('background')), findsOneWidget);
      expect(find.byKey(const Key('center-stage')), findsOneWidget);
      expect(find.byKey(const Key('left-rail')), findsOneWidget);
      expect(find.byKey(const Key('status-panel')), findsOneWidget);
      expect(find.byKey(const Key('left-control-bar')), findsOneWidget);
    });

    testWidgets('switches layout branches without replacing the scaffold root', (tester) async {
      final workspaceController = WorkspaceController()..setLayoutMode(WorkspaceLayoutMode.compact);

      await pumpScaffold(tester, workspaceController: workspaceController);
      expect(find.byKey(const ValueKey<String>('workspace_layout_compact')), findsOneWidget);
      final scaffoldElement = tester.element(find.byKey(const Key('workspace_scaffold_root')));

      workspaceController.setLayoutMode(WorkspaceLayoutMode.wide);
      await tester.pump();

      expect(find.byKey(const ValueKey<String>('workspace_layout_wide')), findsOneWidget);
      expect(tester.element(find.byKey(const Key('workspace_scaffold_root'))), same(scaffoldElement));
    });

    testWidgets('exercises compact medium and wide branches', (tester) async {
      final workspaceController = WorkspaceController()..setLayoutMode(WorkspaceLayoutMode.compact);

      await pumpScaffold(tester, workspaceController: workspaceController);
      expect(find.byKey(const ValueKey<String>('workspace_layout_compact')), findsOneWidget);

      workspaceController.setLayoutMode(WorkspaceLayoutMode.medium);
      await tester.pump();
      expect(find.byKey(const ValueKey<String>('workspace_layout_medium')), findsOneWidget);

      workspaceController.setLayoutMode(WorkspaceLayoutMode.wide);
      await tester.pump();
      expect(find.byKey(const ValueKey<String>('workspace_layout_wide')), findsOneWidget);
    });

    testWidgets('positions voice action dock for compact and wide layouts', (tester) async {
      final workspaceController = WorkspaceController()..setLayoutMode(WorkspaceLayoutMode.compact);

      await pumpScaffold(
        tester,
        workspaceController: workspaceController,
        voiceActionDock: const SizedBox(key: Key('voice-dock'), width: 40, height: 40),
      );

      final Positioned compactPositioned = tester.widget<Positioned>(
        find.ancestor(
          of: find.byKey(const Key('voice-dock')),
          matching: find.byType(Positioned),
        ),
      );
      expect(compactPositioned.left, 0);
      expect(compactPositioned.right, 0);
      expect(compactPositioned.bottom, 20);

      workspaceController.setLayoutMode(WorkspaceLayoutMode.wide);
      await tester.pump();

      final positionedWidgets = tester.widgetList<Positioned>(
        find.ancestor(
          of: find.byKey(const Key('voice-dock')),
          matching: find.byType(Positioned),
        ),
      );
      final widePositioned = positionedWidgets.last;
      expect(widePositioned.right, 24);
      expect(widePositioned.bottom, 24);
    });
  });
}
