import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/controllers/workspace_controller.dart';
import 'package:voice_assistant/state/models/workspace_models.dart';
import 'package:voice_assistant/widgets/layout/left_navigation_rail.dart';

void main() {
  Future<void> pumpRail(
    WidgetTester tester, {
    required WorkspaceController workspaceController,
  }) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<WorkspaceController>.value(
        value: workspaceController,
        child: const MaterialApp(
          home: Scaffold(
            body: LeftNavigationRail(),
          ),
        ),
      ),
    );
  }

  group('LeftNavigationRail', () {
    testWidgets('renders empty when layout is compact', (tester) async {
      final workspaceController = WorkspaceController()
        ..setLayoutMode(WorkspaceLayoutMode.compact);

      await pumpRail(tester, workspaceController: workspaceController);
      expect(find.byType(Container), findsNothing);
    });

    testWidgets('renders rail when layout is medium', (tester) async {
      final workspaceController = WorkspaceController()
        ..setLayoutMode(WorkspaceLayoutMode.medium);

      await pumpRail(tester, workspaceController: workspaceController);
      expect(find.byKey(const Key('left_navigation_rail')), findsOneWidget);
    });

    testWidgets('tapping an unselected tab selects it and opens workbench', (tester) async {
      final workspaceController = WorkspaceController()
        ..setLayoutMode(WorkspaceLayoutMode.wide)
        ..setWorkbenchVisible(false)
        ..selectWorkbenchTab(WorkbenchTab.agents);

      await pumpRail(tester, workspaceController: workspaceController);

      await tester.tap(find.byKey(const Key('rail_tab_timeline')));
      await tester.pump();

      expect(workspaceController.selectedWorkbenchTab, WorkbenchTab.tasks);
      expect(workspaceController.workbenchVisible, isTrue);
    });

    testWidgets('tapping a selected tab toggles workbench visibility', (tester) async {
      final workspaceController = WorkspaceController()
        ..setLayoutMode(WorkspaceLayoutMode.wide)
        ..setWorkbenchVisible(true)
        ..selectWorkbenchTab(WorkbenchTab.agents);

      await pumpRail(tester, workspaceController: workspaceController);

      await tester.tap(find.byKey(const Key('rail_tab_agents')));
      await tester.pump();

      expect(workspaceController.workbenchVisible, isFalse);

      await tester.tap(find.byKey(const Key('rail_tab_agents')));
      await tester.pump();

      expect(workspaceController.workbenchVisible, isTrue);
    });
  });
}
